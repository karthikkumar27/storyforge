import os
import shutil
import subprocess
import tempfile

import httpx

from config import ELEVENLABS_BASE_URL, VOICE_MAP, MUSIC_TAGS, PRESET_NAME


class AudioMixer:
    def __init__(self):
        self.api_key = os.environ.get("ELEVENLABS_API_KEY")
        if not self.api_key:
            raise ValueError("ELEVENLABS_API_KEY environment variable is not set")

    def _generate_voiceover(self, narrative: str, genre: str, workdir: str) -> str:
        """Generate voiceover MP3 via ElevenLabs TTS."""
        default_voice = list(VOICE_MAP.values())[0]
        voice_id = VOICE_MAP.get(genre, default_voice)
        print(f"[AudioMixer] Generating voiceover — genre: {genre}, voice: {voice_id}", flush=True)
        resp = httpx.post(
            f"{ELEVENLABS_BASE_URL}/text-to-speech/{voice_id}",
            headers={"xi-api-key": self.api_key, "Content-Type": "application/json"},
            json={
                "text": narrative,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
            },
            timeout=60,
        )
        if resp.status_code >= 400:
            raise RuntimeError(
                f"ElevenLabs TTS failed: HTTP {resp.status_code} — {resp.text[:500]}"
            )
        vo_path = os.path.join(workdir, "voiceover.mp3")
        with open(vo_path, "wb") as f:
            f.write(resp.content)
        print(f"[AudioMixer] Voiceover generated: {len(resp.content)} bytes", flush=True)
        return vo_path

    def _generate_bgm(self, video_path: str, genre: str, workdir: str) -> str | None:
        """Generate background music via ElevenLabs Video-to-Music API."""
        description = f"{PRESET_NAME} background music for a {genre} video. Mood should match the visuals."
        print(f"[AudioMixer] Generating BGM via Video-to-Music — tags: {MUSIC_TAGS}", flush=True)

        try:
            with open(video_path, "rb") as video_file:
                resp = httpx.post(
                    f"{ELEVENLABS_BASE_URL}/music/video-to-music",
                    headers={"xi-api-key": self.api_key},
                    data={
                        "description": description,
                        "tags": MUSIC_TAGS,
                    },
                    files={"videos": ("video.mp4", video_file, "video/mp4")},
                    timeout=180,
                )

            if resp.status_code >= 400:
                print(f"[AudioMixer] Video-to-Music failed: HTTP {resp.status_code} — {resp.text[:300]}", flush=True)
                print("[AudioMixer] Falling back to voiceover only", flush=True)
                return None

            bgm_path = os.path.join(workdir, "bgm.mp3")
            with open(bgm_path, "wb") as f:
                f.write(resp.content)
            print(f"[AudioMixer] BGM generated: {len(resp.content)} bytes", flush=True)
            return bgm_path

        except Exception as exc:
            print(f"[AudioMixer] Video-to-Music error: {exc}", flush=True)
            print("[AudioMixer] Falling back to voiceover only", flush=True)
            return None

    def mix(self, video_path: str, narrative: str, genre: str) -> str:
        output_path = video_path.replace("stitched.mp4", "final.mp4")
        if output_path == video_path:
            raise ValueError(
                f"video_path must contain 'stitched.mp4' to derive output path, got: {video_path}"
            )

        workdir = tempfile.mkdtemp(prefix="audio_")
        try:
            voiceover_path = self._generate_voiceover(narrative, genre, workdir)
            bgm_path = self._generate_bgm(video_path, genre, workdir)

            if bgm_path:
                # Voiceover + background music
                print("[AudioMixer] Mixing voiceover + BGM", flush=True)
                cmd = [
                    "ffmpeg", "-y",
                    "-i", video_path,
                    "-i", voiceover_path,
                    "-i", bgm_path,
                    "-filter_complex",
                    "[1:a]volume=1.0[vo];[2:a]volume=0.10[bg];[vo][bg]amix=inputs=2:duration=first[aout]",
                    "-map", "0:v", "-map", "[aout]",
                    "-c:v", "copy", "-c:a", "aac", "-shortest",
                    output_path,
                ]
            else:
                # Voiceover only
                print("[AudioMixer] Using voiceover only (no BGM)", flush=True)
                cmd = [
                    "ffmpeg", "-y",
                    "-i", video_path,
                    "-i", voiceover_path,
                    "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-shortest",
                    output_path,
                ]

            subprocess.run(cmd, check=True, capture_output=True)
            print("[AudioMixer] Final video mixed successfully", flush=True)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

        return output_path

    def mix_with_native_audio(
        self,
        video_path: str,
        narrative: str,
        genre: str,
        narration_volume: float = 1.0,
        ambient_volume: float = 0.32,
        narration_start_offset: float = 0.0,
        narration_end_buffer: float = 0.0,
    ) -> str:
        """Mix ElevenLabs narration over the video's NATIVE audio track
        (which already contains Seedance's ambient + SFX + lip-sync sounds).
        No ElevenLabs BGM is generated — Seedance's native audio is the bed.

        narration_start_offset: seconds to delay the narration start (e.g. so
            it doesn't speak over the title card sting). 5.0 for preset-7's
            5-second title card.

        narration_end_buffer: seconds of silence the narration should leave at
            the end of the story segment (so it doesn't overlap the end card).
            5.0 for preset-7's 5-second end card. The narration is faded out
            over the last 0.5s before this buffer begins.

        Volumes follow broadcast voiceover-over-ambient convention:
        - narration_volume = 1.0  (100% — the story's voice, must dominate)
        - ambient_volume   = 0.32 (~32% — audible bed without fighting speech)

        All four parameters are tunable per preset via the audio_mix config
        block (see config.py PRESETS).
        """
        output_path = video_path.replace("stitched.mp4", "final.mp4")
        if output_path == video_path:
            raise ValueError(
                f"video_path must contain 'stitched.mp4' to derive output path, got: {video_path}"
            )

        workdir = tempfile.mkdtemp(prefix="audio_")
        try:
            voiceover_path = self._generate_voiceover(narrative, genre, workdir)

            # Probe video duration so we can compute end-buffer fade timing
            video_duration = self._probe_duration(video_path)
            story_window_end = max(narration_start_offset, video_duration - narration_end_buffer)

            print(
                f"[AudioMixer] Mixing narration ({narration_volume:.2f}) "
                f"+ native ambient ({ambient_volume:.2f}); "
                f"narration window: {narration_start_offset:.1f}s - {story_window_end:.1f}s "
                f"of {video_duration:.1f}s video",
                flush=True,
            )

            # Build the narration stream:
            # 1. Delay it by narration_start_offset (so title card plays clean)
            # 2. Set its volume
            # 3. Fade out at the end of the story window (so end card plays clean)
            vo_filters = []
            if narration_start_offset > 0:
                # adelay takes ms per channel
                delay_ms = int(narration_start_offset * 1000)
                vo_filters.append(f"adelay={delay_ms}|{delay_ms}")
            vo_filters.append(f"volume={narration_volume}")
            if narration_end_buffer > 0 and story_window_end < video_duration:
                fade_dur = 0.5
                fade_start = max(0.0, story_window_end - fade_dur)
                vo_filters.append(f"afade=t=out:st={fade_start}:d={fade_dur}")
            vo_chain = ",".join(vo_filters)

            filter_complex = (
                f"[1:a]{vo_chain}[vo];"
                f"[0:a]volume={ambient_volume}[amb];"
                f"[vo][amb]amix=inputs=2:duration=longest:dropout_transition=0[aout]"
            )
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-i", voiceover_path,
                "-filter_complex", filter_complex,
                "-map", "0:v", "-map", "[aout]",
                "-c:v", "copy", "-c:a", "aac", "-shortest",
                output_path,
            ]

            subprocess.run(cmd, check=True, capture_output=True)
            print("[AudioMixer] Narration + native ambient mix complete", flush=True)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

        return output_path

    @staticmethod
    def _probe_duration(video_path: str) -> float:
        """Return the duration of a video file in seconds via ffprobe."""
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return float(result.stdout.strip())

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
                    "[1:a]volume=1.0[vo];[2:a]volume=0.25[bg];[vo][bg]amix=inputs=2:duration=first[aout]",
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

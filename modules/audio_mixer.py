import os
import shutil
import subprocess
import tempfile

import httpx

from config import ELEVENLABS_BASE_URL, VOICE_MAP, MUSIC_MAP


class AudioMixer:
    def __init__(self):
        self.api_key = os.environ.get("ELEVENLABS_API_KEY")
        if not self.api_key:
            raise ValueError("ELEVENLABS_API_KEY environment variable is not set")

    def _generate_voiceover(self, narrative: str, genre: str, workdir: str) -> str:
        """Generate voiceover MP3 into the given workdir. Returns path to the mp3."""
        voice_id = VOICE_MAP.get(genre, VOICE_MAP["blend"])
        resp = httpx.post(
            f"{ELEVENLABS_BASE_URL}/text-to-speech/{voice_id}",
            headers={"xi-api-key": self.api_key, "Content-Type": "application/json"},
            json={
                "text": narrative,
                "model_id": "eleven_monolingual_v1",
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
            },
            timeout=60,
        )
        resp.raise_for_status()
        vo_path = os.path.join(workdir, "voiceover.mp3")
        with open(vo_path, "wb") as f:
            f.write(resp.content)
        return vo_path

    def mix(self, video_path: str, narrative: str, genre: str) -> str:
        output_path = video_path.replace("stitched.mp4", "final.mp4")
        if output_path == video_path:
            raise ValueError(
                f"video_path must contain 'stitched.mp4' to derive output path, got: {video_path}"
            )

        workdir = tempfile.mkdtemp(prefix="audio_")
        try:
            voiceover_path = self._generate_voiceover(narrative, genre, workdir)
            music_path = MUSIC_MAP.get(genre, MUSIC_MAP["blend"])
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i", video_path,
                    "-i", voiceover_path,
                    "-i", music_path,
                    "-filter_complex",
                    "[1:a]volume=1.0[vo];[2:a]volume=0.3[bg];[vo][bg]amix=inputs=2:duration=first[aout]",
                    "-map", "0:v",
                    "-map", "[aout]",
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-shortest",
                    output_path,
                ],
                check=True,
                capture_output=True,
            )
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

        return output_path

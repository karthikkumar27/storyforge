import os
import time
import subprocess
import tempfile

import httpx
import jwt

from config import (
    KLING_BASE_URL, KLING_MODEL, SHOT_DURATION, ASPECT_RATIO,
    POLL_INTERVAL_SEC, MAX_POLL_ATTEMPTS,
)


class VideoProducer:
    def __init__(self):
        self.access_key_id = os.environ["KLING_ACCESS_KEY_ID"]
        self.secret_key = os.environ["KLING_SECRET_KEY"]

    def _jwt_token(self) -> str:
        now = int(time.time())
        payload = {"iss": self.access_key_id, "exp": now + 1800, "nbf": now - 5}
        return jwt.encode(payload, self.secret_key, algorithm="HS256")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._jwt_token()}",
            "Content-Type": "application/json",
        }

    def _submit_shot(self, prompt: str) -> str:
        resp = httpx.post(
            f"{KLING_BASE_URL}/v1/videos/text2video",
            headers=self._headers(),
            json={"model": KLING_MODEL, "prompt": prompt,
                  "duration": SHOT_DURATION, "aspect_ratio": ASPECT_RATIO},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["data"]["task_id"]

    def _poll_shot(self, task_id: str) -> str:
        for _ in range(MAX_POLL_ATTEMPTS):
            resp = httpx.get(
                f"{KLING_BASE_URL}/v1/videos/text2video/{task_id}",
                headers=self._headers(),
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()["data"]
            if data["task_status"] == "succeed":
                return data["videos"][0]["url"]
            if data["task_status"] == "failed":
                raise RuntimeError(f"Kling task {task_id} failed")
            time.sleep(POLL_INTERVAL_SEC)
        raise TimeoutError(f"Kling task {task_id} timed out after {MAX_POLL_ATTEMPTS} polls")

    def _download_clip(self, url: str, path: str) -> None:
        with httpx.stream("GET", url, timeout=120) as resp:
            resp.raise_for_status()
            with open(path, "wb") as f:
                for chunk in resp.iter_bytes():
                    f.write(chunk)

    def _stitch(self, clip_paths: list[str], output_path: str) -> None:
        concat_file = os.path.join(os.path.dirname(output_path), "concat.txt")
        with open(concat_file, "w") as f:
            for p in clip_paths:
                f.write(f"file '{p}'\n")
        subprocess.run(
            ["ffmpeg", "-f", "concat", "-safe", "0", "-i", concat_file,
             "-c", "copy", output_path, "-y"],
            check=True,
            capture_output=True,
        )

    def produce(self, shots: list[str]) -> str:
        workdir = tempfile.mkdtemp(prefix="cinematic_")
        clip_paths = []
        for i, prompt in enumerate(shots):
            task_id = self._submit_shot(prompt)
            video_url = self._poll_shot(task_id)
            clip_path = os.path.join(workdir, f"shot_{i:02d}.mp4")
            self._download_clip(video_url, clip_path)
            clip_paths.append(clip_path)
        output_path = os.path.join(workdir, "stitched.mp4")
        self._stitch(clip_paths, output_path)
        return output_path

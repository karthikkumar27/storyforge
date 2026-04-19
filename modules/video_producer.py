import os
import shutil
import time
import subprocess
import tempfile
from abc import ABC, abstractmethod

import httpx

from config import (
    VIDEO_PROVIDER,
    SHOT_DURATION, ASPECT_RATIO,
    KLING_BASE_URL, KLING_MODEL, KLING_POLL_INTERVAL_SEC, KLING_MAX_POLL_ATTEMPTS,
    SEEDANCE_MODEL, SEEDANCE_BASE_URL, SEEDANCE_RESOLUTION,
    SEEDANCE_POLL_INTERVAL_SEC, SEEDANCE_MAX_POLL_ATTEMPTS,
)


class BaseVideoProducer(ABC):
    @abstractmethod
    def _submit_shot(self, prompt: str, reference_image_url: str | None = None) -> str:
        ...

    @abstractmethod
    def _poll_shot(self, task_id: str) -> str:
        ...

    def _download_clip(self, url: str, path: str) -> None:
        with httpx.stream("GET", url, timeout=120) as resp:
            resp.raise_for_status()
            with open(path, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=65536):
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

    def produce(self, shots: list[str], reference_image_url: str | None = None) -> str:
        workdir = tempfile.mkdtemp(prefix="cinematic_")
        try:
            clip_paths = []
            for i, prompt in enumerate(shots):
                print(f"[VideoProducer] Submitting shot {i+1}/{len(shots)}", flush=True)
                task_id = self._submit_shot(prompt, reference_image_url)
                print(f"[VideoProducer] Polling task {task_id}...", flush=True)
                video_url = self._poll_shot(task_id)
                clip_path = os.path.join(workdir, f"shot_{i:02d}.mp4")
                self._download_clip(video_url, clip_path)
                clip_paths.append(clip_path)
                print(f"[VideoProducer] Shot {i+1} downloaded", flush=True)
            output_path = os.path.join(workdir, "stitched.mp4")
            self._stitch(clip_paths, output_path)
            print(f"[VideoProducer] All {len(shots)} shots stitched", flush=True)
            return output_path
        except Exception:
            shutil.rmtree(workdir, ignore_errors=True)
            raise


class KlingVideoProducer(BaseVideoProducer):
    def __init__(self):
        import jwt
        self._jwt = jwt
        self.access_key_id = os.environ["KLING_ACCESS_KEY_ID"]
        self.secret_key = os.environ["KLING_SECRET_KEY"]

    def _jwt_token(self) -> str:
        now = int(time.time())
        payload = {"iss": self.access_key_id, "exp": now + 1800, "nbf": now - 5}
        return self._jwt.encode(payload, self.secret_key, algorithm="HS256")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._jwt_token()}",
            "Content-Type": "application/json",
        }

    def _submit_shot(self, prompt: str, reference_image_url: str | None = None) -> str:
        resp = httpx.post(
            f"{KLING_BASE_URL}/v1/videos/text2video",
            headers=self._headers(),
            json={"model": KLING_MODEL, "prompt": prompt,
                  "duration": SHOT_DURATION, "aspect_ratio": ASPECT_RATIO},
            timeout=30,
        )
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Kling submit failed: HTTP {resp.status_code} — body: {resp.text}"
            )
        return resp.json()["data"]["task_id"]

    def _poll_shot(self, task_id: str) -> str:
        for _ in range(KLING_MAX_POLL_ATTEMPTS):
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
            time.sleep(KLING_POLL_INTERVAL_SEC)
        raise TimeoutError(f"Kling task {task_id} timed out after {KLING_MAX_POLL_ATTEMPTS} polls")


class SeedanceVideoProducer(BaseVideoProducer):
    def __init__(self):
        from byteplussdkarkruntime import Ark
        self.client = Ark(
            base_url=SEEDANCE_BASE_URL,
            api_key=os.environ["ARK_API_KEY"],
        )

    def _submit_shot(self, prompt: str, reference_image_url: str | None = None) -> str:
        content = [{"type": "text", "text": prompt}]

        if reference_image_url:
            content.append({
                "type": "image_url",
                "image_url": {"url": reference_image_url},
                "role": "first_frame",
            })

        result = self.client.content_generation.tasks.create(
            model=SEEDANCE_MODEL,
            content=content,
            ratio=ASPECT_RATIO,
            resolution=SEEDANCE_RESOLUTION,
            duration=SHOT_DURATION,
        )
        print(f"[Seedance] Task created: {result.id}", flush=True)
        return result.id

    def _poll_shot(self, task_id: str) -> str:
        for attempt in range(SEEDANCE_MAX_POLL_ATTEMPTS):
            task = self.client.content_generation.tasks.get(task_id=task_id)
            status = task.status
            if status == "succeeded":
                content = task.content
                print(f"[Seedance] Task {task_id} succeeded", flush=True)
                if isinstance(content, list):
                    for item in content:
                        url = getattr(item, "video_url", None)
                        if url:
                            return url if isinstance(url, str) else url.url
                else:
                    url = getattr(content, "video_url", None)
                    if url:
                        return url if isinstance(url, str) else url.url
                raise RuntimeError(
                    f"Seedance task {task_id} succeeded but no video URL found: {content}"
                )
            if status == "failed":
                error_msg = getattr(task, "error", None) or "unknown error"
                raise RuntimeError(f"Seedance task {task_id} failed: {error_msg}")
            if attempt % 2 == 0:
                print(f"[Seedance] Task {task_id} status: {status}, waiting...", flush=True)
            time.sleep(SEEDANCE_POLL_INTERVAL_SEC)
        raise TimeoutError(
            f"Seedance task {task_id} timed out after {SEEDANCE_MAX_POLL_ATTEMPTS * SEEDANCE_POLL_INTERVAL_SEC}s"
        )


def create_video_producer() -> BaseVideoProducer:
    if VIDEO_PROVIDER == "kling":
        print("[VideoProducer] Using Kling backend", flush=True)
        return KlingVideoProducer()
    print("[VideoProducer] Using Seedance 1.5 Pro backend", flush=True)
    return SeedanceVideoProducer()

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
    ATLAS_BASE_URL, ATLAS_VIDEO_MODEL_I2V, ATLAS_VIDEO_MODEL_T2V, ATLAS_POLL_INTERVAL_SEC, ATLAS_MAX_POLL_ATTEMPTS,
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

    def _stitch(
        self,
        clip_paths: list[str],
        output_path: str,
        title_card: str | None = None,
        end_card: str | None = None,
    ) -> None:
        """Concat shots into one MP4, optionally prepending a title card and
        appending an end card.

        Without cards: uses fast `-c copy` (assumes all shots share format).
        With cards: re-encodes via filter_complex concat so format mismatches
        between externally-built cards and AI-generated shots don't break playback.
        """
        all_paths = []
        if title_card:
            all_paths.append(title_card)
        all_paths.extend(clip_paths)
        if end_card:
            all_paths.append(end_card)

        # Fast path — pure shots, all from same source (all h264 from Seedance/Kling)
        if not title_card and not end_card:
            concat_file = os.path.join(os.path.dirname(output_path), "concat.txt")
            with open(concat_file, "w") as f:
                for p in all_paths:
                    f.write(f"file '{p}'\n")
            subprocess.run(
                ["ffmpeg", "-f", "concat", "-safe", "0", "-i", concat_file,
                 "-c", "copy", output_path, "-y"],
                check=True,
                capture_output=True,
            )
            return

        # Cards present — re-encode via filter_complex concat for reliable playback
        # across mixed sources (renderer-built MP4s vs Atlas-generated shots).
        cmd = ["ffmpeg", "-y"]
        for p in all_paths:
            cmd += ["-i", str(p)]

        n = len(all_paths)
        filter_inputs = "".join(f"[{i}:v:0][{i}:a:0]" for i in range(n))
        filter_complex = f"{filter_inputs}concat=n={n}:v=1:a=1[outv][outa]"

        cmd += [
            "-filter_complex", filter_complex,
            "-map", "[outv]", "-map", "[outa]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
            "-movflags", "+faststart",
            output_path,
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode()[-800:] if exc.stderr else ""
            raise RuntimeError(f"Stitch with cards failed: {stderr}") from exc

    def produce(
        self,
        shots: list[str],
        reference_image_url: str | None = None,
        storyboard_urls: list[str] | None = None,
    ) -> str:
        """Produce a stitched video from a list of shot prompts.

        Two modes for first-frame anchoring:

        - **Premium (preset-7)**: caller passes `storyboard_urls` — one URL per
          shot, each generated upstream by GPT Image 2 Edit using the locked
          character ref + shot prompt. Each shot is anchored to its own
          shot-appropriate frame, giving locked character identity AND varied
          starting poses. This is what fixes the wallpaper-effect problem.

        - **Legacy**: caller passes a single `reference_image_url` — used as
          the first frame for all shots (other presets, or fallback when
          storyboard generation fails).
        """
        workdir = tempfile.mkdtemp(prefix="cinematic_")
        try:
            clip_paths = []
            for i, prompt in enumerate(shots):
                print(f"[VideoProducer] Submitting shot {i+1}/{len(shots)}", flush=True)
                # Pick per-shot storyboard if provided, else fall back to single ref
                if storyboard_urls and i < len(storyboard_urls) and storyboard_urls[i]:
                    ref_url = storyboard_urls[i]
                    print(f"[VideoProducer]   shot {i+1} anchor: per-shot storyboard", flush=True)
                else:
                    ref_url = reference_image_url
                    if ref_url:
                        print(f"[VideoProducer]   shot {i+1} anchor: shared locked ref", flush=True)
                task_id = self._submit_shot(prompt, ref_url)
                print(f"[VideoProducer] Polling task {task_id}...", flush=True)
                video_url = self._poll_shot(task_id)
                clip_path = os.path.join(workdir, f"shot_{i:02d}.mp4")
                self._download_clip(video_url, clip_path)
                clip_paths.append(clip_path)
                print(f"[VideoProducer] Shot {i+1} downloaded", flush=True)

            # Optional title/end cards — built once and cached, reused across episodes.
            title_card = self._get_title_card()
            end_card = self._get_end_card()

            output_path = os.path.join(workdir, "stitched.mp4")
            self._stitch(
                clip_paths,
                output_path,
                title_card=str(title_card) if title_card else None,
                end_card=str(end_card) if end_card else None,
            )
            label = f"{len(shots)} shots"
            if title_card:
                label += " + title card"
            if end_card:
                label += " + end card"
            print(f"[VideoProducer] Stitched {label}", flush=True)
            return output_path
        except Exception:
            shutil.rmtree(workdir, ignore_errors=True)
            raise

    def _get_title_card(self):
        """Resolve the active preset's title card (built once, cached forever)."""
        from config import _preset
        cfg = _preset.get("title_card")
        if not cfg:
            return None
        from modules.title_card_renderer import build_card
        resolution = self._card_resolution()
        return build_card(cfg, resolution=resolution, aspect_ratio=ASPECT_RATIO, kind="title")

    def _get_end_card(self):
        """Resolve the active preset's end card (built once, cached forever)."""
        from config import _preset
        cfg = _preset.get("end_card")
        if not cfg:
            return None
        from modules.title_card_renderer import build_card
        resolution = self._card_resolution()
        return build_card(cfg, resolution=resolution, aspect_ratio=ASPECT_RATIO, kind="end")

    def _card_resolution(self) -> str:
        """Match the resolution we render shots at (provider-specific)."""
        if VIDEO_PROVIDER == "atlas":
            return "480p"
        if VIDEO_PROVIDER == "seedance":
            return SEEDANCE_RESOLUTION
        return "720p"


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


class AtlasVideoProducer(BaseVideoProducer):
    """Seedance 2.0 via Atlas Cloud unified API."""

    def __init__(self):
        self.api_key = os.environ["ATLASCLOUD_API_KEY"]
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _submit_shot(self, prompt: str, reference_image_url: str | None = None) -> str:
        if reference_image_url:
            model = ATLAS_VIDEO_MODEL_I2V
            print(f"[Atlas] Using image-to-video (shot 1 with reference)", flush=True)
        else:
            model = ATLAS_VIDEO_MODEL_T2V
            print(f"[Atlas] Using text-to-video (no reference image)", flush=True)

        body = {
            "model": model,
            "prompt": prompt,
            "duration": SHOT_DURATION,
            "resolution": "480p",
            "aspect_ratio": ASPECT_RATIO,
            "watermark": False,
        }
        if reference_image_url:
            body["image"] = reference_image_url

        resp = httpx.post(
            f"{ATLAS_BASE_URL}/model/generateVideo",
            headers=self.headers,
            json=body,
            timeout=60,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Atlas Cloud submit failed: HTTP {resp.status_code} — {resp.text[:500]}")
        prediction_id = resp.json()["data"]["id"]
        print(f"[Atlas] Task created: {prediction_id}", flush=True)
        return prediction_id

    def _poll_shot(self, task_id: str) -> str:
        for attempt in range(ATLAS_MAX_POLL_ATTEMPTS):
            resp = httpx.get(
                f"{ATLAS_BASE_URL}/model/prediction/{task_id}",
                headers=self.headers,
                timeout=30,
            )
            if resp.status_code in (400, 429, 500, 502, 503, 504):
                print(f"[Atlas] HTTP {resp.status_code}: {resp.text[:300]}", flush=True)
                if resp.status_code == 400:
                    raise RuntimeError(f"Atlas poll failed: HTTP 400 — {resp.text[:500]}")
                time.sleep(30)
                continue
            resp.raise_for_status()
            data = resp.json()["data"]
            status = data["status"]

            if status == "completed":
                outputs = data.get("outputs", [])
                if outputs:
                    print(f"[Atlas] Task {task_id} completed", flush=True)
                    return outputs[0]
                raise RuntimeError(f"Atlas task {task_id} completed but no outputs: {data}")
            if status == "failed":
                error = data.get("error", "unknown error")
                raise RuntimeError(f"Atlas task {task_id} failed: {error}")
            if attempt % 5 == 0:
                print(f"[Atlas] Task {task_id} status: {status}, waiting...", flush=True)
            time.sleep(ATLAS_POLL_INTERVAL_SEC)

        raise TimeoutError(
            f"Atlas task {task_id} timed out after {ATLAS_MAX_POLL_ATTEMPTS * ATLAS_POLL_INTERVAL_SEC}s"
        )


def create_video_producer() -> BaseVideoProducer:
    if VIDEO_PROVIDER == "atlas":
        print("[VideoProducer] Using Atlas Cloud — Seedance 2.0 Fast", flush=True)
        return AtlasVideoProducer()
    if VIDEO_PROVIDER == "kling":
        print("[VideoProducer] Using Kling backend", flush=True)
        return KlingVideoProducer()
    print("[VideoProducer] Using BytePlus Seedance 1.0 Pro backend", flush=True)
    return SeedanceVideoProducer()

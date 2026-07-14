import os
import time

import httpx

from config import (
    IMAGE_PROVIDER,
    ATLAS_BASE_URL, ATLAS_IMAGE_MODEL, ATLAS_IMAGE_EDIT_MODEL,
    ATLAS_POLL_INTERVAL_SEC, ATLAS_MAX_POLL_ATTEMPTS,
    SEEDREAM_MODEL, SEEDANCE_BASE_URL,
)

SAFE_PREFIX = "Safe for all ages, family-friendly, no humans, no text. "
MAX_RETRIES = 3


class AtlasImageGenerator:
    """Generates reference images via GPT Image 2 on Atlas Cloud."""

    def __init__(self):
        self.api_key = os.environ["ATLASCLOUD_API_KEY"]
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def generate(self, prompt: str, model: str | None = None) -> str:
        # Allow per-call model override so presets can pick a more permissive
        # image model (e.g. preset-8 drone shorts uses bytedance/seedream-v4.5
        # because GPT Image 2's content filter rejects "drone" prompts).
        chosen_model = model or ATLAS_IMAGE_MODEL
        for attempt in range(MAX_RETRIES):
            current_prompt = prompt if attempt == 0 else f"{SAFE_PREFIX}{prompt}"
            print(f"[ImageGenerator] Atlas image gen ({chosen_model}) — attempt {attempt + 1}/{MAX_RETRIES}...", flush=True)

            try:
                resp = httpx.post(
                    f"{ATLAS_BASE_URL}/model/generateImage",
                    headers=self.headers,
                    json={
                        "model": chosen_model,
                        "prompt": current_prompt,
                        "width": 768,
                        "height": 1344,
                    },
                    timeout=60,
                )
                if resp.status_code == 429:
                    print(f"[ImageGenerator] Rate limited on submit, backing off 60s...", flush=True)
                    time.sleep(60)
                    continue
                if resp.status_code >= 400:
                    raise RuntimeError(f"Atlas image gen failed: HTTP {resp.status_code} — {resp.text[:500]}")

                prediction_id = resp.json()["data"]["id"]
                print(f"[ImageGenerator] Task created: {prediction_id}", flush=True)

                # Poll for result. Atlas surfaces task-side failures (content
                # filter, model errors, fetch failures) as HTTP 400 on the
                # prediction endpoint with the actual cause in the body.
                # Without explicit handling, raise_for_status() throws the body
                # away — same gap that bit us on edit_image earlier.
                for poll in range(ATLAS_MAX_POLL_ATTEMPTS):
                    poll_resp = httpx.get(
                        f"{ATLAS_BASE_URL}/model/prediction/{prediction_id}",
                        headers=self.headers,
                        timeout=30,
                    )
                    if poll_resp.status_code in (429, 500, 502, 503, 504):
                        print(f"[ImageGenerator] HTTP {poll_resp.status_code}, backing off 30s...", flush=True)
                        time.sleep(30)
                        continue
                    if poll_resp.status_code == 400:
                        body = poll_resp.text[:400]
                        # Detect content-filter rejections so the outer retry
                        # loop can re-attempt with the SAFE_PREFIX softening.
                        if "content safety" in body.lower() or "safety policy" in body.lower():
                            print(f"[ImageGenerator] Poll 400 — content safety policy. Body: {body}", flush=True)
                            raise RuntimeError(f"Atlas image content-filter rejection: {body}")
                        print(f"[ImageGenerator] Poll 400 — body: {body}", flush=True)
                        raise RuntimeError(f"Atlas image task failed (HTTP 400): {body}")
                    poll_resp.raise_for_status()
                    data = poll_resp.json()["data"]

                    if data["status"] == "completed":
                        outputs = data.get("outputs", [])
                        if outputs:
                            url = outputs[0]
                            print(f"[ImageGenerator] Reference image generated: {url[:80]}...", flush=True)
                            return url
                        raise RuntimeError(f"Atlas image completed but no outputs: {data}")
                    if data["status"] == "failed":
                        error = data.get("error", "unknown")
                        if "content" in str(error).lower() or "safety" in str(error).lower():
                            print(f"[ImageGenerator] Content filter triggered, retrying...", flush=True)
                            break  # break inner poll loop, retry with safe prefix
                        raise RuntimeError(f"Atlas image failed: {error}")
                    time.sleep(2)  # Atlas recommends 2s for image polling
                else:
                    raise TimeoutError(f"Atlas image timed out after {ATLAS_MAX_POLL_ATTEMPTS * ATLAS_POLL_INTERVAL_SEC}s")

            except (RuntimeError, TimeoutError):
                if attempt == MAX_RETRIES - 1:
                    raise
                continue

        raise RuntimeError(f"Failed to generate reference image after {MAX_RETRIES} attempts.")

    def edit_image(self, base_image_url: str, prompt: str) -> str:
        """Generate a new image using GPT Image 2 Edit, anchored to a base
        image. Used for per-shot storyboards: the locked character reference
        is the base, the shot's scene description is the prompt, and the
        output preserves the character's identity while showing them in the
        shot-appropriate setting/pose.

        Atlas Cloud's image edit endpoint expects the base image to be a
        publicly-accessible URL (not a file upload).
        """
        for attempt in range(MAX_RETRIES):
            print(f"[ImageGenerator] GPT Image 2 Edit — attempt {attempt + 1}/{MAX_RETRIES} — base: {base_image_url}", flush=True)

            try:
                resp = httpx.post(
                    f"{ATLAS_BASE_URL}/model/generateImage",
                    headers=self.headers,
                    json={
                        "model": ATLAS_IMAGE_EDIT_MODEL,
                        "prompt": prompt,
                        "image": base_image_url,
                        "width": 768,
                        "height": 1344,
                    },
                    timeout=60,
                )
                if resp.status_code == 429:
                    print(f"[ImageGenerator] Rate limited on edit submit, backing off 60s...", flush=True)
                    time.sleep(60)
                    continue
                if resp.status_code >= 400:
                    raise RuntimeError(f"Atlas image edit failed: HTTP {resp.status_code} — {resp.text[:500]}")

                prediction_id = resp.json()["data"]["id"]
                print(f"[ImageGenerator] Edit task created: {prediction_id}", flush=True)

                # gpt-image-2/edit typically takes 90-120s end-to-end. Atlas's
                # prediction endpoint occasionally returns a transient 400 mid-flight
                # (gateway race, not a real validation error since we just got a
                # prediction id back). Treat up to 3 consecutive 400s as retryable.
                consecutive_400 = 0
                for poll in range(ATLAS_MAX_POLL_ATTEMPTS):
                    poll_resp = httpx.get(
                        f"{ATLAS_BASE_URL}/model/prediction/{prediction_id}",
                        headers=self.headers,
                        timeout=30,
                    )
                    if poll_resp.status_code in (429, 500, 502, 503, 504):
                        print(f"[ImageGenerator] Edit poll HTTP {poll_resp.status_code}, backing off 30s...", flush=True)
                        time.sleep(30)
                        continue
                    if poll_resp.status_code == 400:
                        consecutive_400 += 1
                        print(f"[ImageGenerator] Edit poll HTTP 400 (#{consecutive_400}/3) — body: {poll_resp.text[:300]}", flush=True)
                        if consecutive_400 >= 3:
                            raise RuntimeError(f"Atlas image edit returned 400 three times in a row: {poll_resp.text[:300]}")
                        time.sleep(5)
                        continue
                    poll_resp.raise_for_status()
                    consecutive_400 = 0
                    data = poll_resp.json()["data"]
                    if data["status"] == "completed":
                        outputs = data.get("outputs", [])
                        if outputs:
                            url = outputs[0]
                            print(f"[ImageGenerator] Edit completed: {url[:80]}...", flush=True)
                            return url
                        raise RuntimeError(f"Edit completed but no outputs: {data}")
                    if data["status"] == "failed":
                        error = data.get("error", "unknown")
                        raise RuntimeError(f"Atlas image edit task failed: {error}")
                    time.sleep(3)  # Edits run ~100s; 3s cadence keeps load light
                else:
                    raise TimeoutError(f"Edit polling timed out after {ATLAS_MAX_POLL_ATTEMPTS} attempts (~{ATLAS_MAX_POLL_ATTEMPTS * 3}s)")

            except (RuntimeError, TimeoutError, httpx.HTTPStatusError) as exc:
                print(f"[ImageGenerator] Edit attempt {attempt + 1} failed: {exc}", flush=True)
                if attempt == MAX_RETRIES - 1:
                    raise
                continue

        raise RuntimeError(f"Failed to edit image after {MAX_RETRIES} attempts.")


class SeedreamImageGenerator:
    """Generates reference images via Seedream on BytePlus ModelArk."""

    def __init__(self):
        from byteplussdkarkruntime import Ark
        self.client = Ark(
            base_url=SEEDANCE_BASE_URL,
            api_key=os.environ["ARK_API_KEY"],
        )

    def generate(self, prompt: str) -> str:
        for attempt in range(MAX_RETRIES):
            current_prompt = prompt if attempt == 0 else f"{SAFE_PREFIX}{prompt}"
            print(f"[ImageGenerator] Seedream — attempt {attempt + 1}/{MAX_RETRIES}...", flush=True)

            try:
                result = self.client.images.generate(
                    model=SEEDREAM_MODEL,
                    prompt=current_prompt,
                    size="2K",
                    response_format="url",
                    watermark=False,
                )
                url = result.data[0].url
                print(f"[ImageGenerator] Reference image generated: {url[:80]}...", flush=True)
                return url
            except Exception as exc:
                if "SensitiveContent" in str(exc):
                    print(f"[ImageGenerator] Content filter triggered, retrying...", flush=True)
                    continue
                raise

        raise RuntimeError(
            f"Failed to generate reference image after {MAX_RETRIES} attempts due to content filter."
        )


def create_image_generator():
    if IMAGE_PROVIDER == "atlas":
        print("[ImageGenerator] Using Atlas Cloud — GPT Image 2", flush=True)
        return AtlasImageGenerator()
    print("[ImageGenerator] Using BytePlus — Seedream 5.0", flush=True)
    return SeedreamImageGenerator()

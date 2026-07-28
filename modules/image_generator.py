import os

import httpx

from config import (
    IMAGE_PROVIDER,
    ATLAS_IMAGE_MODEL, ATLAS_IMAGE_EDIT_MODEL,
    SEEDREAM_MODEL, SEEDANCE_BASE_URL,
)
from modules.atlas_client import AtlasClient, AtlasError

SAFE_PREFIX = "Safe for all ages, family-friendly, no humans, no text. "
MAX_RETRIES = 3

# Image generation settles in seconds, not minutes — poll far more often than
# video. Edits run ~100s, so a slightly slacker cadence keeps the load light.
IMAGE_POLL_INTERVAL = 2
EDIT_POLL_INTERVAL = 3


class AtlasImageGenerator:
    """Generates reference images via GPT Image 2 on Atlas Cloud.

    The submit/poll/read-outputs protocol lives in AtlasClient. What stays here
    is the part that is genuinely about images: softening a prompt and trying
    again when the content filter refuses it.
    """

    def __init__(self, client: AtlasClient | None = None):
        self._atlas = client or AtlasClient()

    def generate(self, prompt: str, model: str | None = None) -> str:
        # Allow per-call model override so presets can pick a more permissive
        # image model (e.g. preset-8 drone shorts uses bytedance/seedream-v4.5
        # because GPT Image 2's content filter rejects "drone" prompts).
        chosen_model = model or ATLAS_IMAGE_MODEL
        for attempt in range(MAX_RETRIES):
            # Retry 0 uses the prompt as written; later attempts prepend a
            # family-friendly framing to get past a content-filter refusal.
            current_prompt = prompt if attempt == 0 else f"{SAFE_PREFIX}{prompt}"
            print(
                f"[ImageGenerator] Atlas image gen ({chosen_model}) — "
                f"attempt {attempt + 1}/{MAX_RETRIES}...",
                flush=True,
            )
            try:
                outputs = self._atlas.run(
                    "model/generateImage",
                    {
                        "model": chosen_model,
                        "prompt": current_prompt,
                        "width": 768,
                        "height": 1344,
                    },
                    poll_interval=IMAGE_POLL_INTERVAL,
                    label="ImageGenerator",
                )
            except AtlasError as exc:
                print(f"[ImageGenerator] Attempt {attempt + 1} failed: {exc}", flush=True)
                if attempt == MAX_RETRIES - 1:
                    raise
                continue

            url = outputs[0]
            print(f"[ImageGenerator] Reference image generated: {url[:80]}...", flush=True)
            return url

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
            print(
                f"[ImageGenerator] GPT Image 2 Edit — attempt {attempt + 1}/{MAX_RETRIES} "
                f"— base: {base_image_url}",
                flush=True,
            )
            try:
                outputs = self._atlas.run(
                    "model/generateImage",
                    {
                        "model": ATLAS_IMAGE_EDIT_MODEL,
                        "prompt": prompt,
                        "image": base_image_url,
                        "width": 768,
                        "height": 1344,
                    },
                    poll_interval=EDIT_POLL_INTERVAL,
                    label="ImageGenerator-Edit",
                )
            except (AtlasError, httpx.HTTPStatusError) as exc:
                print(f"[ImageGenerator] Edit attempt {attempt + 1} failed: {exc}", flush=True)
                if attempt == MAX_RETRIES - 1:
                    raise
                continue

            url = outputs[0]
            print(f"[ImageGenerator] Edit completed: {url[:80]}...", flush=True)
            return url

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

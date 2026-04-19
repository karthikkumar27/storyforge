import os

from config import SEEDREAM_MODEL, SEEDANCE_BASE_URL

SAFE_PREFIX = "Safe for all ages, family-friendly, no humans, no text. "
MAX_RETRIES = 3


class ReferenceImageGenerator:
    """Generates a character reference image using Seedream for visual consistency."""

    def __init__(self):
        from byteplussdkarkruntime import Ark
        self.client = Ark(
            base_url=SEEDANCE_BASE_URL,
            api_key=os.environ["ARK_API_KEY"],
        )

    def generate(self, prompt: str) -> str:
        """Generate a reference image and return its URL. Retries with safer prompt on content filter."""
        for attempt in range(MAX_RETRIES):
            current_prompt = prompt if attempt == 0 else f"{SAFE_PREFIX}{prompt}"
            print(f"[ImageGenerator] Attempt {attempt + 1}/{MAX_RETRIES}...", flush=True)

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
                    print(f"[ImageGenerator] Content filter triggered, retrying with safer prompt...", flush=True)
                    continue
                raise

        raise RuntimeError(
            f"Failed to generate reference image after {MAX_RETRIES} attempts due to content filter. "
            f"Try adjusting the character_image_prompt in the script generator."
        )

# Chained Reference Frames Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the lead character changing appearance between shots in preset-9 episodes, by giving each shot's storyboard both the locked reference image *and* the previous shot's last frame.

**Architecture:** Storyboards are currently generated as one batch before any video exists. This plan inverts that: `produce()` calls a *supplier* once per shot, so storyboard N can be built from shot N−1's rendered clip. Each storyboard edit takes two base images — the locked reference (identity authority) first, the previous frame (continuity) second — so every storyboard stays exactly one generation from the reference and drift never accumulates.

**Tech Stack:** Python 3.12, pytest, ffmpeg/ffprobe (already a pipeline dependency), Atlas Cloud (`openai/gpt-image-2/edit`, `bytedance/seedance-v1.5-pro/image-to-video-fast`).

**Spec:** `docs/superpowers/specs/2026-08-03-frame-chaining-design.md`

## Global Constraints

- **Behaviour must be byte-identical when the feature is off.** `chain_reference_frames` defaults to `False`. With no supplier passed, `produce()` behaves exactly as it does today.
- **preset-9 only.** Do not enable this for preset-7 — it is a 200-episode series with locked canon (spec §7).
- **Never letterbox a still.** Aspect correction is always centre-crop. Black bars in a first frame become scene content in the generated clip (spec §3.5).
- **No hosted storage.** Local files reach Atlas as base64 data URIs. Both `model/generateImage` and `model/generateVideo` accept them (spec §2).
- **Every failure degrades, none aborts.** Any chaining failure falls back to today's single-base behaviour for that shot (spec §4).
- **Reference image goes first in the base-image list**, previous frame second. Order is the identity-authority signal.
- **Tests run without network.** Follow the existing pattern: inject stubs at constructor seams (`tests/support.py`), never patch module internals.
- Run the full suite with `python3 -m pytest tests -q` (currently 247 passed, 4 skipped).

---

### Task 1: Frame extraction and data-URI encoding

Creates the new module with the two functions that get a frame out of a clip and into a form Atlas accepts.

**Files:**
- Create: `modules/frame_chain.py`
- Create: `tests/modules/test_frame_chain.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `FrameExtractionError(RuntimeError)`
  - `extract_last_frame(clip_path: str, *, offset_sec: float = FRAME_OFFSET_SEC, dest_dir: str | None = None) -> str` — returns a PNG path
  - `to_data_uri(image_path: str, *, max_edge: int = MAX_EDGE_PX) -> str`
  - `fetch_image(url: str, dest_dir: str | None = None) -> str`
  - `_probe_size(path: str) -> tuple[int, int]`
  - `_even(value: int) -> int`
  - Constants `FRAME_OFFSET_SEC = 0.4`, `MAX_EDGE_PX = 768`

- [ ] **Step 1: Write the failing tests**

Create `tests/modules/test_frame_chain.py`:

```python
# tests/modules/test_frame_chain.py
import base64
import os
import subprocess

import pytest

from modules.frame_chain import (
    FrameExtractionError,
    _probe_size,
    extract_last_frame,
    to_data_uri,
)


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    """A real 2-second 180x320 portrait clip. Real ffmpeg, because the offset
    arithmetic and pixel formats are exactly what could go wrong here."""
    path = str(tmp_path_factory.mktemp("clips") / "shot.mp4")
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "testsrc=duration=2:size=180x320:rate=10",
         "-pix_fmt", "yuv420p", path],
        check=True, capture_output=True,
    )
    return path


def test_extracts_a_png_that_exists_and_has_content(clip, tmp_path):
    frame = extract_last_frame(clip, dest_dir=str(tmp_path))

    assert frame.endswith(".png")
    assert os.path.getsize(frame) > 0


def test_extracted_frame_keeps_the_clip_dimensions(clip, tmp_path):
    frame = extract_last_frame(clip, dest_dir=str(tmp_path))

    assert _probe_size(frame) == (180, 320)


def test_extraction_samples_before_the_very_end(clip, tmp_path):
    """The true final frame is often mid-motion-blur or part of a fade, which
    makes a poor anchor. testsrc counts up, so an earlier sample differs."""
    late = extract_last_frame(clip, offset_sec=0.1, dest_dir=str(tmp_path / "late"))
    early = extract_last_frame(clip, offset_sec=1.5, dest_dir=str(tmp_path / "early"))

    assert open(late, "rb").read() != open(early, "rb").read()


def test_a_clip_that_is_not_a_clip_raises(tmp_path):
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(b"not actually video")

    with pytest.raises(FrameExtractionError):
        extract_last_frame(str(broken), dest_dir=str(tmp_path))


def test_a_missing_clip_raises(tmp_path):
    with pytest.raises(FrameExtractionError):
        extract_last_frame(str(tmp_path / "nope.mp4"), dest_dir=str(tmp_path))


def test_data_uri_has_the_shape_atlas_accepts(clip, tmp_path):
    frame = extract_last_frame(clip, dest_dir=str(tmp_path))

    uri = to_data_uri(frame)

    assert uri.startswith("data:image/png;base64,")
    base64.b64decode(uri.split(",", 1)[1])  # raises if not valid base64


def test_a_small_frame_is_not_upscaled(clip, tmp_path):
    frame = extract_last_frame(clip, dest_dir=str(tmp_path))

    uri = to_data_uri(frame, max_edge=768)
    decoded = base64.b64decode(uri.split(",", 1)[1])
    out = tmp_path / "roundtrip.png"
    out.write_bytes(decoded)

    assert _probe_size(str(out)) == (180, 320)


def test_a_large_frame_is_downscaled_to_the_max_edge(clip, tmp_path):
    frame = extract_last_frame(clip, dest_dir=str(tmp_path))

    uri = to_data_uri(frame, max_edge=64)
    decoded = base64.b64decode(uri.split(",", 1)[1])
    out = tmp_path / "small.png"
    out.write_bytes(decoded)

    width, height = _probe_size(str(out))
    assert max(width, height) == 64
    assert width % 2 == 0 and height % 2 == 0


def test_fetch_image_writes_what_the_http_client_streamed(tmp_path):
    from modules.frame_chain import fetch_image

    class StubResponse:
        def raise_for_status(self): pass
        def iter_bytes(self, chunk_size=65536): yield b"PNGDATA"
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class StubHttp:
        def stream(self, method, url, timeout=None): return StubResponse()

    path = fetch_image("https://cdn/sb.png", dest_dir=str(tmp_path), http=StubHttp())

    assert open(path, "rb").read() == b"PNGDATA"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/modules/test_frame_chain.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'modules.frame_chain'`

- [ ] **Step 3: Write the implementation**

Create `modules/frame_chain.py`:

```python
"""Chained reference frames.

A Storyboard fixes who and where a character is at the START of a shot. What it
cannot see is what the PREVIOUS shot actually rendered -- so shot 4 is free to
re-decide the character's eye colour within the reference image's tolerance,
which is exactly how one episode ends up with two different leads.

This module carries a still forward: the last clean frame of shot N-1 becomes a
second base image for shot N's Storyboard, alongside the locked Reference Image.

Deliberately NOT the last frame: a Seedance clip drifts furthest from the
reference at its end, and the true final frame is often mid-motion-blur or part
of a fade. Sampling slightly earlier gets a settled, on-model frame.

Nothing here is hosted. Atlas accepts base64 data URIs on both the image-edit
and video endpoints, so a frame goes local file -> data URI -> API without ever
touching cloud storage.
"""

from __future__ import annotations

import base64
import os
import subprocess
import tempfile

# How far before the end to sample. Far enough to clear motion blur and fades,
# close enough that it is still the shot's ending state.
FRAME_OFFSET_SEC = 0.4

# Longest edge of the encoded frame. 768px keeps the base64 payload near 300KB,
# a size proven to work against the Atlas edit endpoint.
MAX_EDGE_PX = 768


class FrameExtractionError(RuntimeError):
    """The clip could not yield a usable still."""


def _probe_size(path: str) -> tuple[int, int]:
    """Return (width, height) of the first video stream in path."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", str(path)],
        check=True, capture_output=True, text=True,
    )
    width, height = result.stdout.strip().split("\n")[0].split("x")[:2]
    return int(width), int(height)


def _even(value: int) -> int:
    """Round down to an even number -- yuv420p requires even dimensions."""
    return max(2, value - (value % 2))


def extract_last_frame(
    clip_path: str,
    *,
    offset_sec: float = FRAME_OFFSET_SEC,
    dest_dir: str | None = None,
) -> str:
    """Write the clip's last clean frame as a PNG and return its path.

    Raises FrameExtractionError rather than returning a partial result, so the
    caller can fall back to a single-base Storyboard for this one shot.
    """
    dest_dir = dest_dir or tempfile.mkdtemp(prefix="frame_chain_")
    os.makedirs(dest_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(clip_path))[0]
    dest = os.path.join(dest_dir, f"{stem}_last.png")

    result = subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-sseof", f"-{offset_sec}",
         "-i", str(clip_path),
         "-frames:v", "1", "-update", "1", dest],
        capture_output=True,
    )
    if result.returncode != 0 or not os.path.exists(dest) or os.path.getsize(dest) == 0:
        stderr = result.stderr.decode(errors="replace")[-300:] if result.stderr else ""
        raise FrameExtractionError(
            f"could not extract a frame from {clip_path}: {stderr}"
        )
    return dest


def to_data_uri(image_path: str, *, max_edge: int = MAX_EDGE_PX) -> str:
    """Return the image as a base64 data URI, downscaling only if oversized."""
    width, height = _probe_size(image_path)
    source = image_path

    longest = max(width, height)
    if longest > max_edge:
        # The longest edge lands on max_edge exactly; the other scales to match.
        if width >= height:
            target_w = _even(max_edge)
            target_h = _even(round(height * max_edge / longest))
        else:
            target_h = _even(max_edge)
            target_w = _even(round(width * max_edge / longest))
        source = os.path.join(
            os.path.dirname(image_path), f"scaled_{os.path.basename(image_path)}"
        )
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(image_path),
             "-vf", f"scale={target_w}:{target_h}", source],
            check=True, capture_output=True,
        )

    with open(source, "rb") as handle:
        encoded = base64.b64encode(handle.read()).decode()
    return f"data:image/png;base64,{encoded}"


def fetch_image(url: str, dest_dir: str | None = None, *, http: Any = httpx) -> str:
    """Download an image URL to a local file and return its path.

    Storyboards come back from Atlas as hosted URLs, but their aspect ratio has
    to be checked and corrected locally, which means having the bytes.
    """
    dest_dir = dest_dir or tempfile.mkdtemp(prefix="frame_chain_")
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, "storyboard.png")
    with http.stream("GET", url, timeout=120) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as handle:
            for chunk in resp.iter_bytes(chunk_size=65536):
                handle.write(chunk)
    return dest
```

Also add to the imports at the top of `modules/frame_chain.py`:

```python
from typing import Any

import httpx
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/modules/test_frame_chain.py -v`
Expected: all PASS

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest tests -q`
Expected: 247 passed + the new tests, 4 skipped, no failures

- [ ] **Step 6: Commit**

```bash
git add modules/frame_chain.py tests/modules/test_frame_chain.py
git commit -m "feat: extract a clip's last clean frame as a data URI

The frame that carries character identity forward between shots.
Sampled 0.4s before the end -- the true final frame is often
mid-motion-blur or part of a fade, and a clip drifts furthest from
its reference at the end.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Centre-crop to 9:16

A two-image edit silently returns 1536×1024 landscape (spec §2). Every storyboard is corrected locally before it becomes a first frame.

**Files:**
- Modify: `modules/frame_chain.py`
- Modify: `tests/modules/test_frame_chain.py`

**Interfaces:**
- Consumes: `_probe_size`, `_even`, `fetch_image`, `to_data_uri` from Task 1.
- Produces:
  - `normalise_portrait(image_path: str, *, ratio: float = PORTRAIT_RATIO) -> str`
  - `portrait_anchor(image_url: str, *, fetch: Callable[..., str] = fetch_image) -> str` — the function callers actually use: returns the URL untouched when it is already 9:16, otherwise downloads, centre-crops, and returns a data URI
  - constant `PORTRAIT_RATIO = 9 / 16`

- [ ] **Step 1: Write the failing tests**

Append to `tests/modules/test_frame_chain.py`:

```python
from modules.frame_chain import PORTRAIT_RATIO, normalise_portrait


def _solid(path, width, height):
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", f"color=c=red:s={width}x{height}",
         "-frames:v", "1", "-update", "1", str(path)],
        check=True, capture_output=True,
    )
    return str(path)


def test_a_landscape_still_is_cropped_to_portrait(tmp_path):
    wide = _solid(tmp_path / "wide.png", 1536, 1024)

    result = normalise_portrait(wide)

    width, height = _probe_size(result)
    assert height > width
    assert abs((width / height) - PORTRAIT_RATIO) < 0.02


def test_cropping_never_adds_bars(tmp_path):
    """A letterboxed still would carry black bars into the first frame, and
    Seedance would treat them as scene content for the whole clip."""
    wide = _solid(tmp_path / "wide.png", 1536, 1024)

    result = normalise_portrait(wide)

    width, height = _probe_size(result)
    assert width <= 1536 and height <= 1024   # cropped, never padded


def test_an_already_portrait_still_is_returned_untouched(tmp_path):
    tall = _solid(tmp_path / "tall.png", 768, 1344)

    assert normalise_portrait(tall) == tall


def test_a_too_tall_still_is_cropped_on_height(tmp_path):
    skinny = _solid(tmp_path / "skinny.png", 400, 1600)

    result = normalise_portrait(skinny)

    width, height = _probe_size(result)
    assert abs((width / height) - PORTRAIT_RATIO) < 0.02
    assert width == 400


def test_cropped_dimensions_are_even(tmp_path):
    """yuv420p downstream requires even dimensions."""
    odd = _solid(tmp_path / "odd.png", 1001, 777)

    width, height = _probe_size(normalise_portrait(odd))

    assert width % 2 == 0 and height % 2 == 0


# -- portrait_anchor: what callers actually use -------------------------------

def test_an_already_portrait_url_is_passed_through_untouched(tmp_path):
    """No download, no re-encode, no 300KB inline payload — the hosted URL is
    already exactly what Seedance needs."""
    from modules.frame_chain import portrait_anchor
    calls = []

    def fetch(url, dest_dir=None):
        calls.append(url)
        return _solid(tmp_path / "tall.png", 768, 1344)

    result = portrait_anchor("https://cdn/sb.png", fetch=fetch)

    assert result == "https://cdn/sb.png"
    assert len(calls) == 1   # fetched once to measure, then discarded


def test_a_landscape_url_comes_back_as_a_cropped_data_uri(tmp_path):
    from modules.frame_chain import portrait_anchor

    def fetch(url, dest_dir=None):
        return _solid(tmp_path / "wide.png", 1536, 1024)

    result = portrait_anchor("https://cdn/sb.png", fetch=fetch)

    assert result.startswith("data:image/png;base64,")


def test_a_fetch_failure_falls_back_to_the_original_url(tmp_path):
    """Aspect correction is an enhancement. If it cannot run, the un-corrected
    URL is still better than no first frame at all."""
    from modules.frame_chain import portrait_anchor

    def fetch(url, dest_dir=None):
        raise OSError("connection reset")

    assert portrait_anchor("https://cdn/sb.png", fetch=fetch) == "https://cdn/sb.png"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/modules/test_frame_chain.py -k portrait -v`
Expected: FAIL — `ImportError: cannot import name 'normalise_portrait'`

- [ ] **Step 3: Write the implementation**

Add to `modules/frame_chain.py`, after `MAX_EDGE_PX`:

```python
# Target shape for anything handed to Seedance as a first frame.
PORTRAIT_RATIO = 9 / 16
```

And append this function:

```python
def normalise_portrait(image_path: str, *, ratio: float = PORTRAIT_RATIO) -> str:
    """Centre-crop the image to 9:16 and return the corrected path.

    Returns the input path unchanged when it is already the right shape.

    CROP, never letterbox. This still becomes a Seedance first frame, and
    Seedance reads black bars as scene content -- it would propagate them
    through the whole generated clip. Losing edge detail is the cheaper cost.
    """
    width, height = _probe_size(image_path)
    if abs((width / height) - ratio) < 0.01:
        return image_path

    if (width / height) > ratio:
        crop_w, crop_h = _even(round(height * ratio)), _even(height)
    else:
        crop_w, crop_h = _even(width), _even(round(width / ratio))

    dest = os.path.join(
        os.path.dirname(image_path), f"portrait_{os.path.basename(image_path)}"
    )
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(image_path),
         "-vf", f"crop={crop_w}:{crop_h}", dest],
        check=True, capture_output=True,
    )
    print(
        f"[FrameChain] Corrected {width}x{height} -> {crop_w}x{crop_h} (centre-crop)",
        flush=True,
    )
    return dest


def portrait_anchor(image_url: str, *, fetch: Any = None) -> str:
    """Return something Seedance can use as a 9:16 first frame.

    A two-image edit silently returns landscape regardless of the width/height
    requested, so every storyboard is measured rather than trusted.

    Already 9:16 -> the hosted URL is returned untouched, which keeps the video
    request small. Anything else -> centre-cropped locally and returned as a
    data URI, which model/generateVideo accepts.

    Never raises. Aspect correction is an enhancement; an uncorrected first
    frame beats no first frame.
    """
    fetch = fetch or fetch_image
    try:
        local = fetch(image_url)
        corrected = normalise_portrait(local)
        if corrected == local:
            return image_url
        return to_data_uri(corrected)
    except Exception as exc:
        print(
            f"[FrameChain] Could not verify aspect for {image_url[:60]}... "
            f"({exc}) — using it as-is",
            flush=True,
        )
        return image_url
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/modules/test_frame_chain.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add modules/frame_chain.py tests/modules/test_frame_chain.py
git commit -m "feat: centre-crop stills to 9:16 before they become first frames

A two-image edit silently returns 1536x1024 landscape regardless of
the width/height asked for, so the pipeline corrects locally rather
than trusting the API. Crop, never letterbox -- Seedance reads black
bars as scene content and carries them through the whole clip.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `edit_image` accepts multiple base images

**Files:**
- Modify: `modules/image_generator.py:70-109`
- Modify: `tests/modules/test_image_generator.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `AtlasImageGenerator.edit_image(base_image_url: str | list[str], prompt: str) -> str` — a list is passed through to the Atlas `image` field verbatim, preserving order.

- [ ] **Step 1: Write the failing tests**

Append to `tests/modules/test_image_generator.py`:

```python
def test_edit_accepts_a_list_of_base_images_in_order():
    """Chained storyboards pass [locked_reference, previous_frame]. Order is the
    identity-authority signal, so it must survive to the request body."""
    from modules.image_generator import AtlasImageGenerator
    from tests.support import StubAtlasClient
    client = StubAtlasClient(outputs=["https://cdn/sb.png"])

    AtlasImageGenerator(client).edit_image(
        ["https://cdn/ref.png", "data:image/png;base64,AAAA"], "a rooftop"
    )

    assert client.calls[0]["body"]["image"] == [
        "https://cdn/ref.png", "data:image/png;base64,AAAA",
    ]


def test_edit_still_accepts_a_single_base_image():
    from modules.image_generator import AtlasImageGenerator
    from tests.support import StubAtlasClient
    client = StubAtlasClient(outputs=["https://cdn/sb.png"])

    AtlasImageGenerator(client).edit_image("https://cdn/ref.png", "a rooftop")

    assert client.calls[0]["body"]["image"] == "https://cdn/ref.png"


def test_edit_logs_a_readable_base_for_a_data_uri():
    """A base64 data URI is ~300KB; logging it raw floods the pipeline output."""
    from modules.image_generator import AtlasImageGenerator
    from tests.support import StubAtlasClient
    import io, contextlib
    client = StubAtlasClient(outputs=["https://cdn/sb.png"])

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        AtlasImageGenerator(client).edit_image(
            ["https://cdn/ref.png", "data:image/png;base64," + "A" * 5000], "x"
        )

    assert len(buffer.getvalue()) < 2000
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/modules/test_image_generator.py -k "list_of_base or data_uri" -v`
Expected: FAIL — the list is logged in full and/or the assertion on `body["image"]` fails

- [ ] **Step 3: Write the implementation**

Replace `edit_image` in `modules/image_generator.py` (lines 70-109) with:

```python
    def edit_image(self, base_image_url: str | list[str], prompt: str) -> str:
        """Generate a new image using GPT Image 2 Edit, anchored to one or more
        base images.

        Single base -- the locked character reference. Two bases -- the locked
        reference FIRST (the authority on identity) and the previous shot's last
        frame SECOND (continuity of lighting, wardrobe and staging). Order is
        the signal; the prompt tells the model which is which.

        A base may be a public URL or a base64 data URI; Atlas accepts both.
        """
        for attempt in range(MAX_RETRIES):
            print(
                f"[ImageGenerator] GPT Image 2 Edit — attempt {attempt + 1}/{MAX_RETRIES} "
                f"— base: {_describe_bases(base_image_url)}",
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
```

Add this module-level helper above `class AtlasImageGenerator`:

```python
def _describe_bases(base: str | list[str]) -> str:
    """A short, loggable description of edit bases.

    A base64 data URI runs to hundreds of KB. Printed raw, one storyboard
    would bury the whole pipeline log.
    """
    items = base if isinstance(base, list) else [base]
    parts = []
    for item in items:
        if item.startswith("data:"):
            parts.append(f"<inline {len(item) // 1024}KB>")
        else:
            parts.append(item[:80])
    return " + ".join(parts)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/modules/test_image_generator.py -v`
Expected: all PASS, including the pre-existing edit tests

- [ ] **Step 5: Commit**

```bash
git add modules/image_generator.py tests/modules/test_image_generator.py
git commit -m "feat: edit_image accepts multiple base images

Chained storyboards pass [locked_reference, previous_frame]. Order
carries meaning: the reference is the authority on identity. Data
URI bases are summarised in logs rather than printed -- one is
~300KB and would bury the pipeline output.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Chained storyboard supplier

**Files:**
- Modify: `modules/storyboard.py`
- Modify: `tests/modules/test_storyboard.py`

**Interfaces:**
- Consumes: `extract_last_frame`, `to_data_uri`, `FrameExtractionError` (Task 1), `portrait_anchor` (Task 2); `edit_image(str | list[str], str)` (Task 3).
- Produces:
  - `build_continuity_prompt(shot_prompt: str, style: str) -> str`
  - `class ChainedStoryboards` with `__init__(self, reference_image_url: str, *, style: str, generator: ImageEditor | None = None, log: Callable[[str], None] | None = None)` and `frame_for(self, index: int, shot_prompt: str, previous_clip: str | None) -> str | None`

`frame_for` takes the previous shot's **clip path**, not a frame — extraction is this class's job, so the video producer never learns about ffmpeg.

- [ ] **Step 1: Write the failing tests**

Append to `tests/modules/test_storyboard.py`:

```python
from modules.storyboard import ChainedStoryboards, build_continuity_prompt


class ListEditor:
    """StubEditor's sibling: accepts a list-or-string base, records both."""

    def __init__(self, results=None):
        self.results = list(results or [])
        self.calls = []

    def edit_image(self, base_image_url, prompt):
        self.calls.append((base_image_url, prompt))
        if self.results:
            result = self.results.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        return f"https://cdn/chained{len(self.calls)}.png"


# -- the continuity prompt ----------------------------------------------------

def test_continuity_prompt_names_which_base_owns_identity():
    """Probing showed text wins over images when they conflict, so the
    instruction has to be explicit about precedence."""
    prompt = build_continuity_prompt("Kenji lunges forward", "anime cel-shaded")

    assert "first image" in prompt.lower()
    assert "second image" in prompt.lower()
    assert "Scene: Kenji lunges forward" in prompt


def test_continuity_prompt_still_asks_for_a_vertical_first_frame():
    prompt = build_continuity_prompt("Kenji lunges forward", "anime")

    assert "9:16" in prompt
    assert "START of the action" in prompt
    assert "no motion blur" in prompt


# -- the supplier -------------------------------------------------------------

def test_first_shot_uses_the_reference_alone():
    editor = ListEditor()
    supplier = ChainedStoryboards(
        "https://cdn/ref.png", style="anime", generator=editor, log=lambda _: None,
    )

    supplier.frame_for(0, "the bridge at night", None)

    base, _ = editor.calls[0]
    assert base == "https://cdn/ref.png"


def test_later_shots_pass_reference_first_and_previous_frame_second(monkeypatch, tmp_path):
    clip = tmp_path / "shot_00.mp4"
    clip.write_bytes(b"fake")
    monkeypatch.setattr(
        "modules.storyboard.extract_last_frame", lambda path, **kw: str(clip)
    )
    monkeypatch.setattr(
        "modules.storyboard.to_data_uri", lambda path, **kw: "data:image/png;base64,ZZZ"
    )
    editor = ListEditor()
    supplier = ChainedStoryboards(
        "https://cdn/ref.png", style="anime", generator=editor, log=lambda _: None,
    )

    supplier.frame_for(1, "Kenji lunges", str(clip))

    base, _ = editor.calls[0]
    assert base == ["https://cdn/ref.png", "data:image/png;base64,ZZZ"]


def test_extraction_failure_falls_back_to_the_reference_alone(monkeypatch, tmp_path):
    """One shot loses continuity; the episode continues."""
    from modules.frame_chain import FrameExtractionError
    clip = tmp_path / "shot_00.mp4"
    clip.write_bytes(b"fake")

    def boom(path, **kw):
        raise FrameExtractionError("corrupt clip")

    monkeypatch.setattr("modules.storyboard.extract_last_frame", boom)
    editor = ListEditor()
    supplier = ChainedStoryboards(
        "https://cdn/ref.png", style="anime", generator=editor, log=lambda _: None,
    )

    result = supplier.frame_for(1, "Kenji lunges", str(clip))

    assert editor.calls[0][0] == "https://cdn/ref.png"
    assert result is not None


def test_an_edit_failure_returns_none_rather_than_raising():
    """None tells the video producer to fall back to the shared reference."""
    editor = ListEditor([RuntimeError("content filter")])
    supplier = ChainedStoryboards(
        "https://cdn/ref.png", style="anime", generator=editor, log=lambda _: None,
    )

    assert supplier.frame_for(0, "the bridge", None) is None


def test_character_absent_shots_still_use_the_style_only_prompt():
    editor = ListEditor()
    supplier = ChainedStoryboards(
        "https://cdn/ref.png", style="anime", generator=editor, log=lambda _: None,
    )

    supplier.frame_for(0, "POV shot — the altar cracks", None)

    _, prompt = editor.calls[0]
    assert "STYLE anchor only" in prompt


def test_the_result_is_aspect_checked_before_it_is_returned(monkeypatch):
    """A two-image edit silently returns landscape. Every storyboard goes
    through portrait_anchor before it can become a first frame."""
    seen = []
    monkeypatch.setattr(
        "modules.storyboard.portrait_anchor",
        lambda url, **kw: seen.append(url) or "data:image/png;base64,CROPPED",
    )
    editor = ListEditor(["https://cdn/wide.png"])
    supplier = ChainedStoryboards(
        "https://cdn/ref.png", style="anime", generator=editor, log=lambda _: None,
    )

    result = supplier.frame_for(0, "the bridge", None)

    assert seen == ["https://cdn/wide.png"]
    assert result == "data:image/png;base64,CROPPED"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/modules/test_storyboard.py -k "continuity or chained or shot_uses or later_shots or extraction_failure or edit_failure" -v`
Expected: FAIL — `ImportError: cannot import name 'ChainedStoryboards'`

- [ ] **Step 3: Write the implementation**

Add to the imports at the top of `modules/storyboard.py`:

```python
from modules.frame_chain import (
    FrameExtractionError,
    extract_last_frame,
    portrait_anchor,
    to_data_uri,
)
```

Widen the `ImageEditor` Protocol at `modules/storyboard.py:36` so the seam
matches what `ChainedStoryboards` actually sends through it. Task 3 widened the
implementation; the Protocol that describes it must agree, or the declared
contract for this module's one collaborator is a lie:

```python
    def edit_image(self, base_image_url: str | list[str], prompt: str) -> str:
        ...
```

Append to `modules/storyboard.py`:

```python
def build_continuity_prompt(shot_prompt: str, style: str) -> str:
    """The instruction for a two-base edit.

    Probing showed the model resolves conflicts toward the TEXT, so precedence
    between the two images has to be stated rather than implied.
    """
    if character_is_absent(shot_prompt):
        return (
            f"You are given two images. The FIRST is a STYLE anchor — preserve the "
            f"{style} illustration style, colour palette and world from it. The SECOND "
            f"is the final moment of the previous shot — match its lighting, weather "
            f"and time of day so the two shots feel continuous. The main character "
            f"should NOT be in frame for this shot (it is a POV, wide-exterior, or "
            f"environmental shot). Render the scene as a 9:16 vertical still frame at "
            f"the START of the action, no motion blur. Scene: {shot_prompt}"
        )
    return (
        f"You are given two images. The FIRST image is the authority on WHO the "
        f"character is — preserve their face, hair, eye colour, outfit and the {style} "
        f"style from it exactly. The SECOND image is the final moment of the previous "
        f"shot — use it for continuity of lighting, weather, wardrobe state and where "
        f"other characters are standing, and keep any second character looking exactly "
        f"as they do there. Where the two images disagree about the main character's "
        f"appearance, the FIRST image wins. Render this scene as a 9:16 vertical still "
        f"frame at the START of the action, no motion blur. Scene: {shot_prompt}"
    )


class ChainedStoryboards:
    """A StoryboardSupplier that carries the previous shot's last frame forward.

    Shot 1 is edited from the Reference Image alone. Every shot after it is
    edited from [Reference Image, previous shot's last frame] -- so identity is
    re-anchored to the reference on every shot rather than drifting forward,
    while continuity still flows from what actually rendered.

    Extraction lives here rather than in the video producer so the producer
    never learns about ffmpeg or data URIs: it hands over a clip path and gets
    back a first frame.
    """

    def __init__(
        self,
        reference_image_url: str,
        *,
        style: str,
        generator: ImageEditor | None = None,
        log: Callable[[str], None] | None = None,
    ):
        if generator is None:
            from modules.image_generator import AtlasImageGenerator
            generator = AtlasImageGenerator()
        self._reference = reference_image_url
        self._style = style
        self._generator = generator
        self._log = log or (lambda message: print(message, flush=True))

    def frame_for(
        self, index: int, shot_prompt: str, previous_clip: str | None
    ) -> str | None:
        """The first-frame still for one shot, or None to fall back."""
        bases: str | list[str] = self._reference
        prompt = build_edit_prompt(shot_prompt, self._style)

        if previous_clip:
            try:
                frame = extract_last_frame(previous_clip)
                bases = [self._reference, to_data_uri(frame)]
                prompt = build_continuity_prompt(shot_prompt, self._style)
                self._log(f"[Storyboard]   shot {index + 1} chained to the previous frame")
            # Broad on purpose: extract_last_frame raises FrameExtractionError,
            # but to_data_uri shells out to ffmpeg with check=True, and
            # CalledProcessError is NOT an OSError. Anything that goes wrong
            # here costs continuity for one shot, never the episode.
            except Exception as exc:
                self._log(
                    f"[Storyboard]   shot {index + 1} could not chain ({exc}) "
                    f"— using the locked reference alone"
                )

        try:
            url = self._generator.edit_image(bases, prompt)
        except Exception as exc:
            self._log(
                f"[Storyboard]   shot {index + 1} FAILED ({exc}) "
                f"— falling back to the locked reference"
            )
            return None

        # Measured, not trusted: a two-base edit silently returns landscape.
        anchor = portrait_anchor(url)
        self._log(f"[Storyboard]   shot {index + 1} ✓")
        return anchor
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/modules/test_storyboard.py -v`
Expected: all PASS, including every pre-existing `build_storyboards` test

- [ ] **Step 5: Commit**

```bash
git add modules/storyboard.py tests/modules/test_storyboard.py
git commit -m "feat: ChainedStoryboards supplier carries the previous frame forward

Shot 1 edits from the reference alone; every later shot edits from
[reference, previous last frame]. Identity is re-anchored to the
reference each shot rather than drifting forward, while continuity
flows from what actually rendered.

The continuity prompt states image precedence explicitly -- probing
showed the model resolves conflicts toward the text.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `produce()` calls a supplier per shot

The control-flow inversion. Storyboard generation moves inside the shot loop so storyboard N can see shot N−1.

**Files:**
- Modify: `modules/video_producer.py:140-204`
- Modify: `tests/modules/test_video_producer.py`

**Interfaces:**
- Consumes: `ChainedStoryboards.frame_for(index, shot_prompt, previous_clip)` (Task 4). The producer stays ignorant of ffmpeg, data URIs and aspect ratios — it hands over a clip path and receives a first-frame reference.
- Produces: `BaseVideoProducer.produce(shots, reference_image_url=None, storyboard_urls=None, storyboard_supplier=None) -> str`, and the `StoryboardSupplier` Protocol.

- [ ] **Step 1: Write the failing tests**

Append to `tests/modules/test_video_producer.py`:

```python
from modules.video_producer import BaseVideoProducer


class RecordingProducer(BaseVideoProducer):
    """A BaseVideoProducer with the network removed. Records every anchor it
    was handed, which is the whole point of these tests."""

    def __init__(self):
        self.submitted = []

    def _submit_shot(self, prompt, reference_image_url=None):
        self.submitted.append((prompt, reference_image_url))
        return f"task_{len(self.submitted)}"

    def _poll_shot(self, task_id):
        return f"https://cdn/{task_id}.mp4"


class StubSupplier:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.calls = []

    def frame_for(self, index, shot_prompt, previous_clip):
        self.calls.append((index, shot_prompt, previous_clip))
        if self.results:
            return self.results.pop(0)
        return f"https://cdn/sb{index}.png"


def _run(producer, **kwargs):
    """Drive produce() with downloads and stitching stubbed out."""
    from unittest.mock import patch
    with patch.object(producer, "_download_clip") as download, \
         patch.object(producer, "_stitch"), \
         patch.object(producer, "_get_title_card", return_value=None), \
         patch.object(producer, "_get_end_card", return_value=None):
        download.side_effect = lambda url, path: open(path, "wb").write(b"clip")
        return producer.produce(**kwargs)


def test_supplier_gets_none_for_the_first_shot_and_a_clip_after():
    producer = RecordingProducer()
    supplier = StubSupplier()

    _run(producer, shots=["one", "two", "three"], storyboard_supplier=supplier)

    assert supplier.calls[0][2] is None
    assert supplier.calls[1][2].endswith("shot_00.mp4")
    assert supplier.calls[2][2].endswith("shot_01.mp4")


def test_supplier_results_become_the_shot_reference_images():
    producer = RecordingProducer()
    supplier = StubSupplier(["https://cdn/a.png", "https://cdn/b.png"])

    _run(producer, shots=["one", "two"], storyboard_supplier=supplier)

    assert [ref for _, ref in producer.submitted] == [
        "https://cdn/a.png", "https://cdn/b.png",
    ]


def test_a_none_from_the_supplier_falls_back_to_the_shared_reference():
    producer = RecordingProducer()
    supplier = StubSupplier([None, "https://cdn/b.png"])

    _run(
        producer, shots=["one", "two"],
        reference_image_url="https://cdn/ref.png",
        storyboard_supplier=supplier,
    )

    assert producer.submitted[0][1] == "https://cdn/ref.png"


def test_without_a_supplier_behaviour_is_unchanged():
    """The pre-existing batch path must still work byte-identically."""
    producer = RecordingProducer()

    _run(
        producer, shots=["one", "two"],
        reference_image_url="https://cdn/ref.png",
        storyboard_urls=["https://cdn/sb0.png", None],
    )

    assert [ref for _, ref in producer.submitted] == [
        "https://cdn/sb0.png", "https://cdn/ref.png",
    ]


def test_a_supplier_that_raises_does_not_kill_the_episode():
    producer = RecordingProducer()

    class Exploding:
        def frame_for(self, index, shot_prompt, previous_clip):
            raise RuntimeError("atlas down")

    _run(
        producer, shots=["one"],
        reference_image_url="https://cdn/ref.png",
        storyboard_supplier=Exploding(),
    )

    assert producer.submitted[0][1] == "https://cdn/ref.png"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/modules/test_video_producer.py -k supplier -v`
Expected: FAIL — `produce() got an unexpected keyword argument 'storyboard_supplier'`

- [ ] **Step 3: Write the implementation**

Add to the imports at the top of `modules/video_producer.py`:

```python
from typing import Any, Protocol
```

(replacing the existing `from typing import Any`)

Add above `class BaseVideoProducer`:

```python
class StoryboardSupplier(Protocol):
    """Yields the first-frame still for one shot, given what came before.

    `previous_clip` is None for the first shot. Returning None means "no
    storyboard for this shot" and the producer falls back to the shared
    reference image.
    """

    def frame_for(
        self, index: int, shot_prompt: str, previous_clip: str | None
    ) -> str | None:
        ...
```

Replace the body of `produce()` (lines 140-204) with:

```python
    def produce(
        self,
        shots: list[str],
        reference_image_url: str | None = None,
        storyboard_urls: list[str] | None = None,
        storyboard_supplier: "StoryboardSupplier | None" = None,
    ) -> str:
        """Produce a stitched video from a list of shot prompts.

        Three modes for first-frame anchoring, in priority order:

        - **Chained (preset-9)**: caller passes `storyboard_supplier`. It is
          called once per shot with the PREVIOUS shot's clip, so each
          storyboard can carry character identity forward from what actually
          rendered. Requires the shot loop and the storyboard loop to
          interleave, which is why this is a callback rather than a list.

        - **Premium (preset-7)**: caller passes `storyboard_urls` — one URL per
          shot, generated upstream before production starts. Each shot is
          anchored to its own shot-appropriate frame, giving locked character
          identity AND varied starting poses.

        - **Legacy**: caller passes a single `reference_image_url` — used as
          the first frame for all shots (other presets, or fallback when
          storyboard generation fails).
        """
        workdir = tempfile.mkdtemp(prefix="cinematic_")
        try:
            clip_paths = []
            previous_clip: str | None = None
            for i, prompt in enumerate(shots):
                print(f"[VideoProducer] Submitting shot {i+1}/{len(shots)}", flush=True)
                ref_url = self._anchor_for(
                    i, prompt, previous_clip, storyboard_urls,
                    reference_image_url, storyboard_supplier,
                )
                task_id = self._submit_shot(prompt, ref_url)
                print(f"[VideoProducer] Polling task {task_id}...", flush=True)
                video_url = self._poll_shot(task_id)
                clip_path = os.path.join(workdir, f"shot_{i:02d}.mp4")
                self._download_clip(video_url, clip_path)
                clip_paths.append(clip_path)
                previous_clip = clip_path
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
            # Preserve the workdir on failure so the (already paid for) shots
            # can be reused for a manual stitch retry. The OS sweeps temp
            # folders eventually; a stuck folder costs nothing locally.
            print(f"[VideoProducer] FAILED — shots preserved at {workdir}", flush=True)
            raise

    def _anchor_for(
        self,
        index: int,
        prompt: str,
        previous_clip: str | None,
        storyboard_urls: list[str] | None,
        reference_image_url: str | None,
        supplier: "StoryboardSupplier | None",
    ) -> str | None:
        """Resolve one shot's first frame. Never raises — an anchor is an
        enhancement, and losing it costs pose variety, not the episode."""
        if supplier is not None:
            try:
                url = supplier.frame_for(index, prompt, previous_clip)
            except Exception as exc:
                print(
                    f"[VideoProducer]   shot {index+1} supplier failed ({exc}) "
                    f"— falling back to the shared reference",
                    flush=True,
                )
                url = None
            if url:
                print(f"[VideoProducer]   shot {index+1} anchor: chained storyboard", flush=True)
                return url

        if storyboard_urls and index < len(storyboard_urls) and storyboard_urls[index]:
            print(f"[VideoProducer]   shot {index+1} anchor: per-shot storyboard", flush=True)
            return storyboard_urls[index]

        if reference_image_url:
            print(f"[VideoProducer]   shot {index+1} anchor: shared locked ref", flush=True)
        return reference_image_url
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/modules/test_video_producer.py -v`
Expected: all PASS

- [ ] **Step 5: Run the full suite to confirm nothing regressed**

Run: `python3 -m pytest tests -q`
Expected: no failures — especially `tests/test_orchestrator.py`, which drives `produce()` through the pipeline

- [ ] **Step 6: Commit**

```bash
git add modules/video_producer.py tests/modules/test_video_producer.py
git commit -m "feat: produce() can take a per-shot storyboard supplier

Chaining needs storyboard N to see shot N-1, so the storyboard loop
and the shot loop have to interleave. A supplier callback keeps the
two responsibilities separate rather than moving image generation
into the video producer.

Anchor resolution never raises: losing a first frame costs pose
variety for one shot, not the episode.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Preset capability and orchestrator wiring

**Files:**
- Modify: `modules/preset.py:52-62` (feature configuration block), `modules/preset.py:119-148` (`from_raw`)
- Modify: `config.py` — the `preset-9` block beginning at line 329
- Modify: `orchestrator.py:281-297`
- Modify: `tests/modules/test_preset.py`

**Interfaces:**
- Consumes: `ChainedStoryboards` (Task 4); `produce(..., storyboard_supplier=...)` (Task 5).
- Produces: `Preset.chain_reference_frames: bool` (default `False`); `Deps.chained_storyboards: Callable[..., Any] = ChainedStoryboards`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/modules/test_preset.py`:

```python
def test_chaining_is_off_unless_a_preset_asks_for_it():
    from modules.preset import from_raw
    from config import PRESETS

    for key, raw in PRESETS.items():
        if key == "preset-9":
            continue
        assert from_raw(key, raw).chain_reference_frames is False, key


def test_preset_9_chains_reference_frames():
    from modules.preset import from_raw
    from config import PRESETS

    assert from_raw("preset-9", PRESETS["preset-9"]).chain_reference_frames is True


def test_preset_7_still_uses_batch_storyboards_not_chaining():
    """preset-7 is a 200-episode series with locked canon — it does not get
    this until a real before/after proves the two-base call holds fidelity."""
    from modules.preset import from_raw
    from config import PRESETS

    preset = from_raw("preset-7", PRESETS["preset-7"])
    assert preset.per_shot_storyboards is True
    assert preset.chain_reference_frames is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/modules/test_preset.py -k chain -v`
Expected: FAIL — `AttributeError: 'Preset' object has no attribute 'chain_reference_frames'`

- [ ] **Step 3: Write the implementation**

In `modules/preset.py`, add to the feature-configuration block (after `per_shot_storyboards`):

```python
    # Per-shot storyboards, but each one also sees the PREVIOUS shot's last
    # frame -- so character identity carries forward from what actually
    # rendered instead of being re-derived from the reference every time.
    # Requires per_shot_storyboards.
    chain_reference_frames: bool = False
```

In `from_raw`, add after the `per_shot_storyboards` line:

```python
        chain_reference_frames=bool(raw.get("chain_reference_frames", False)),
```

In `config.py`, in the `preset-9` block, immediately after `"per_shot_storyboards": True,` (line 397):

```python
        # Each shot's storyboard also sees the previous shot's last frame, so
        # the lead stops changing eye colour and outfit between shots.
        "chain_reference_frames": True,
```

In `orchestrator.py`, add to the imports:

```python
from modules.storyboard import build_storyboards, ChainedStoryboards
```

Add to the `Deps` dataclass, after the `storyboards` field:

```python
    chained_storyboards: Callable[..., Any] = ChainedStoryboards
```

Replace `orchestrator.py:281-297` with:

```python
        # Per-shot storyboard generation. Opt-in per preset via
        # `per_shot_storyboards: True` in config. For each shot, GPT Image 2
        # Edit takes the reference image as the base and the shot's scene
        # description as the prompt, producing a shot-appropriate first frame
        # that preserves the character's identity. Solves wallpaper-effect
        # and character drift across shots.
        #
        # With `chain_reference_frames: True` the storyboards are generated
        # lazily, one per shot, each also seeing the previous shot's last
        # frame — so identity carries forward from what actually rendered.
        storyboard_urls: list[str | None] | None = None
        storyboard_supplier = None
        if _preset.per_shot_storyboards and ref_image_url:
            if _preset.chain_reference_frames:
                storyboard_supplier = deps.chained_storyboards(
                    ref_image_url, style=VIDEO_STYLE,
                )
                print("[Pipeline] Chained storyboards enabled", flush=True)
            else:
                storyboard_urls = deps.storyboards(
                    script_result["shots"], ref_image_url, style=VIDEO_STYLE,
                )

        video_path = deps.video_producer().produce(
            script_result["shots"],
            reference_image_url=ref_image_url,
            storyboard_urls=storyboard_urls,
            storyboard_supplier=storyboard_supplier,
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/modules/test_preset.py tests/test_orchestrator.py -v`
Expected: all PASS

- [ ] **Step 5: Verify the modules still import cleanly**

Run: `python3 -c "import orchestrator, config; from modules.preset import active_preset; print(active_preset().key, active_preset().chain_reference_frames)"`
Expected: prints the active preset key and its chaining flag with no traceback

- [ ] **Step 6: Run the full suite**

Run: `python3 -m pytest tests -q`
Expected: no failures

- [ ] **Step 7: Commit**

```bash
git add modules/preset.py config.py orchestrator.py tests/modules/test_preset.py
git commit -m "feat: chain_reference_frames capability, enabled for preset-9

Data, not an identity check -- consistent with the capability pattern
in preset.py. Defaults off. preset-7 stays on batch storyboards until
a real before/after proves the two-base edit holds fidelity.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Manual before/after verification

The one thing unit tests cannot establish: whether a two-base edit actually holds character fidelity. Spec §5 names this as the risk that could sink the design.

**Files:**
- Modify: `scripts/manual_episode.py:98-104` (argument parsing) and `:196-215` (storyboard section)
- Create: `docs/superpowers/plans/2026-08-03-chained-reference-frames-results.md`

**Interfaces:**
- Consumes: everything from Tasks 1-6.
- Produces: a `--chain` flag on `scripts/manual_episode.py`, and a verdict — ship, tune the continuity prompt, or fall back to the composite-panel alternative in spec §3.1.

`manual_episode.py` calls `build_storyboards` directly rather than going through
the orchestrator, so it needs its own switch. A flag also makes before/after a
clean A/B on the same sheet row instead of an edit-and-revert of `config.py`.

- [ ] **Step 1: Add the `--chain` flag**

In `scripts/manual_episode.py`, add after the `--no-storyboards` argument (line 102-103):

```python
    ap.add_argument("--chain", action="store_true",
                    help="Chain reference frames: each shot's storyboard also sees the "
                         "previous shot's last frame. Fixes character drift across shots.")
```

Replace the storyboard section (lines 196-215) with:

```python
    # ===== 3. Per-shot storyboards (optional) =====
    storyboard_urls = None
    storyboard_supplier = None
    if args.chain:
        print("\n[3/4] Chained storyboards — each shot sees the previous frame")
        storyboard_supplier = ChainedStoryboards(ref_image_url, style=VIDEO_STYLE)
    elif not args.no_storyboards:
        print("\n[3/4] Generating per-shot storyboards...")
        storyboard_urls = build_storyboards(shots, ref_image_url, style=VIDEO_STYLE)
    else:
        print("\n[3/4] Skipping per-shot storyboards (--no-storyboards)")
```

Then extend the `produce(...)` call that follows it with:

```python
        storyboard_supplier=storyboard_supplier,
```

And update the import near line 50:

```python
from modules.storyboard import build_storyboards, ChainedStoryboards
```

- [ ] **Step 2: Verify the flag parses and the script still imports**

Run: `python3 scripts/manual_episode.py --help`
Expected: help text lists `--chain`, no traceback

- [ ] **Step 3: Confirm the active preset, then generate both episodes**

Run: `python3 -c "from modules.preset import active_preset; print(active_preset().key)"`
Expected: `preset-9`. If not, set `CONTENT_PRESET=preset-9` in `.env` first — `config.py` resolves at import time.

Generate the BEFORE (today's batch storyboards) and the AFTER (chained) from the **same sheet row**, so the story is identical and only the anchoring differs:

```bash
python3 scripts/manual_episode.py --row N            # BEFORE
python3 scripts/manual_episode.py --row N --chain    # AFTER
```

Note the output path each run prints. Cost is roughly $1.10 per run.

- [ ] **Step 4: Build a contact sheet for each**


```bash
ffmpeg -v error -i BEFORE.mp4 -vf "fps=1/2,scale=200:-1,tile=5x4" -q:v 4 before_grid.jpg
ffmpeg -v error -i AFTER.mp4  -vf "fps=1/2,scale=200:-1,tile=5x4" -q:v 4 after_grid.jpg
```

- [ ] **Step 5: Compare and record the verdict**

Look at both grids and answer, for the lead character across all five shots:

- Does eye colour stay constant?
- Does the outfit stay constant (same colour, same collar, same emblem)?
- Does the art style stay constant (same line weight, same grading)?
- Where a second character appears, do they stay constant after their first appearance?
- Did any shot end up letterboxed or oddly cropped?

Write the answers, with the two grids referenced, into
`docs/superpowers/plans/2026-08-03-chained-reference-frames-results.md`.

**Ship** if identity holds across all five shots. **Tune** `build_continuity_prompt` if identity holds but continuity is weak. **Fall back** to the composite-panel alternative (spec §3.1) if the two-base edit is visibly ignoring the reference image.

- [ ] **Step 6: Commit the results**

```bash
git add docs/superpowers/plans/2026-08-03-chained-reference-frames-results.md
git commit -m "docs: before/after results for chained reference frames

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Spec Coverage

| Spec section | Task |
|---|---|
| §3.1 Dual-base mechanism, reference first | Task 4 |
| §3.2 Control flow inversion via supplier | Task 5 |
| §3.3 `frame_chain.py` | Tasks 1-2 |
| §3.3 `edit_image` accepts a list | Task 3 |
| §3.3 `chain_reference_frames` capability | Task 6 |
| §3.4 Prompt names which base owns identity | Task 4 |
| §3.5 Centre-crop, never letterbox | Task 2 (`normalise_portrait`) |
| §3.5 Every storyboard aspect-checked before use | Task 2 (`portrait_anchor`), applied in Task 4 |
| §3.5 Data URI transport to Seedance | Task 1 (`to_data_uri`, `fetch_image`), Task 2 |
| §4 Extraction failure → single base | Task 4 |
| §4 Non-portrait → centre-crop | Task 2 |
| §4 Oversized payload → downscale | Task 1 |
| §4 Edit failure → locked reference | Task 4 |
| §4 Supplier raises → locked reference | Task 5 |
| §6 Unit tests | Tasks 1-6 |
| §6 Manual before/after | Task 7 (via a new `--chain` flag on `manual_episode.py`) |
| §7 preset-9 only | Task 6 |
| §5 Risk: two-base fidelity unproven | Task 7 is the gate; it names the fallback |

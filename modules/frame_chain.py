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
from typing import Any

import httpx

# How far before the end to sample. Far enough to clear motion blur and fades,
# close enough that it is still the shot's ending state.
FRAME_OFFSET_SEC = 0.4

# Longest edge of a frame encoded for the *image-edit* endpoint
# (openai/gpt-image-2/edit). 768px keeps the base64 payload near 300KB, a size
# proven to work there during probing.
MAX_EDGE_PX = 768

# Longest edge of a still encoded for the *video* endpoint
# (model/generateVideo). Deliberately a separate number from MAX_EDGE_PX: the
# two endpoints have different payload tolerances and must not silently share
# one constant. A still sent here becomes a Seedance FIRST FRAME, and Seedance
# renders 720x1280 — capping at 768 would hand it a 432x768 anchor, roughly a
# third of the output's pixels, and the softness shows. 1024 keeps the anchor
# at or above the clip's own resolution on the short edge.
ANCHOR_MAX_EDGE_PX = 1024

# Target shape for anything handed to Seedance as a first frame.
PORTRAIT_RATIO = 9 / 16


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


def _encoded_size(width: int, height: int, max_edge: int) -> tuple[int, int]:
    """The dimensions an image of this size is actually encoded at.

    Shared by to_data_uri (which does the scaling) and its callers (which want
    to log what they sent) so the arithmetic exists in exactly one place.
    """
    longest = max(width, height)
    if longest <= max_edge:
        return width, height
    # The longest edge lands on max_edge exactly; the other scales to match.
    if width >= height:
        return _even(max_edge), _even(round(height * max_edge / longest))
    return _even(round(width * max_edge / longest)), _even(max_edge)


def to_data_uri(image_path: str, *, max_edge: int = MAX_EDGE_PX) -> str:
    """Return the image as a base64 data URI, downscaling only if oversized."""
    width, height = _probe_size(image_path)
    source = image_path

    target_w, target_h = _encoded_size(width, height, max_edge)
    if (target_w, target_h) != (width, height):
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

    Encoded at ANCHOR_MAX_EDGE_PX, not MAX_EDGE_PX: this still goes to the
    video endpoint, and 768 there would leave shots 2-N visibly softer than
    shot 1 (which passes a full-size hosted URL through).

    Never raises. Aspect correction is an enhancement; an uncorrected first
    frame beats no first frame.
    """
    fetch = fetch or fetch_image
    try:
        local = fetch(image_url)
        corrected = normalise_portrait(local)
        if corrected == local:
            return image_url
        uri = to_data_uri(corrected, max_edge=ANCHOR_MAX_EDGE_PX)
        # Logged so the paid verification run tells us what Atlas actually
        # accepts at this size — the probe only ever proved 391KB.
        encoded_w, encoded_h = _encoded_size(
            *_probe_size(corrected), ANCHOR_MAX_EDGE_PX
        )
        print(
            f"[FrameChain] Anchor payload: {len(uri) // 1024}KB "
            f"at {encoded_w}x{encoded_h}",
            flush=True,
        )
        return uri
    except Exception as exc:
        print(
            f"[FrameChain] Could not verify aspect for {image_url[:60]}... "
            f"({exc}) — using it as-is",
            flush=True,
        )
        return image_url

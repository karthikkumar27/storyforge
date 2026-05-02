"""Build duration-locked MP4 cards from PNG + MP3 inputs.

Title and end cards are produced ONCE per (image+audio+format) combo, then
reused across every episode of that preset. Output format matches the current
video shots (resolution, aspect ratio, codec) so ffmpeg concat works cleanly.

Cache key: SHA256 of (image bytes + audio bytes + duration + width + height +
fade params). If you swap any input, the cache invalidates automatically.
"""

import hashlib
import os
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
CACHE_DIR = PROJECT_ROOT / "assets" / "cache"


def _resolve_dimensions(resolution: str, aspect_ratio: str) -> tuple[int, int]:
    """Match the dimensions our shots are rendered at.

    Returns (width, height) where height > width for vertical aspect ratios.
    """
    # Atlas Cloud / Seedance use these standard sizes.
    res_map = {
        "480p": 480,
        "720p": 720,
        "1080p": 1080,
    }
    short_side = res_map.get(resolution, 720)
    if aspect_ratio == "9:16":
        return (short_side * 9 // 16, short_side)  # vertical
    if aspect_ratio == "16:9":
        return (short_side, short_side * 9 // 16)  # horizontal
    if aspect_ratio == "1:1":
        return (short_side, short_side)
    # Sensible default — vertical
    return (short_side * 9 // 16, short_side)


def _hash_inputs(
    image_path: Path,
    audio_path: Path | None,
    duration: float,
    width: int,
    height: int,
    fade_in: float,
    fade_out: float,
) -> str:
    """Build a deterministic cache key from input contents and format params."""
    h = hashlib.sha256()
    h.update(image_path.read_bytes())
    if audio_path and audio_path.exists():
        h.update(audio_path.read_bytes())
    else:
        h.update(b"NO_AUDIO")
    h.update(f"{duration}|{width}|{height}|{fade_in}|{fade_out}".encode())
    return h.hexdigest()[:16]


def build_card(
    config: dict,
    resolution: str,
    aspect_ratio: str,
    kind: str = "card",
) -> Path | None:
    """Build (or fetch from cache) an MP4 title/end card matching the
    current video format.

    Returns the path to the MP4, or None if the source assets are missing
    (graceful no-op so the pipeline doesn't break when cards aren't set up).
    """
    if not config:
        return None

    image_path = PROJECT_ROOT / config["image"]
    if not image_path.exists():
        print(f"[TitleCard] No {kind} image at {image_path} — skipping", flush=True)
        return None

    audio_path = PROJECT_ROOT / config["audio"] if config.get("audio") else None
    if audio_path and not audio_path.exists():
        print(f"[TitleCard] {kind} audio missing at {audio_path} — building silent card", flush=True)
        audio_path = None

    duration = float(config.get("duration", 5.0))
    fade_in = float(config.get("fade_in", 0.0))
    fade_out = float(config.get("fade_out", 0.0))
    width, height = _resolve_dimensions(resolution, aspect_ratio)

    cache_key = _hash_inputs(image_path, audio_path, duration, width, height, fade_in, fade_out)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = CACHE_DIR / f"{kind}_{cache_key}.mp4"

    if cached.exists():
        print(f"[TitleCard] Cache hit — {kind}: {cached.name}", flush=True)
        return cached

    print(f"[TitleCard] Building {kind} ({width}x{height}, {duration}s)...", flush=True)

    # Build a video filter that scales+pads the image to exact dimensions
    # (preserving aspect of the source image, padding with black if needed)
    # then applies fade in / fade out.
    fade_filter_parts = []
    fade_filter_parts.append(
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black"
    )
    if fade_in > 0:
        fade_filter_parts.append(f"fade=in:st=0:d={fade_in}")
    if fade_out > 0:
        fade_filter_parts.append(f"fade=out:st={duration - fade_out}:d={fade_out}")
    video_filter = ",".join(fade_filter_parts)

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(image_path),
    ]

    if audio_path:
        cmd += ["-i", str(audio_path)]
        cmd += [
            "-t", str(duration),
            "-vf", video_filter,
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-r", "24",
            "-c:a", "aac",
            "-b:a", "128k",
            "-ar", "44100",
            "-ac", "2",
            "-shortest",
            str(cached),
        ]
    else:
        # No audio — generate a silent track so format matches shot files
        cmd += [
            "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100",
            "-t", str(duration),
            "-vf", video_filter,
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-r", "24",
            "-c:a", "aac",
            "-b:a", "128k",
            "-shortest",
            str(cached),
        ]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode()[-500:] if exc.stderr else ""
        print(f"[TitleCard] ffmpeg failed for {kind}: {stderr}", flush=True)
        return None

    print(f"[TitleCard] Built {kind}: {cached.name}", flush=True)
    return cached

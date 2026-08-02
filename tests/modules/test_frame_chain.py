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

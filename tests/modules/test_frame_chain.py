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

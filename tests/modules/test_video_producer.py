# tests/modules/test_video_producer.py
import pytest
from unittest.mock import MagicMock, patch, call

from config import (
    ASPECT_RATIO,
    ATLAS_VIDEO_MODEL_I2V,
    ATLAS_VIDEO_MODEL_T2V,
    SHOT_DURATION,
)
from tests.support import StubAtlasClient


# -- Atlas producer: talks to the shared client, not its own polling loop -----

def test_atlas_shot_with_a_reference_image_uses_image_to_video():
    from modules.video_producer import AtlasVideoProducer
    client = StubAtlasClient()

    AtlasVideoProducer(client)._submit_shot("a slow orbit", "https://cdn/alan.png")

    body = client.calls[0]["body"]
    assert body["model"] == ATLAS_VIDEO_MODEL_I2V
    assert body["image"] == "https://cdn/alan.png"
    assert body["prompt"] == "a slow orbit"
    assert body["duration"] == SHOT_DURATION
    assert body["aspect_ratio"] == ASPECT_RATIO


def test_atlas_shot_without_a_reference_image_uses_text_to_video():
    from modules.video_producer import AtlasVideoProducer
    client = StubAtlasClient()

    AtlasVideoProducer(client)._submit_shot("a wide vista")

    body = client.calls[0]["body"]
    assert body["model"] == ATLAS_VIDEO_MODEL_T2V
    assert "image" not in body


def test_atlas_poll_returns_the_first_output():
    from modules.video_producer import AtlasVideoProducer
    client = StubAtlasClient(outputs=["https://cdn/shot.mp4", "https://cdn/extra.mp4"])

    assert AtlasVideoProducer(client)._poll_shot("pred_1") == "https://cdn/shot.mp4"


def test_seedance_1_5_fast_caps_duration_at_ten_seconds():
    from modules.video_producer import AtlasSeedance1_5T2VFastProducer
    client = StubAtlasClient(outputs=["https://cdn/drone.mp4"])

    AtlasSeedance1_5T2VFastProducer(client).produce("a coastal flight", {"duration": 15})

    assert client.calls[0]["body"]["duration"] == 10


def test_seedance_1_5_fast_uses_the_underscored_aspect_ratio_field():
    """1.5-fast takes `aspect_ratio` and plain 720p; 2.0 takes `ratio` and
    720p-SR. Getting these crossed is a silent 400 from Atlas."""
    from modules.video_producer import AtlasSeedance1_5T2VFastProducer
    client = StubAtlasClient(outputs=["https://cdn/drone.mp4"])

    AtlasSeedance1_5T2VFastProducer(client).produce("x", {"ratio": "9:16"})

    body = client.calls[0]["body"]
    assert body["aspect_ratio"] == "9:16"
    assert "ratio" not in body
    assert "generate_audio" not in body


def test_seedance_2_t2v_requests_native_audio():
    from modules.video_producer import AtlasSeedance2T2VProducer
    client = StubAtlasClient(outputs=["https://cdn/drone.mp4"])

    AtlasSeedance2T2VProducer(client).produce("x", {"duration": 12})

    body = client.calls[0]["body"]
    assert body["generate_audio"] is True
    assert body["ratio"] == "9:16"
    assert body["duration"] == 12


def test_seedance_2_loop_passes_the_same_still_as_first_and_last_frame():
    """That's the whole looping mechanism -- it's native to the i2v API."""
    from modules.video_producer import AtlasSeedance2I2VLoopProducer
    client = StubAtlasClient(outputs=["https://cdn/loop.mp4"])
    producer = AtlasSeedance2I2VLoopProducer(client)

    with patch.object(producer, "_apply_loop_crossfade") as crossfade:
        producer.produce("https://cdn/still.png", "drift and return", {})

    body = client.calls[0]["body"]
    assert body["image"] == "https://cdn/still.png"
    assert body["last_image"] == "https://cdn/still.png"
    assert crossfade.called


def test_seedance_downloads_through_the_client():
    from modules.video_producer import AtlasSeedance2T2VProducer
    client = StubAtlasClient(outputs=["https://cdn/drone.mp4"])

    path = AtlasSeedance2T2VProducer(client).produce("x", {})

    assert client.downloads[0][0] == "https://cdn/drone.mp4"
    assert path.endswith("drone.mp4")


# -- Kling producer (unchanged, still has its own protocol) -------------------


@patch("modules.video_producer.httpx")
def test_submit_shot_returns_task_id(mock_httpx, monkeypatch):
    monkeypatch.setenv("KLING_ACCESS_KEY_ID", "key123")
    monkeypatch.setenv("KLING_SECRET_KEY", "secret456")

    mock_resp = MagicMock()
    mock_resp.status_code = 200  # _submit_shot raises on >= 400
    mock_resp.json.return_value = {"data": {"task_id": "task_abc"}}
    mock_httpx.post.return_value = mock_resp

    from modules.video_producer import KlingVideoProducer
    producer = KlingVideoProducer()
    task_id = producer._submit_shot("Slow orbital pan, deep space black, nebula glow")

    assert task_id == "task_abc"
    mock_httpx.post.assert_called_once()


@patch("modules.video_producer.httpx")
def test_poll_shot_returns_url_when_succeed(mock_httpx, monkeypatch):
    monkeypatch.setenv("KLING_ACCESS_KEY_ID", "key123")
    monkeypatch.setenv("KLING_SECRET_KEY", "secret456")

    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "data": {"task_status": "succeed", "videos": [{"url": "https://cdn.kling.ai/v.mp4"}]}
    }
    mock_httpx.get.return_value = mock_resp

    from modules.video_producer import KlingVideoProducer
    producer = KlingVideoProducer()
    url = producer._poll_shot("task_abc")

    assert url == "https://cdn.kling.ai/v.mp4"


@patch("modules.video_producer.httpx")
def test_poll_shot_raises_on_failed_status(mock_httpx, monkeypatch):
    monkeypatch.setenv("KLING_ACCESS_KEY_ID", "key123")
    monkeypatch.setenv("KLING_SECRET_KEY", "secret456")

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": {"task_status": "failed"}}
    mock_httpx.get.return_value = mock_resp

    from modules.video_producer import KlingVideoProducer
    producer = KlingVideoProducer()

    with pytest.raises(RuntimeError, match="failed"):
        producer._poll_shot("task_abc")


@patch("modules.video_producer.subprocess.run")
def test_stitch_writes_concat_file_and_calls_ffmpeg(mock_run, monkeypatch, tmp_path):
    monkeypatch.setenv("KLING_ACCESS_KEY_ID", "key123")
    monkeypatch.setenv("KLING_SECRET_KEY", "secret456")

    from modules.video_producer import KlingVideoProducer
    producer = KlingVideoProducer()
    clip_paths = [str(tmp_path / "shot_00.mp4"), str(tmp_path / "shot_01.mp4")]
    output = str(tmp_path / "stitched.mp4")

    producer._stitch(clip_paths, output)

    args = mock_run.call_args[0][0]
    assert args[0] == "ffmpeg"
    assert "-f" in args
    assert "concat" in args
    assert output in args


def test_jwt_token_contains_access_key_id(monkeypatch):
    monkeypatch.setenv("KLING_ACCESS_KEY_ID", "my_key_id")
    monkeypatch.setenv("KLING_SECRET_KEY", "my_secret")

    from modules.video_producer import KlingVideoProducer
    import jwt

    producer = KlingVideoProducer()
    token = producer._jwt_token()
    decoded = jwt.decode(token, "my_secret", algorithms=["HS256"])

    assert decoded["iss"] == "my_key_id"

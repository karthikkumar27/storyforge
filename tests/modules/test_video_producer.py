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


# -- Kling producer (legacy provider, still has its own protocol) -------------
#
# Credentials, HTTP and sleep are all injected, so these need no environment,
# no network and no clock.

def _kling(http):
    from modules.video_producer import KlingVideoProducer
    return KlingVideoProducer(
        access_key_id="key123",
        secret_key="secret456",
        http=http,
        sleep=lambda _s: None,
    )


def _resp(status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


def test_kling_submit_returns_the_task_id():
    http = MagicMock()
    http.post.return_value = _resp(200, {"data": {"task_id": "task_abc"}})

    assert _kling(http)._submit_shot("Slow orbital pan") == "task_abc"
    http.post.assert_called_once()


def test_kling_submit_raises_with_the_response_body():
    http = MagicMock()
    http.post.return_value = _resp(400, {})
    http.post.return_value.text = "bad prompt"

    with pytest.raises(RuntimeError, match="bad prompt"):
        _kling(http)._submit_shot("x")


def test_kling_poll_returns_the_url_when_it_succeeds():
    http = MagicMock()
    http.get.return_value = _resp(200, {
        "data": {"task_status": "succeed", "videos": [{"url": "https://cdn.kling.ai/v.mp4"}]},
    })

    assert _kling(http)._poll_shot("task_abc") == "https://cdn.kling.ai/v.mp4"


def test_kling_poll_raises_on_a_failed_task():
    http = MagicMock()
    http.get.return_value = _resp(200, {"data": {"task_status": "failed"}})

    with pytest.raises(RuntimeError, match="failed"):
        _kling(http)._poll_shot("task_abc")


def test_kling_poll_waits_while_the_task_is_still_running():
    from config import KLING_MAX_POLL_ATTEMPTS
    http = MagicMock()
    http.get.return_value = _resp(200, {"data": {"task_status": "processing"}})

    with pytest.raises(TimeoutError, match="timed out"):
        _kling(http)._poll_shot("task_abc")

    assert http.get.call_count == KLING_MAX_POLL_ATTEMPTS


def test_kling_signs_requests_with_its_access_key():
    import jwt
    http = MagicMock()

    token = _kling(http)._jwt_token()

    assert jwt.decode(token, "secret456", algorithms=["HS256"])["iss"] == "key123"


@patch("modules.video_producer.subprocess.run")
def test_stitch_writes_concat_file_and_calls_ffmpeg(mock_run, tmp_path):
    producer = _kling(MagicMock())
    clip_paths = [str(tmp_path / "shot_00.mp4"), str(tmp_path / "shot_01.mp4")]
    output = str(tmp_path / "stitched.mp4")

    producer._stitch(clip_paths, output)

    args = mock_run.call_args[0][0]
    assert args[0] == "ffmpeg"
    assert "-f" in args
    assert "concat" in args
    assert output in args


# -- Seedance 1.0 (legacy BytePlus SDK path) ----------------------------------

def test_seedance_legacy_producer_accepts_an_injected_ark_client():
    """No ARK_API_KEY needed: the SDK client is passed in."""
    from modules.video_producer import SeedanceVideoProducer
    client = MagicMock()
    client.content_generation.tasks.create.return_value.id = "task_9"

    producer = SeedanceVideoProducer(client=client, sleep=lambda _s: None)

    assert producer._submit_shot("a slow orbit") == "task_9"

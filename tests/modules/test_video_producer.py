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


# -- produce() anchor resolution: supplier vs storyboard_urls vs shared ref ---

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


def test_the_supplier_outranks_batch_storyboards_and_none_falls_to_them():
    producer = RecordingProducer()
    _run(producer, shots=["one", "two"],
         reference_image_url="https://cdn/ref.png",
         storyboard_urls=["https://cdn/sb0.png", "https://cdn/sb1.png"],
         storyboard_supplier=StubSupplier(["https://cdn/a.png", None]))
    assert [r for _, r in producer.submitted] == ["https://cdn/a.png", "https://cdn/sb1.png"]


# -- a rejected inline anchor must not cost the episode -----------------------
#
# Chaining is the first thing in this pipeline to put an inline `data:` payload
# in `body["image"]`; before it, that field was always a hosted URL. Atlas is
# documented (spec §2) as intermittently rejecting bodies it accepts minutes
# later with misleading schema errors. A rejection on shot 3 would otherwise
# kill an episode with shots 1-2 already paid for.

class RejectsInlineAnchors(RecordingProducer):
    def _submit_shot(self, prompt, reference_image_url=None):
        self.submitted.append((prompt, reference_image_url))
        if reference_image_url and reference_image_url.startswith("data:"):
            raise RuntimeError("request body field <image> is required")
        return f"task_{len(self.submitted)}"


def test_a_rejected_inline_anchor_retries_with_the_shared_reference():
    producer = RejectsInlineAnchors()
    supplier = StubSupplier(["data:image/png;base64,AAAA", "https://cdn/b.png"])

    _run(
        producer, shots=["one", "two"],
        reference_image_url="https://cdn/ref.png",
        storyboard_supplier=supplier,
    )

    assert [r for _, r in producer.submitted] == [
        "data:image/png;base64,AAAA",   # rejected
        "https://cdn/ref.png",          # retried with the shared reference
        "https://cdn/b.png",            # shot 2 unaffected — the episode ran on
    ]


def test_a_rejected_inline_anchor_retries_bare_when_there_is_no_shared_reference():
    producer = RejectsInlineAnchors()

    _run(
        producer, shots=["one"],
        storyboard_supplier=StubSupplier(["data:image/png;base64,AAAA"]),
    )

    assert producer.submitted[-1][1] is None   # text-to-video rather than nothing


def test_a_submit_failure_on_a_hosted_anchor_still_propagates():
    """Only the inline-payload case gets a retry. A hosted URL failing means
    something is genuinely wrong, and swallowing it would mask it."""
    class Exploding(RecordingProducer):
        def _submit_shot(self, prompt, reference_image_url=None):
            self.submitted.append((prompt, reference_image_url))
            raise RuntimeError("atlas down")

    producer = Exploding()

    with pytest.raises(RuntimeError, match="atlas down"):
        _run(producer, shots=["one"], reference_image_url="https://cdn/ref.png")

    assert len(producer.submitted) == 1   # no retry


def test_a_retry_that_also_fails_propagates():
    class AlwaysFails(RecordingProducer):
        def _submit_shot(self, prompt, reference_image_url=None):
            self.submitted.append((prompt, reference_image_url))
            raise RuntimeError("atlas down")

    producer = AlwaysFails()

    with pytest.raises(RuntimeError, match="atlas down"):
        _run(
            producer, shots=["one"],
            reference_image_url="https://cdn/ref.png",
            storyboard_supplier=StubSupplier(["data:image/png;base64,AAAA"]),
        )

    assert len(producer.submitted) == 2   # tried once, retried once, then gave up


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

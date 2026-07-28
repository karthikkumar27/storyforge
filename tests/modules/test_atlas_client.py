# tests/modules/test_atlas_client.py
import httpx
import pytest

from modules.atlas_client import (
    AtlasClient,
    AtlasContentFilterError,
    AtlasError,
    AtlasTaskFailed,
    AtlasTimeout,
    GATEWAY_BACKOFF,
    RATE_LIMIT_BACKOFF,
)


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=None):
        self.status_code = status_code
        self._json = json_data
        self.text = text if text is not None else ""

    def json(self):
        if self._json is None:
            raise ValueError("not JSON")
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=None)


class FakeStream:
    def __init__(self, chunks):
        self._chunks = chunks

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        pass

    def iter_bytes(self, chunk_size=65536):
        return iter(self._chunks)


class FakeHttp:
    """Scripted responses. Each call pops the next one from its queue."""

    def __init__(self, posts=None, gets=None, chunks=(b"data",)):
        self.posts = list(posts or [])
        self.gets = list(gets or [])
        self.chunks = chunks
        self.post_calls = []
        self.get_calls = []

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        nxt = self.posts.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        nxt = self.gets.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    def stream(self, method, url, **kwargs):
        self.get_calls.append((url, kwargs))
        return FakeStream(self.chunks)


class RecordingSleep:
    """Stands in for time.sleep so retry paths run instantly and visibly."""

    def __init__(self):
        self.slept = []

    def __call__(self, seconds):
        self.slept.append(seconds)


def _client(http, sleep=None, **kwargs):
    return AtlasClient(
        api_key="test-key",
        http=http,
        sleep=sleep or RecordingSleep(),
        **kwargs,
    )


SUBMITTED = FakeResponse(200, {"data": {"id": "pred_123"}})


def _completed(outputs=("https://cdn/out.mp4",)):
    return FakeResponse(200, {"data": {"status": "completed", "outputs": list(outputs)}})


def _pending():
    return FakeResponse(200, {"data": {"status": "processing"}})


# -- submit -------------------------------------------------------------------

def test_submit_returns_the_prediction_id():
    http = FakeHttp(posts=[SUBMITTED])

    assert _client(http).submit("model/generateVideo", {"prompt": "x"}) == "pred_123"


def test_submit_targets_the_endpoint_with_auth():
    http = FakeHttp(posts=[SUBMITTED])

    _client(http).submit("/model/generateImage", {"prompt": "x"})

    url, kwargs = http.post_calls[0]
    assert url.endswith("/model/generateImage")
    assert url.count("//") == 1          # no doubled slash from the leading "/"
    assert kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert kwargs["json"] == {"prompt": "x"}


def test_submit_backs_off_and_retries_on_rate_limit():
    sleep = RecordingSleep()
    http = FakeHttp(posts=[FakeResponse(429, text="slow down"), SUBMITTED])

    assert _client(http, sleep).submit("model/generateVideo", {}) == "pred_123"
    assert sleep.slept == [RATE_LIMIT_BACKOFF]


def test_submit_raises_on_a_hard_rejection():
    http = FakeHttp(posts=[FakeResponse(422, text="bad model id")])

    with pytest.raises(AtlasError, match="bad model id"):
        _client(http).submit("model/generateVideo", {})


def test_submit_flags_a_content_filter_rejection_distinctly():
    http = FakeHttp(posts=[FakeResponse(400, text="rejected by content safety system")])

    with pytest.raises(AtlasContentFilterError):
        _client(http).submit("model/generateImage", {})


# -- polling ------------------------------------------------------------------

def test_await_outputs_returns_the_outputs():
    http = FakeHttp(gets=[_pending(), _completed(["https://cdn/a.png"])])

    outputs = _client(http).await_outputs("pred_123")

    assert outputs == ["https://cdn/a.png"]


def test_await_outputs_waits_the_requested_cadence_between_polls():
    sleep = RecordingSleep()
    http = FakeHttp(gets=[_pending(), _pending(), _completed()])

    _client(http, sleep).await_outputs("pred_123", poll_interval=2)

    assert sleep.slept == [2, 2]


def test_completed_without_outputs_is_a_failure():
    http = FakeHttp(gets=[FakeResponse(200, {"data": {"status": "completed", "outputs": []}})])

    with pytest.raises(AtlasTaskFailed, match="no outputs"):
        _client(http).await_outputs("pred_123")


def test_failed_status_raises_with_the_reason():
    http = FakeHttp(gets=[FakeResponse(200, {"data": {"status": "failed", "error": "OOM"}})])

    with pytest.raises(AtlasTaskFailed, match="OOM"):
        _client(http).await_outputs("pred_123")


def test_failed_status_from_the_content_filter_is_distinct():
    http = FakeHttp(gets=[
        FakeResponse(200, {"data": {"status": "failed", "error": "blocked by safety policy"}}),
    ])

    with pytest.raises(AtlasContentFilterError):
        _client(http).await_outputs("pred_123")


def test_a_hung_poll_resumes_instead_of_killing_the_run():
    """The regression this whole module exists to fix: AtlasVideoProducer had no
    read-timeout handler, so a hung prediction request killed a preset-7 episode
    after its shots had already been paid for."""
    sleep = RecordingSleep()
    http = FakeHttp(gets=[httpx.ReadTimeout("hung"), _completed()])

    outputs = _client(http, sleep).await_outputs("pred_123", poll_interval=15)

    assert outputs == ["https://cdn/out.mp4"]
    assert sleep.slept == [15]


def test_rate_limited_polling_backs_off_sixty_seconds():
    sleep = RecordingSleep()
    http = FakeHttp(gets=[FakeResponse(429, text="slow down"), _completed()])

    _client(http, sleep).await_outputs("pred_123")

    assert sleep.slept == [RATE_LIMIT_BACKOFF]


@pytest.mark.parametrize("code", [502, 503, 504])
def test_gateway_errors_back_off_and_resume(code):
    sleep = RecordingSleep()
    http = FakeHttp(gets=[FakeResponse(code, text="bad gateway"), _completed()])

    _client(http, sleep).await_outputs("pred_123")

    assert sleep.slept == [GATEWAY_BACKOFF]


@pytest.mark.parametrize("code", [400, 500])
def test_a_structured_failure_body_is_terminal(code):
    """Atlas reports real task failures as 400/500 with the reason in JSON."""
    http = FakeHttp(gets=[
        FakeResponse(code, {"message": "input image could not be fetched"},
                     text='{"message": "input image could not be fetched"}'),
    ])

    with pytest.raises(AtlasTaskFailed, match="could not be fetched"):
        _client(http).await_outputs("pred_123")


def test_a_structured_failure_naming_the_filter_is_a_content_filter_error():
    http = FakeHttp(gets=[
        FakeResponse(400, {"message": "request violates our content policy"},
                     text="content policy"),
    ])

    with pytest.raises(AtlasContentFilterError):
        _client(http).await_outputs("pred_123")


@pytest.mark.parametrize("code", [400, 500])
def test_an_unstructured_error_body_is_treated_as_transient(code):
    """A bare HTML error page is a gateway blip, not a task failure -- the case
    the comments in image_generator.edit_image were written about."""
    sleep = RecordingSleep()
    http = FakeHttp(gets=[FakeResponse(code, text="<html>Server Error</html>"), _completed()])

    outputs = _client(http, sleep).await_outputs("pred_123")

    assert outputs == ["https://cdn/out.mp4"]
    assert sleep.slept == [GATEWAY_BACKOFF]


def test_polling_gives_up_eventually():
    http = FakeHttp(gets=[_pending() for _ in range(5)])

    with pytest.raises(AtlasTimeout, match="timed out"):
        _client(http, max_attempts=5).await_outputs("pred_123")


# -- run + download -----------------------------------------------------------

def test_run_submits_then_waits():
    http = FakeHttp(posts=[SUBMITTED], gets=[_completed(["https://cdn/v.mp4"])])

    assert _client(http).run("model/generateVideo", {"prompt": "x"}) == ["https://cdn/v.mp4"]


def test_run_polls_the_id_that_submit_returned():
    http = FakeHttp(posts=[SUBMITTED], gets=[_completed()])

    _client(http).run("model/generateVideo", {})

    poll_url = http.get_calls[0][0]
    assert poll_url.endswith("/model/prediction/pred_123")


def test_download_streams_to_the_given_path(tmp_path):
    http = FakeHttp(chunks=[b"abc", b"def"])
    target = tmp_path / "clip.mp4"

    result = _client(http).download("https://cdn/v.mp4", str(target))

    assert result == str(target)
    assert target.read_bytes() == b"abcdef"

# tests/modules/test_youtube_uploader.py
#
# The authenticated YouTube service is injected, so these tests need no OAuth
# token, no client credentials and no network.
import pytest
from unittest.mock import MagicMock

from config import DEFAULT_HASHTAGS
from modules.preset import active_preset
from modules.youtube_uploader import YouTubeUploader

_preset = active_preset()

SCRIPT_RESULT = {
    "title": "The Last Signal",
    "description": "A haunting journey through deep space.",
    "tags": ["scifi", "space", "horror", "cinematic", "shortfilm"],
    "narrative": "In the void...",
    "shots": [],
}


class FakeInsertRequest:
    """Yields the given chunk results in order, then completes."""

    def __init__(self, video_id="abc123", chunks=None):
        self.results = list(chunks or []) + [(None, {"id": video_id})]
        self.calls = 0

    def next_chunk(self):
        self.calls += 1
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _uploader(request=None):
    service = MagicMock()
    request = request or FakeInsertRequest()
    service.videos.return_value.insert.return_value = request
    uploader = YouTubeUploader(service=service, media_factory=lambda *a, **k: MagicMock())
    return uploader, service, request


def _snippet(service):
    return service.videos.return_value.insert.call_args.kwargs["body"]["snippet"]


def _status(service):
    return service.videos.return_value.insert.call_args.kwargs["body"]["status"]


# -- the upload ---------------------------------------------------------------

def test_upload_returns_the_watch_url():
    uploader, _, _ = _uploader(FakeInsertRequest(video_id="xyz789"))

    assert uploader.upload("/tmp/final.mp4", SCRIPT_RESULT) == (
        "https://www.youtube.com/watch?v=xyz789"
    )


def test_the_title_and_tags_come_from_the_script():
    uploader, service, _ = _uploader()

    uploader.upload("/tmp/final.mp4", SCRIPT_RESULT)

    snippet = _snippet(service)
    assert snippet["title"] == "The Last Signal"
    assert snippet["tags"] == ["scifi", "space", "horror", "cinematic", "shortfilm"]


def test_the_category_comes_from_the_active_preset():
    uploader, service, _ = _uploader()

    uploader.upload("/tmp/final.mp4", SCRIPT_RESULT)

    assert _snippet(service)["categoryId"] == _preset.youtube_category


def test_chunks_are_uploaded_until_the_video_id_arrives():
    request = FakeInsertRequest(chunks=[(None, None), (None, None)])
    uploader, _, _ = _uploader(request)

    uploader.upload("/tmp/final.mp4", SCRIPT_RESULT)

    assert request.calls == 3


# -- hashtags -----------------------------------------------------------------

def test_hashtags_are_prepended_above_the_description():
    """The first three render as clickable chips above the title on mobile."""
    uploader, service, _ = _uploader()

    uploader.upload("/tmp/final.mp4", SCRIPT_RESULT)

    hashtag_line, blank, body = _snippet(service)["description"].split("\n", 2)
    assert body == "A haunting journey through deep space."
    assert blank == ""
    assert all(tag.startswith("#") for tag in hashtag_line.split())


def test_preset_hashtags_lead_and_defaults_follow():
    uploader, service, _ = _uploader()

    uploader.upload("/tmp/final.mp4", SCRIPT_RESULT)

    tags = _snippet(service)["description"].split("\n", 1)[0].split()
    expected_lead = [f"#{t.lstrip('#').lower()}" for t in _preset.youtube_hashtags]
    assert tags[:len(expected_lead)] == expected_lead
    for default in DEFAULT_HASHTAGS:
        assert f"#{default.lower()}" in tags


def test_hashtags_are_deduplicated_case_insensitively():
    uploader, service, _ = _uploader()

    uploader.upload("/tmp/final.mp4", SCRIPT_RESULT)

    tags = _snippet(service)["description"].split("\n", 1)[0].split()
    assert len(tags) == len(set(tags))


# -- COPPA --------------------------------------------------------------------

def test_the_audience_declaration_follows_the_preset():
    """Declared explicitly rather than omitted, so Studio doesn't park the video
    in 'pending audience declaration' and disable end screens."""
    uploader, service, _ = _uploader()

    uploader.upload("/tmp/final.mp4", SCRIPT_RESULT)

    status = _status(service)
    assert status["selfDeclaredMadeForKids"] is _preset.made_for_kids
    assert status["privacyStatus"] == "public"

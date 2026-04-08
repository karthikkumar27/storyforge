# tests/modules/test_youtube_uploader.py
import json
import pytest
from unittest.mock import MagicMock, patch

SCRIPT_RESULT = {
    "title": "The Last Signal",
    "description": "A haunting journey through deep space.",
    "tags": ["scifi", "space", "horror", "cinematic", "shortfilm"],
    "narrative": "In the void...",
    "shots": [],
}


@patch("modules.youtube_uploader.MediaFileUpload")
@patch("modules.youtube_uploader.build")
@patch("modules.youtube_uploader.Credentials")
@patch("modules.youtube_uploader.Request")
def test_upload_returns_youtube_url(
    mock_request, mock_creds_class, mock_build, mock_media, monkeypatch
):
    monkeypatch.setenv("YOUTUBE_OAUTH_TOKEN", json.dumps({"refresh_token": "tok123"}))
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "client_id")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "client_secret")

    mock_creds = MagicMock()
    mock_creds.expired = False
    mock_creds_class.return_value = mock_creds

    mock_youtube = MagicMock()
    mock_build.return_value = mock_youtube

    mock_insert_request = MagicMock()
    mock_youtube.videos.return_value.insert.return_value = mock_insert_request
    mock_insert_request.next_chunk.return_value = (None, {"id": "abc123"})

    from modules.youtube_uploader import YouTubeUploader
    uploader = YouTubeUploader()
    url = uploader.upload("/tmp/final.mp4", SCRIPT_RESULT)

    assert url == "https://www.youtube.com/watch?v=abc123"


@patch("modules.youtube_uploader.MediaFileUpload")
@patch("modules.youtube_uploader.build")
@patch("modules.youtube_uploader.Credentials")
@patch("modules.youtube_uploader.Request")
def test_upload_uses_script_title_and_description(
    mock_request, mock_creds_class, mock_build, mock_media, monkeypatch
):
    monkeypatch.setenv("YOUTUBE_OAUTH_TOKEN", json.dumps({"refresh_token": "tok123"}))
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "client_id")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "client_secret")

    mock_creds = MagicMock()
    mock_creds.expired = False
    mock_creds_class.return_value = mock_creds

    mock_youtube = MagicMock()
    mock_build.return_value = mock_youtube
    mock_insert_request = MagicMock()
    mock_youtube.videos.return_value.insert.return_value = mock_insert_request
    mock_insert_request.next_chunk.return_value = (None, {"id": "xyz"})

    from modules.youtube_uploader import YouTubeUploader
    uploader = YouTubeUploader()
    uploader.upload("/tmp/final.mp4", SCRIPT_RESULT)

    call_kwargs = mock_youtube.videos.return_value.insert.call_args.kwargs
    snippet = call_kwargs["body"]["snippet"]
    assert snippet["title"] == "The Last Signal"
    assert snippet["description"] == "A haunting journey through deep space."
    assert snippet["tags"] == ["scifi", "space", "horror", "cinematic", "shortfilm"]

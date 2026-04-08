# tests/test_orchestrator.py
import pytest
from unittest.mock import MagicMock, patch


SCRIPT_RESULT = {
    "narrative": "In the void...",
    "title": "The Ghost Signal",
    "description": "desc",
    "tags": ["scifi"],
    "shots": ["shot1", "shot2", "shot3"],
}


@patch("orchestrator.YouTubeUploader")
@patch("orchestrator.AudioMixer")
@patch("orchestrator.VideoProducer")
@patch("orchestrator.ScriptGenerator")
@patch("orchestrator.GSheetReader")
def test_run_pipeline_returns_done_with_url(
    MockReader, MockScript, MockVideo, MockAudio, MockYouTube
):
    mock_reader = MockReader.return_value
    mock_reader.get_pending_row.return_value = {
        "row_index": 2,
        "title": "Test",
        "story_brief": "A ghost astronaut",
        "genre": "blend",
        "duration_sec": 75,
    }
    MockScript.return_value.generate.return_value = SCRIPT_RESULT
    MockVideo.return_value.produce.return_value = "/tmp/stitched.mp4"
    MockAudio.return_value.mix.return_value = "/tmp/final.mp4"
    MockYouTube.return_value.upload.return_value = "https://youtube.com/watch?v=abc"

    from orchestrator import run_pipeline
    result = run_pipeline()

    assert result["status"] == "done"
    assert result["youtube_url"] == "https://youtube.com/watch?v=abc"
    mock_reader.update_done.assert_called_once_with(2, "https://youtube.com/watch?v=abc")


@patch("orchestrator.BriefGenerator")
@patch("orchestrator.GSheetReader")
def test_run_pipeline_returns_no_pending_when_sheet_empty(MockReader, MockBrief):
    # Both calls to get_pending_row return None (even after brief generation attempt)
    MockReader.return_value.get_pending_row.return_value = None
    MockBrief.return_value.generate.return_value = {
        "story_brief": "A ghost in the machine",
        "genre": "sci-fi",
        "title_hint": "Static",
    }

    from orchestrator import run_pipeline
    result = run_pipeline()

    assert result["status"] == "no_pending_rows"


@patch("orchestrator.YouTubeUploader")
@patch("orchestrator.AudioMixer")
@patch("orchestrator.VideoProducer")
@patch("orchestrator.ScriptGenerator")
@patch("orchestrator.GSheetReader")
def test_run_pipeline_writes_error_on_script_failure(
    MockReader, MockScript, MockVideo, MockAudio, MockYouTube
):
    mock_reader = MockReader.return_value
    mock_reader.get_pending_row.return_value = {
        "row_index": 2, "title": "T", "story_brief": "b", "genre": "sci-fi", "duration_sec": 75
    }
    MockScript.return_value.generate.side_effect = RuntimeError("Claude API down")

    from orchestrator import run_pipeline
    with pytest.raises(RuntimeError, match="Claude API down"):
        run_pipeline()

    mock_reader.update_error.assert_called_once_with(2, "Claude API down")


@patch("orchestrator.YouTubeUploader")
@patch("orchestrator.AudioMixer")
@patch("orchestrator.VideoProducer")
@patch("orchestrator.ScriptGenerator")
@patch("orchestrator.GSheetReader")
def test_run_pipeline_sets_status_generating_before_script(
    MockReader, MockScript, MockVideo, MockAudio, MockYouTube
):
    mock_reader = MockReader.return_value
    mock_reader.get_pending_row.return_value = {
        "row_index": 2, "title": "T", "story_brief": "b", "genre": "blend", "duration_sec": 75
    }
    MockScript.return_value.generate.return_value = SCRIPT_RESULT
    MockVideo.return_value.produce.return_value = "/tmp/stitched.mp4"
    MockAudio.return_value.mix.return_value = "/tmp/final.mp4"
    MockYouTube.return_value.upload.return_value = "https://youtube.com/watch?v=xyz"

    from orchestrator import run_pipeline
    run_pipeline()

    status_calls = [c.args[1] for c in mock_reader.update_status.call_args_list]
    assert status_calls == ["generating", "uploading"]


@patch("orchestrator.YouTubeUploader")
@patch("orchestrator.AudioMixer")
@patch("orchestrator.VideoProducer")
@patch("orchestrator.ScriptGenerator")
@patch("orchestrator.BriefGenerator")
@patch("orchestrator.GSheetReader")
def test_run_pipeline_generates_brief_when_no_pending(
    MockReader, MockBrief, MockScript, MockVideo, MockAudio, MockYouTube
):
    mock_reader = MockReader.return_value
    # First call returns None (no pending), second returns a row after brief was appended
    mock_reader.get_pending_row.side_effect = [
        None,
        {"row_index": 2, "title": "Static", "story_brief": "A ghost in the machine",
         "genre": "sci-fi", "duration_sec": 75}
    ]
    MockBrief.return_value.generate.return_value = {
        "story_brief": "A ghost in the machine",
        "genre": "sci-fi",
        "title_hint": "Static",
    }
    MockScript.return_value.generate.return_value = {
        "narrative": "In the void...", "title": "Static",
        "description": "desc", "tags": ["scifi"], "shots": ["shot1"],
    }
    MockVideo.return_value.produce.return_value = "/tmp/stitched.mp4"
    MockAudio.return_value.mix.return_value = "/tmp/final.mp4"
    MockYouTube.return_value.upload.return_value = "https://youtube.com/watch?v=xyz"

    from orchestrator import run_pipeline
    result = run_pipeline()

    MockBrief.return_value.generate.assert_called_once()
    mock_reader.append_pending_row.assert_called_once()
    assert result["status"] == "done"

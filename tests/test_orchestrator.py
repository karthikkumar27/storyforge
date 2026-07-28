# tests/test_orchestrator.py
import pytest
from unittest.mock import patch

from config import GENRES, STORY_MODE, SERIES_PARTS
from modules.preset import active_preset
from modules.episode_ledger import EpisodeLedger, LedgerSpec
from modules.sheet_access import SheetTab
from tests.support import CountingSheet

# run_pipeline() branches to a completely different flow for presets that
# generate a whole video in one call (preset-8). These tests exercise the
# shot-assembly flow, so skip them rather than assert nonsense under preset-8.
requires_shot_pipeline = pytest.mark.skipif(
    active_preset().is_single_shot_native,
    reason="active preset uses the single-shot native flow",
)

HEADERS = [
    "title", "story_brief", "script_text", "ref_image_url", "genre", "series_id",
    "part_number", "story_mode", "duration_sec", "status", "youtube_url",
    "error_msg", "arc_number", "episode_number", "character_form",
]

SPEC = LedgerSpec(
    genres=tuple(GENRES), story_mode=STORY_MODE, series_parts=SERIES_PARTS,
)

SCRIPT_RESULT = {
    "narrative": "In the void...",
    "title": "The Ghost Signal",
    "description": "desc",
    "tags": ["scifi"],
    "shots": ["shot1", "shot2", "shot3"],
}


def _row(**overrides):
    row = {h: "" for h in HEADERS}
    row["duration_sec"] = 75
    row["genre"] = GENRES[0]
    row.update(overrides)
    return row


def _ledger(rows, headers=HEADERS):
    """A real EpisodeLedger over an in-memory sheet.

    These tests cross the same seam run_pipeline() does, so assertions are about
    what ended up in the ledger rather than which methods were called on a mock.
    """
    raw = CountingSheet(rows, headers=headers)
    return EpisodeLedger(SheetTab(raw), SPEC), raw


def _wire_audio(mock_audio):
    """The orchestrator picks mix() or mix_with_native_audio() based on the
    preset's audio_mix config. Wire both so these tests don't depend on which."""
    mock_audio.return_value.mix.return_value = "/tmp/final.mp4"
    mock_audio.return_value.mix_with_native_audio.return_value = "/tmp/final.mp4"


@requires_shot_pipeline
@patch("orchestrator.YouTubeUploader")
@patch("orchestrator.AudioMixer")
@patch("orchestrator.create_video_producer")
@patch("orchestrator.ScriptGenerator")
@patch("orchestrator.get_episode_ledger")
def test_run_pipeline_publishes_and_records_the_url(
    MockLedger, MockScript, MockVideo, MockAudio, MockYouTube
):
    ledger, raw = _ledger([_row(title="Test", story_brief="A ghost astronaut",
                                status="pending")])
    MockLedger.return_value = ledger
    MockScript.return_value.generate.return_value = SCRIPT_RESULT
    MockVideo.return_value.produce.return_value = "/tmp/stitched.mp4"
    _wire_audio(MockAudio)
    MockYouTube.return_value.upload.return_value = "https://youtube.com/watch?v=abc"

    from orchestrator import run_pipeline
    result = run_pipeline()

    assert result == {"status": "done", "youtube_url": "https://youtube.com/watch?v=abc"}
    _, records = raw.read_all()
    assert records[0]["status"] == "done"
    assert records[0]["youtube_url"] == "https://youtube.com/watch?v=abc"
    assert records[0]["script_text"] == "In the void..."


@requires_shot_pipeline
@patch("orchestrator.BriefGenerator")
@patch("orchestrator.get_episode_ledger")
def test_run_pipeline_reports_no_pending_when_the_brief_cannot_be_claimed(
    MockLedger, MockBrief
):
    # A sheet with no status column: the appended row can't be marked pending,
    # so there is still nothing to claim afterwards.
    ledger, _ = _ledger([], headers=["title", "story_brief", "genre"])
    MockLedger.return_value = ledger
    MockBrief.return_value.generate.return_value = {
        "story_brief": "A ghost in the machine",
        "genre": GENRES[0],
        "title_hint": "Static",
    }

    from orchestrator import run_pipeline
    result = run_pipeline()

    assert result["status"] == "no_pending_rows"


@requires_shot_pipeline
@patch("orchestrator.YouTubeUploader")
@patch("orchestrator.AudioMixer")
@patch("orchestrator.create_video_producer")
@patch("orchestrator.ScriptGenerator")
@patch("orchestrator.get_episode_ledger")
def test_run_pipeline_records_the_error_breadcrumb_on_failure(
    MockLedger, MockScript, MockVideo, MockAudio, MockYouTube
):
    ledger, raw = _ledger([_row(story_brief="b", status="pending")])
    MockLedger.return_value = ledger
    MockScript.return_value.generate.side_effect = RuntimeError("Claude API down")

    from orchestrator import run_pipeline
    with pytest.raises(RuntimeError, match="Claude API down"):
        run_pipeline()

    _, records = raw.read_all()
    assert records[0]["status"] == "error"
    assert records[0]["error_msg"] == "Claude API down"


@requires_shot_pipeline
@patch("orchestrator.YouTubeUploader")
@patch("orchestrator.AudioMixer")
@patch("orchestrator.create_video_producer")
@patch("orchestrator.ScriptGenerator")
@patch("orchestrator.get_episode_ledger")
def test_status_is_generating_in_the_sheet_before_the_script_is_written(
    MockLedger, MockScript, MockVideo, MockAudio, MockYouTube
):
    ledger, raw = _ledger([_row(story_brief="b", status="pending")])
    MockLedger.return_value = ledger

    seen = {}

    def capture_status_then_generate(*args, **kwargs):
        # Status transitions flush immediately, so by the time the script
        # generator runs the sheet must already say "generating".
        _, records = raw.read_all()
        seen["status"] = records[0]["status"]
        return SCRIPT_RESULT

    MockScript.return_value.generate.side_effect = capture_status_then_generate
    MockVideo.return_value.produce.return_value = "/tmp/stitched.mp4"
    _wire_audio(MockAudio)
    MockYouTube.return_value.upload.return_value = "https://youtube.com/watch?v=xyz"

    from orchestrator import run_pipeline
    run_pipeline()

    assert seen["status"] == "generating"


@requires_shot_pipeline
@patch("orchestrator.YouTubeUploader")
@patch("orchestrator.AudioMixer")
@patch("orchestrator.create_video_producer")
@patch("orchestrator.ScriptGenerator")
@patch("orchestrator.BriefGenerator")
@patch("orchestrator.get_episode_ledger")
def test_run_pipeline_writes_a_brief_when_the_ledger_has_no_work(
    MockLedger, MockBrief, MockScript, MockVideo, MockAudio, MockYouTube
):
    ledger, raw = _ledger([])
    MockLedger.return_value = ledger
    MockBrief.return_value.generate.return_value = {
        "story_brief": "A ghost in the machine",
        "genre": GENRES[0],
        "title_hint": "Static",
    }
    MockScript.return_value.generate.return_value = SCRIPT_RESULT
    MockVideo.return_value.produce.return_value = "/tmp/stitched.mp4"
    _wire_audio(MockAudio)
    MockYouTube.return_value.upload.return_value = "https://youtube.com/watch?v=xyz"

    from orchestrator import run_pipeline
    result = run_pipeline()

    MockBrief.return_value.generate.assert_called_once()
    assert raw.appends == 1
    _, records = raw.read_all()
    assert records[0]["story_brief"] == "A ghost in the machine"
    assert records[0]["title"] == "Static"
    assert records[0]["status"] == "done"
    assert result["status"] == "done"


@requires_shot_pipeline
@patch("orchestrator.YouTubeUploader")
@patch("orchestrator.AudioMixer")
@patch("orchestrator.create_video_producer")
@patch("orchestrator.ScriptGenerator")
@patch("orchestrator.get_episode_ledger")
def test_a_full_run_reads_the_sheet_once(
    MockLedger, MockScript, MockVideo, MockAudio, MockYouTube
):
    ledger, raw = _ledger([_row(story_brief="b", status="pending")])
    MockLedger.return_value = ledger
    MockScript.return_value.generate.return_value = SCRIPT_RESULT
    MockVideo.return_value.produce.return_value = "/tmp/stitched.mp4"
    _wire_audio(MockAudio)
    MockYouTube.return_value.upload.return_value = "https://youtube.com/watch?v=xyz"

    from orchestrator import run_pipeline
    run_pipeline()

    assert raw.reads == 1
    assert raw.write_batches == 3   # generating, uploading (+buffered), done

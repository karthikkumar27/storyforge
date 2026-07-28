# tests/test_orchestrator.py
from dataclasses import replace

import pytest

from config import GENRES, STORY_MODE, SERIES_PARTS
from modules.preset import active_preset
from modules.episode_ledger import EpisodeLedger, LedgerSpec
from modules.sheet_access import SheetTab
from orchestrator import Deps, run_pipeline
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


# -- fakes --------------------------------------------------------------------

class FakeGenerator:
    """Stands in for BriefGenerator / ScriptGenerator."""

    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def __call__(self, session):        # Deps holds factories, not instances
        return self

    def generate(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.error:
            raise self.error
        return self.result


class FakeVideoProducer:
    def __init__(self, path="/tmp/stitched.mp4"):
        self.path = path
        self.calls = []

    def __call__(self):
        return self

    def produce(self, shots, **kwargs):
        self.calls.append((shots, kwargs))
        return self.path


class FakeAudioMixer:
    def __init__(self, path="/tmp/final.mp4"):
        self.path = path

    def __call__(self):
        return self

    # The orchestrator picks one of these based on the preset's audio_mix config.
    def mix(self, *args, **kwargs):
        return self.path

    def mix_with_native_audio(self, *args, **kwargs):
        return self.path


class FakeUploader:
    def __init__(self, url="https://youtube.com/watch?v=abc", error=None):
        self.url = url
        self.error = error
        self.uploads = []

    def __call__(self):
        return self

    def upload(self, path, script_result):
        self.uploads.append((path, script_result))
        if self.error:
            raise self.error
        return self.url


class FakeCharactersReader:
    available = False

    def __call__(self, session):
        return self

    def get_main_ref_image_for_form(self, form):
        return None


def _deps(rows, *, headers=HEADERS, brief=None, script=None, uploader=None, **overrides):
    """Real ledger over an in-memory sheet, fakes for everything that costs money."""
    raw = CountingSheet(rows, headers=headers)
    ledger = EpisodeLedger(SheetTab(raw), SPEC)

    fields = {
        "session": None,                       # fakes ignore it
        "ledger": lambda _session: ledger,
        "brief_generator": brief or FakeGenerator({"story_brief": "b", "genre": GENRES[0]}),
        "script_generator": script or FakeGenerator(SCRIPT_RESULT),
        "characters": FakeCharactersReader(),
        "video_producer": FakeVideoProducer(),
        "audio_mixer": FakeAudioMixer(),
        "uploader": uploader or FakeUploader(),
        "storyboards": lambda shots, ref, **kw: [None] * len(shots),
    }
    fields.update(overrides)
    return Deps(**fields), raw


# -- the happy path -----------------------------------------------------------

@requires_shot_pipeline
def test_run_pipeline_publishes_and_records_the_url():
    deps, raw = _deps([_row(title="Test", story_brief="A ghost astronaut", status="pending")])

    result = run_pipeline(deps)

    assert result == {"status": "done", "youtube_url": "https://youtube.com/watch?v=abc"}
    _, records = raw.read_all()
    assert records[0]["status"] == "done"
    assert records[0]["youtube_url"] == "https://youtube.com/watch?v=abc"
    assert records[0]["script_text"] == "In the void..."


@requires_shot_pipeline
def test_the_script_is_generated_from_the_claimed_episode():
    script = FakeGenerator(SCRIPT_RESULT)
    deps, _ = _deps(
        [_row(story_brief="A ghost astronaut", genre=GENRES[0], status="pending")],
        script=script,
    )

    run_pipeline(deps)

    (brief, genre), _kwargs = script.calls[0]
    assert brief == "A ghost astronaut"
    assert genre == GENRES[0]


@requires_shot_pipeline
def test_the_producer_receives_the_scripts_shots():
    producer = FakeVideoProducer()
    deps, _ = _deps([_row(story_brief="b", status="pending")], video_producer=producer)

    run_pipeline(deps)

    shots, _kwargs = producer.calls[0]
    assert shots == SCRIPT_RESULT["shots"]


# -- claiming and brief writing ----------------------------------------------

@requires_shot_pipeline
def test_run_pipeline_writes_a_brief_when_the_ledger_has_no_work():
    brief = FakeGenerator({
        "story_brief": "A ghost in the machine",
        "genre": GENRES[0],
        "title_hint": "Static",
    })
    deps, raw = _deps([], brief=brief)

    result = run_pipeline(deps)

    assert len(brief.calls) == 1
    assert raw.appends == 1
    _, records = raw.read_all()
    assert records[0]["story_brief"] == "A ghost in the machine"
    assert records[0]["title"] == "Static"
    assert result["status"] == "done"


@requires_shot_pipeline
def test_run_pipeline_reports_no_pending_when_the_brief_cannot_be_claimed():
    # A sheet with no status column: the appended row can't be marked pending,
    # so there is still nothing to claim afterwards.
    deps, _ = _deps([], headers=["title", "story_brief", "genre"])

    assert run_pipeline(deps)["status"] == "no_pending_rows"


@requires_shot_pipeline
def test_an_existing_pending_row_is_used_without_writing_a_brief():
    brief = FakeGenerator({"story_brief": "unused", "genre": GENRES[0]})
    deps, _ = _deps([_row(story_brief="already here", status="pending")], brief=brief)

    run_pipeline(deps)

    assert brief.calls == []


# -- failure -----------------------------------------------------------------

@requires_shot_pipeline
def test_run_pipeline_records_the_error_breadcrumb_on_failure():
    deps, raw = _deps(
        [_row(story_brief="b", status="pending")],
        script=FakeGenerator(error=RuntimeError("Claude API down")),
    )

    with pytest.raises(RuntimeError, match="Claude API down"):
        run_pipeline(deps)

    _, records = raw.read_all()
    assert records[0]["status"] == "error"
    assert records[0]["error_msg"] == "Claude API down"


@requires_shot_pipeline
def test_a_failed_upload_is_recorded_too():
    """The video already cost ~$1.10 by this point, so the breadcrumb matters."""
    deps, raw = _deps(
        [_row(story_brief="b", status="pending")],
        uploader=FakeUploader(error=RuntimeError("invalid_grant")),
    )

    with pytest.raises(RuntimeError, match="invalid_grant"):
        run_pipeline(deps)

    _, records = raw.read_all()
    assert records[0]["status"] == "error"
    assert "invalid_grant" in records[0]["error_msg"]


# -- ordering and cost --------------------------------------------------------

@requires_shot_pipeline
def test_status_is_generating_in_the_sheet_before_the_script_is_written():
    deps, raw = _deps([_row(story_brief="b", status="pending")])
    seen = {}

    class WatchingGenerator(FakeGenerator):
        def generate(self, *args, **kwargs):
            # Status transitions flush immediately, so by the time the script
            # generator runs the sheet must already say "generating".
            _, records = raw.read_all()
            seen["status"] = records[0]["status"]
            return SCRIPT_RESULT

    deps.script_generator = WatchingGenerator(SCRIPT_RESULT)

    run_pipeline(deps)

    assert seen["status"] == "generating"


@requires_shot_pipeline
def test_nothing_is_uploaded_when_the_script_fails():
    uploader = FakeUploader()
    deps, _ = _deps(
        [_row(story_brief="b", status="pending")],
        script=FakeGenerator(error=RuntimeError("boom")),
        uploader=uploader,
    )

    with pytest.raises(RuntimeError):
        run_pipeline(deps)

    assert uploader.uploads == []


@requires_shot_pipeline
def test_a_full_run_reads_the_sheet_once():
    deps, raw = _deps([_row(story_brief="b", status="pending")])

    run_pipeline(deps)

    assert raw.reads == 1
    assert raw.write_batches == 3   # generating, uploading (+buffered), done


# -- audio routing ------------------------------------------------------------

@requires_shot_pipeline
def test_a_native_only_preset_never_calls_the_audio_mixer(monkeypatch):
    """preset-9 has no narration — the model's own audio is the soundtrack, and
    the stitched file must reach YouTube without an audio re-encode."""
    import orchestrator
    # Preset is frozen, so swap the whole value rather than a field.
    monkeypatch.setattr(
        orchestrator, "_preset",
        replace(orchestrator._preset, audio_mix={"mode": "native_only"}),
    )

    class ExplodingMixer:
        def __call__(self):
            raise AssertionError("the audio mixer must not run for native_only")

    uploader = FakeUploader()
    deps, _ = _deps(
        [_row(story_brief="b", status="pending")],
        uploader=uploader,
        audio_mixer=ExplodingMixer(),
    )

    result = run_pipeline(deps)

    assert result["status"] == "done"
    # the file handed to YouTube is the stitched video, untouched
    assert uploader.uploads[0][0] == "/tmp/stitched.mp4"


@requires_shot_pipeline
def test_a_narration_preset_still_mixes(monkeypatch):
    import orchestrator
    monkeypatch.setattr(
        orchestrator, "_preset",
        replace(orchestrator._preset, audio_mix={"mode": "narration_over_native"}),
    )
    uploader = FakeUploader()
    deps, _ = _deps([_row(story_brief="b", status="pending")], uploader=uploader)

    run_pipeline(deps)

    assert uploader.uploads[0][0] == "/tmp/final.mp4"

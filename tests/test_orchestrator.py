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
    "character_appearance",
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

    def get_main_appearance_for_form(self, form):
        return None


class FakeImageGenerator:
    """Stands in for the reference-image generator (Deps.image_generator)."""

    def __init__(self, url="https://cdn/fresh.png"):
        self.url = url
        self.calls = []

    def __call__(self):
        return self

    def generate(self, prompt):
        self.calls.append(prompt)
        return self.url


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


# -- storyboard routing -------------------------------------------------------
#
# The only production wiring for chained reference frames. A regression here
# silently reverts preset-9 to the drift it was built to fix.

def _explodes(what):
    def boom(*_args, **_kwargs):
        raise AssertionError(f"{what} must not run")
    return boom


@requires_shot_pipeline
def test_a_chaining_preset_hands_produce_a_supplier_not_a_url_list(monkeypatch):
    import orchestrator
    monkeypatch.setattr(
        orchestrator, "_preset",
        replace(
            orchestrator._preset,
            per_shot_storyboards=True,
            chain_reference_frames=True,
            default_ref_image="https://cdn/ref.png",
        ),
    )
    supplier = object()
    built = []
    producer = FakeVideoProducer()

    deps, _ = _deps(
        [_row(story_brief="b", status="pending")],
        video_producer=producer,
        storyboards=_explodes("the batch storyboard builder"),
        chained_storyboards=lambda ref, **kw: built.append((ref, kw)) or supplier,
    )

    run_pipeline(deps)

    assert built and built[0][0] == "https://cdn/ref.png"
    _shots, kwargs = producer.calls[0]
    assert kwargs["storyboard_supplier"] is supplier
    assert kwargs["storyboard_urls"] is None


@requires_shot_pipeline
def test_a_non_chaining_preset_still_builds_storyboards_up_front(monkeypatch):
    import orchestrator
    monkeypatch.setattr(
        orchestrator, "_preset",
        replace(
            orchestrator._preset,
            per_shot_storyboards=True,
            chain_reference_frames=False,
            default_ref_image="https://cdn/ref.png",
        ),
    )
    producer = FakeVideoProducer()

    deps, _ = _deps(
        [_row(story_brief="b", status="pending")],
        video_producer=producer,
        storyboards=lambda shots, ref, **kw: [f"https://cdn/sb{i}.png" for i in range(len(shots))],
        chained_storyboards=_explodes("the chained storyboard supplier"),
    )

    run_pipeline(deps)

    _shots, kwargs = producer.calls[0]
    assert kwargs["storyboard_supplier"] is None
    assert kwargs["storyboard_urls"] == [
        "https://cdn/sb0.png", "https://cdn/sb1.png", "https://cdn/sb2.png",
    ]


# -- the locked appearance reaches the storyboard builders --------------------

@requires_shot_pipeline
def test_a_canon_preset_takes_the_appearance_from_the_characters_sheet(monkeypatch):
    """preset-7's locked paragraph is canon and stable across 200 episodes, so
    it beats the per-episode character_image_prompt."""
    import orchestrator
    monkeypatch.setattr(
        orchestrator, "_preset",
        replace(
            orchestrator._preset,
            serialized_canon=True,
            per_shot_storyboards=True,
            chain_reference_frames=False,
        ),
    )

    class Chars:
        available = True
        def __call__(self, session):
            return self
        def get_main_ref_image_for_form(self, form):
            return "https://cdn/zenith.png"
        def get_main_appearance_for_form(self, form):
            return "LOCKED PARAGRAPH FROM THE SHEET"

    seen = {}
    deps, _ = _deps(
        [_row(story_brief="b", status="pending")],
        script=FakeGenerator({**SCRIPT_RESULT,
                              "character_image_prompt": "GENERATED CHARACTER PROMPT"}),
        characters=Chars(),
        storyboards=lambda shots, ref, **kw: seen.update(kw) or [None] * len(shots),
        chained_storyboards=_explodes("the chained storyboard supplier"),
    )

    run_pipeline(deps)

    assert seen["appearance"] == "LOCKED PARAGRAPH FROM THE SHEET"


@requires_shot_pipeline
def test_a_non_canon_preset_takes_the_appearance_from_the_script(monkeypatch):
    """The script's prompt is trustworthy as the appearance only when THIS run
    is the one that used it to generate the reference image."""
    import orchestrator
    monkeypatch.setattr(
        orchestrator, "_preset",
        replace(
            orchestrator._preset,
            serialized_canon=False,
            per_shot_storyboards=True,
            chain_reference_frames=False,
            default_ref_image=None,
        ),
    )
    seen = {}
    deps, _ = _deps(
        [_row(story_brief="b", status="pending")],
        script=FakeGenerator({**SCRIPT_RESULT,
                              "character_image_prompt": "GENERATED CHARACTER PROMPT"}),
        image_generator=FakeImageGenerator(),
        storyboards=lambda shots, ref, **kw: seen.update(kw) or [None] * len(shots),
        chained_storyboards=_explodes("the chained storyboard supplier"),
    )

    run_pipeline(deps)

    assert seen["appearance"] == "GENERATED CHARACTER PROMPT"


@requires_shot_pipeline
def test_a_non_canon_preset_never_consults_the_characters_sheet_for_appearance(monkeypatch):
    """Guards the serialized_canon check itself. A Chars fake that *does* have
    an answer must still lose to the script's prompt on a non-canon preset --
    otherwise preset-7's Alan/Zenith paragraph would leak into preset-1/2/3/9
    runs whenever a characters sheet happens to be configured."""
    import orchestrator
    monkeypatch.setattr(
        orchestrator, "_preset",
        replace(
            orchestrator._preset,
            serialized_canon=False,
            per_shot_storyboards=True,
            chain_reference_frames=False,
            default_ref_image=None,
        ),
    )

    class Chars:
        available = True
        def __call__(self, session):
            return self
        def get_main_ref_image_for_form(self, form):
            return "https://cdn/zenith.png"
        def get_main_appearance_for_form(self, form):
            return "SHOULD NEVER BE SEEN"

    seen = {}
    deps, _ = _deps(
        [_row(story_brief="b", status="pending")],
        script=FakeGenerator({**SCRIPT_RESULT,
                              "character_image_prompt": "GENERATED CHARACTER PROMPT"}),
        characters=Chars(),
        image_generator=FakeImageGenerator(),
        storyboards=lambda shots, ref, **kw: seen.update(kw) or [None] * len(shots),
        chained_storyboards=_explodes("the chained storyboard supplier"),
    )

    run_pipeline(deps)

    assert seen["appearance"] == "GENERATED CHARACTER PROMPT"


@requires_shot_pipeline
def test_a_canon_preset_falls_back_to_the_script_when_the_sheet_is_empty(monkeypatch):
    """A roster row with no appearance paragraph must not blank the prompt --
    as long as this run is the one that generated the image the prompt
    describes."""
    import orchestrator
    monkeypatch.setattr(
        orchestrator, "_preset",
        replace(
            orchestrator._preset,
            serialized_canon=True,
            per_shot_storyboards=True,
            chain_reference_frames=False,
            default_ref_image=None,
        ),
    )

    class EmptyChars:
        available = True
        def __call__(self, session):
            return self
        def get_main_ref_image_for_form(self, form):
            return None
        def get_main_appearance_for_form(self, form):
            return None

    seen = {}
    deps, _ = _deps(
        [_row(story_brief="b", status="pending")],
        script=FakeGenerator({**SCRIPT_RESULT,
                              "character_image_prompt": "GENERATED CHARACTER PROMPT"}),
        characters=EmptyChars(),
        image_generator=FakeImageGenerator(),
        storyboards=lambda shots, ref, **kw: seen.update(kw) or [None] * len(shots),
        chained_storyboards=_explodes("the chained storyboard supplier"),
    )

    run_pipeline(deps)

    assert seen["appearance"] == "GENERATED CHARACTER PROMPT"


@requires_shot_pipeline
def test_a_chaining_preset_also_receives_the_appearance(monkeypatch):
    import orchestrator
    monkeypatch.setattr(
        orchestrator, "_preset",
        replace(
            orchestrator._preset,
            serialized_canon=False,
            per_shot_storyboards=True,
            chain_reference_frames=True,
            default_ref_image=None,
        ),
    )
    seen = {}

    class SpySupplier:
        def frame_for(self, index, shot_prompt, previous_clip):
            return None

    deps, _ = _deps(
        [_row(story_brief="b", status="pending")],
        script=FakeGenerator({**SCRIPT_RESULT,
                              "character_image_prompt": "GENERATED CHARACTER PROMPT"}),
        image_generator=FakeImageGenerator(),
        storyboards=_explodes("the batch storyboard builder"),
        chained_storyboards=lambda ref, **kw: seen.update(kw) or SpySupplier(),
    )

    run_pipeline(deps)

    assert seen["appearance"] == "GENERATED CHARACTER PROMPT"


# -- the appearance and the image it describes travel together as a pair -----
#
# A rerun's ScriptGenerator call is non-deterministic. If the pipeline only
# saved the reference image URL, a later rerun could pair a stable, saved
# image with a freshly-invented description -- text beats image on conflict,
# so newly-invented words would override the very image that was saved to
# keep the character stable. Saving the prompt beside the URL, and reading it
# back instead of trusting a fresh prompt, closes that gap.

@requires_shot_pipeline
def test_generating_a_fresh_reference_image_saves_its_prompt_alongside_it(monkeypatch):
    import orchestrator
    monkeypatch.setattr(
        orchestrator, "_preset",
        replace(orchestrator._preset, serialized_canon=False, default_ref_image=None),
    )
    image_gen = FakeImageGenerator(url="https://cdn/fresh.png")
    deps, raw = _deps(
        [_row(story_brief="b", status="pending")],
        script=FakeGenerator({**SCRIPT_RESULT, "character_image_prompt": "FRESH PROMPT"}),
        image_generator=image_gen,
    )

    run_pipeline(deps)

    assert image_gen.calls == ["FRESH PROMPT"]
    _, records = raw.read_all()
    assert records[0]["ref_image_url"] == "https://cdn/fresh.png"
    assert records[0]["character_appearance"] == "FRESH PROMPT"


@requires_shot_pipeline
def test_a_reused_image_takes_the_appearance_from_the_sheet_not_a_fresh_prompt(monkeypatch):
    """The reference image is reused (not generated this run), so the sheet's
    saved character_appearance -- which matches that image by construction --
    must win, even though the script generated a different, unrelated prompt
    this time around."""
    import orchestrator
    monkeypatch.setattr(
        orchestrator, "_preset",
        replace(
            orchestrator._preset,
            serialized_canon=False,
            per_shot_storyboards=True,
            chain_reference_frames=False,
            default_ref_image="https://cdn/ref.png",
        ),
    )
    seen = {}
    deps, _ = _deps(
        [_row(story_brief="b", status="pending", character_appearance="SHEET SENTINEL")],
        script=FakeGenerator({**SCRIPT_RESULT, "character_image_prompt": "SCRIPT SENTINEL"}),
        storyboards=lambda shots, ref, **kw: seen.update(kw) or [None] * len(shots),
        chained_storyboards=_explodes("the chained storyboard supplier"),
    )

    run_pipeline(deps)

    assert seen["appearance"] == "SHEET SENTINEL"


@requires_shot_pipeline
def test_a_reused_image_with_no_saved_appearance_injects_nothing(monkeypatch):
    """No appearance was ever saved for this reused image, and this run did
    not generate it -- the fresh script prompt must NOT be used as a
    stand-in, because it describes nothing about this particular image."""
    import orchestrator
    monkeypatch.setattr(
        orchestrator, "_preset",
        replace(
            orchestrator._preset,
            serialized_canon=False,
            per_shot_storyboards=True,
            chain_reference_frames=False,
            default_ref_image="https://cdn/ref.png",
        ),
    )
    seen = {}
    deps, _ = _deps(
        [_row(story_brief="b", status="pending", character_appearance="")],
        script=FakeGenerator({**SCRIPT_RESULT, "character_image_prompt": "SCRIPT SENTINEL"}),
        storyboards=lambda shots, ref, **kw: seen.update(kw) or [None] * len(shots),
        chained_storyboards=_explodes("the chained storyboard supplier"),
    )

    run_pipeline(deps)

    assert seen["appearance"] is None


@requires_shot_pipeline
def test_a_canon_preset_beats_both_the_saved_appearance_and_the_fresh_prompt(monkeypatch):
    import orchestrator
    monkeypatch.setattr(
        orchestrator, "_preset",
        replace(
            orchestrator._preset,
            serialized_canon=True,
            per_shot_storyboards=True,
            chain_reference_frames=False,
        ),
    )

    class Chars:
        available = True
        def __call__(self, session):
            return self
        def get_main_ref_image_for_form(self, form):
            return "https://cdn/zenith.png"
        def get_main_appearance_for_form(self, form):
            return "CANON SENTINEL"

    seen = {}
    deps, _ = _deps(
        [_row(story_brief="b", status="pending", character_appearance="SHEET SENTINEL")],
        script=FakeGenerator({**SCRIPT_RESULT, "character_image_prompt": "SCRIPT SENTINEL"}),
        characters=Chars(),
        storyboards=lambda shots, ref, **kw: seen.update(kw) or [None] * len(shots),
        chained_storyboards=_explodes("the chained storyboard supplier"),
    )

    run_pipeline(deps)

    assert seen["appearance"] == "CANON SENTINEL"

# tests/modules/test_episode_ledger.py
import pytest

from modules.episode_ledger import EpisodeLedger, LedgerSpec
from modules.sheet_access import SheetTab
from tests.support import CountingSheet

HEADERS = [
    "title", "story_brief", "script_text", "ref_image_url", "genre", "series_id",
    "part_number", "story_mode", "duration_sec", "status", "youtube_url",
    "error_msg", "arc_number", "episode_number", "character_form",
]

SERIES_SPEC = LedgerSpec(
    genres=("sci-fi", "space"), story_mode="series", series_parts=3,
)
ZENITH_SPEC = LedgerSpec(
    genres=("origin-story",), story_mode="series", series_parts=999,
    tracks_episode_numbers=True,
)
STANDALONE_SPEC = LedgerSpec(
    genres=("sci-fi",), story_mode="standalone", series_parts=1,
)


def _row(**overrides):
    row = {h: "" for h in HEADERS}
    row["duration_sec"] = 75
    row.update(overrides)
    return row


def _ledger(rows, spec=SERIES_SPEC):
    raw = CountingSheet(rows, headers=HEADERS)
    return EpisodeLedger(SheetTab(raw), spec), raw


# -- claiming -----------------------------------------------------------------

def test_claim_next_returns_the_first_pending_episode():
    ledger, _ = _ledger([
        _row(title="Done", story_brief="old", genre="sci-fi", status="done"),
        _row(title="Next", story_brief="new", genre="space", status="pending"),
    ])

    claim = ledger.claim_next()

    assert not claim.needs_brief
    assert claim.episode.row_index == 3          # header is row 1
    assert claim.episode.story_brief == "new"
    assert claim.episode.genre == "space"


def test_claim_next_defaults_fields_whose_columns_are_absent():
    # The fallbacks fire only when a column doesn't exist at all -- gspread
    # populates every header, so an empty cell reads as "" and stays "".
    raw = CountingSheet(
        [{"story_brief": "b", "status": "pending"}],
        headers=["story_brief", "status"],
    )
    ledger = EpisodeLedger(SheetTab(raw), SERIES_SPEC)

    episode = ledger.claim_next().episode

    assert episode.genre == "blend"
    assert episode.duration_sec == 75
    assert episode.story_mode == "standalone"


def test_an_empty_cell_stays_empty_rather_than_taking_the_default():
    ledger, _ = _ledger([_row(story_brief="b", status="pending", genre="")])

    assert ledger.claim_next().episode.genre == ""


def test_claim_next_asks_for_a_brief_when_nothing_is_pending():
    ledger, _ = _ledger([
        _row(title="Done", story_brief="old", genre="sci-fi", status="done"),
    ])

    claim = ledger.claim_next()

    assert claim.needs_brief
    assert claim.episode is None
    assert claim.brief_context is not None


def test_brief_context_offers_past_stories_of_this_presets_genres_only():
    ledger, _ = _ledger([
        _row(title="Mine", story_brief="a", genre="sci-fi", status="done"),
        _row(title="Other preset", story_brief="b", genre="lullaby", status="done"),
        _row(title="Unfinished", story_brief="c", genre="sci-fi", status="error"),
    ])

    stories = ledger.claim_next().brief_context.past_stories

    assert [s["title"] for s in stories] == ["Mine"]


def test_brief_context_caps_past_stories_at_twenty_most_recent():
    rows = [
        _row(title=f"Ep{i}", story_brief=f"b{i}", genre="sci-fi", status="done")
        for i in range(30)
    ]
    ledger, _ = _ledger(rows)

    stories = ledger.claim_next().brief_context.past_stories

    assert len(stories) == 20
    assert stories[-1]["title"] == "Ep29"


def test_brief_context_carries_previous_parts_of_an_incomplete_series():
    ledger, _ = _ledger([
        _row(story_brief="p1", genre="sci-fi", status="done",
             series_id="s1", part_number=1),
        _row(story_brief="p2", genre="sci-fi", status="done",
             series_id="s1", part_number=2),
    ])

    parts = ledger.claim_next().brief_context.previous_parts

    assert [p["story_brief"] for p in parts] == ["p1", "p2"]


def test_brief_context_starts_a_new_series_once_the_last_one_completed():
    # series_parts=3, and s1 already has 3 done parts
    ledger, _ = _ledger([
        _row(story_brief=f"p{i}", genre="sci-fi", status="done",
             series_id="s1", part_number=i)
        for i in (1, 2, 3)
    ])

    assert ledger.claim_next().brief_context.previous_parts == []


def test_brief_context_ignores_series_from_another_presets_genres():
    ledger, _ = _ledger([
        _row(story_brief="p1", genre="lullaby", status="done",
             series_id="kids-1", part_number=1),
    ])

    assert ledger.claim_next().brief_context.previous_parts == []


def test_standalone_presets_get_no_previous_parts():
    ledger, _ = _ledger([
        _row(story_brief="p1", genre="sci-fi", status="done",
             series_id="s1", part_number=1),
    ], spec=STANDALONE_SPEC)

    assert ledger.claim_next().brief_context.previous_parts == []


# -- episode numbering --------------------------------------------------------

def test_episode_number_is_absent_unless_the_preset_tracks_it():
    ledger, _ = _ledger([_row(genre="sci-fi", status="done", episode_number=4)])

    assert ledger.claim_next().brief_context.episode_number is None


def test_episode_number_is_one_past_the_highest_seen():
    ledger, _ = _ledger([
        _row(genre="origin-story", status="done", episode_number=1),
        _row(genre="origin-story", status="error", episode_number=3),
        _row(genre="origin-story", status="done", episode_number=2),
    ], spec=ZENITH_SPEC)

    assert ledger.claim_next().brief_context.episode_number == 4


def test_episode_number_starts_at_one_on_an_empty_ledger():
    ledger, _ = _ledger([], spec=ZENITH_SPEC)

    assert ledger.claim_next().brief_context.episode_number == 1


def test_episode_number_ignores_other_presets_rows():
    ledger, _ = _ledger([
        _row(genre="lullaby", status="done", episode_number=99),
        _row(genre="origin-story", status="done", episode_number=2),
    ], spec=ZENITH_SPEC)

    assert ledger.claim_next().brief_context.episode_number == 3


def test_episode_number_survives_a_non_numeric_cell():
    ledger, _ = _ledger([
        _row(genre="origin-story", status="done", episode_number="n/a"),
        _row(genre="origin-story", status="done", episode_number=5),
    ], spec=ZENITH_SPEC)

    assert ledger.claim_next().brief_context.episode_number == 6


def test_part_number_and_episode_number_diverge_after_an_error():
    """KNOWN DIVERGENCE, pinned deliberately.

    Part Number counts completed Episodes; Episode Number counts the highest
    seen. One errored Episode splits them permanently, and they never
    re-converge. Behaviour preserved verbatim from GSheetReader -- see the
    Episode Number / Part Number entries in CONTEXT.md. If this test starts
    failing, the divergence was fixed, and that is a behaviour change that
    needs its own commit and its own evidence.
    """
    ledger, _ = _ledger([
        _row(story_brief="p1", genre="origin-story", status="done",
             series_id="z", part_number=1, episode_number=1),
        _row(story_brief="p2", genre="origin-story", status="done",
             series_id="z", part_number=2, episode_number=2),
        _row(story_brief="p3", genre="origin-story", status="error",
             series_id="z", part_number=3, episode_number=3),
    ], spec=ZENITH_SPEC)

    ctx = ledger.claim_next().brief_context
    next_part_number = len(ctx.previous_parts) + 1   # how brief_generator derives it

    assert next_part_number == 3
    assert ctx.episode_number == 4
    assert next_part_number != ctx.episode_number


# -- starting work ------------------------------------------------------------

def test_start_appends_the_brief_and_claims_it():
    ledger, raw = _ledger([])

    claim = ledger.start({
        "title_hint": "Static",
        "story_brief": "A ghost in the machine",
        "genre": "sci-fi",
        "story_mode": "series",
        "series_id": "s1",
        "part_number": 1,
    })

    assert raw.appends == 1
    assert claim.episode is not None
    assert claim.episode.row_index == 2
    assert claim.episode.title == "Static"
    assert claim.episode.story_brief == "A ghost in the machine"
    assert claim.episode.duration_sec == 75


def test_start_marks_the_appended_row_pending():
    ledger, raw = _ledger([])

    ledger.start({"story_brief": "b", "genre": "sci-fi"})

    _, records = raw.read_all()
    assert records[0]["status"] == "pending"


def test_start_adds_the_arc_tracking_columns_when_missing():
    raw = CountingSheet([], headers=["title", "story_brief", "genre", "status"])
    ledger = EpisodeLedger(SheetTab(raw), ZENITH_SPEC)

    ledger.start({"story_brief": "b", "genre": "origin-story", "arc_number": 2})

    headers, records = raw.read_all()
    assert "arc_number" in headers
    assert "episode_number" in headers
    assert "character_form" in headers
    assert records[0]["arc_number"] == 2


# -- recording progress -------------------------------------------------------

def test_record_buffers_content_without_touching_the_sheet():
    ledger, raw = _ledger([_row(story_brief="b", status="pending")])

    ledger.record(2, script="the narration")
    ledger.record(2, ref_image_url="https://img")

    assert raw.write_batches == 0


def test_a_status_transition_flushes_everything_buffered_with_it():
    ledger, raw = _ledger([_row(story_brief="b", status="pending")])

    ledger.record(2, script="the narration")
    ledger.record(2, ref_image_url="https://img")
    ledger.record(2, status="uploading")

    assert raw.write_batches == 1
    assert raw.cells_written == 3
    _, records = raw.read_all()
    assert records[0]["script_text"] == "the narration"
    assert records[0]["ref_image_url"] == "https://img"
    assert records[0]["status"] == "uploading"


def test_record_with_nothing_to_say_does_nothing():
    ledger, raw = _ledger([_row(status="pending")])

    ledger.record(2)

    assert raw.write_batches == 0


def test_finish_publishes_immediately():
    ledger, raw = _ledger([_row(story_brief="b", status="pending")])

    ledger.finish(2, "https://youtu.be/abc")

    assert raw.write_batches == 1
    _, records = raw.read_all()
    assert records[0]["status"] == "done"
    assert records[0]["youtube_url"] == "https://youtu.be/abc"


def test_fail_records_the_breadcrumb_immediately():
    ledger, raw = _ledger([_row(story_brief="b", status="pending")])

    ledger.record(2, script="unflushed")
    ledger.fail(2, "Atlas timed out")

    assert raw.write_batches == 1
    _, records = raw.read_all()
    assert records[0]["status"] == "error"
    assert records[0]["error_msg"] == "Atlas timed out"
    # the buffered content rides along rather than being lost
    assert records[0]["script_text"] == "unflushed"


# -- direct lookups -----------------------------------------------------------

def test_row_fetches_by_sheet_position():
    ledger, _ = _ledger([
        _row(title="First", status="done"),
        _row(title="Second", status="done"),
    ])

    assert ledger.row(3)["title"] == "Second"


@pytest.mark.parametrize("bad_index", [1, 0, 4])
def test_row_rejects_positions_outside_the_sheet(bad_index):
    ledger, _ = _ledger([_row(title="Only", status="done")])

    with pytest.raises(IndexError, match="out of range"):
        ledger.row(bad_index)


def test_series_parts_are_ordered_by_part_number():
    ledger, _ = _ledger([
        _row(story_brief="c", status="done", series_id="s1", part_number=3),
        _row(story_brief="a", status="done", series_id="s1", part_number=1),
        _row(story_brief="b", status="done", series_id="s1", part_number=2),
        _row(story_brief="x", status="done", series_id="s2", part_number=1),
    ])

    assert [p["story_brief"] for p in ledger.series_parts("s1")] == ["a", "b", "c"]


def test_series_parts_excludes_incomplete_episodes():
    ledger, _ = _ledger([
        _row(story_brief="a", status="done", series_id="s1", part_number=1),
        _row(story_brief="b", status="pending", series_id="s1", part_number=2),
    ])

    assert [p["story_brief"] for p in ledger.series_parts("s1")] == ["a"]


# -- the headline claim -------------------------------------------------------

def test_a_full_episode_costs_three_round_trips():
    """The old GSheetReader spent ~20: five full-sheet reads, seven header
    re-reads (one per _col call), and five single-cell writes."""
    ledger, raw = _ledger([
        _row(story_brief="old", genre="sci-fi", status="done"),
        _row(story_brief="work", genre="sci-fi", status="pending"),
    ])

    claim = ledger.claim_next()                       # read
    row_index = claim.episode.row_index
    ledger.record(row_index, status="generating")     # write
    ledger.record(row_index, script="narration")      # buffered
    ledger.record(row_index, ref_image_url="https://img")   # buffered
    ledger.record(row_index, status="uploading")      # write (3 cells)
    ledger.finish(row_index, "https://youtu.be/abc")  # write

    assert raw.reads == 1
    assert raw.round_trips == 4

# tests/modules/test_sheet_access.py
import pytest

from modules.sheet_access import InMemorySheet, SheetSession, SheetTab
from tests.support import CountingSheet

ROWS = [
    {"title": "One", "story_brief": "first", "status": "done", "youtube_url": "u1"},
    {"title": "Two", "story_brief": "second", "status": "pending", "youtube_url": ""},
]


def test_in_memory_sheet_round_trips_rows():
    sheet = InMemorySheet(ROWS)
    headers, records = sheet.read_all()

    assert headers == ["title", "story_brief", "status", "youtube_url"]
    assert records[0]["title"] == "One"
    assert records[1]["status"] == "pending"


def test_tab_reads_the_sheet_once_however_many_queries():
    raw = CountingSheet(ROWS)
    tab = SheetTab(raw)

    tab.records
    tab.records
    tab.headers
    tab.column("status")
    tab.column("title")

    assert raw.reads == 1


def test_staged_writes_land_as_one_batch():
    raw = CountingSheet(ROWS)
    tab = SheetTab(raw)

    tab.stage(2, {"title": "Renamed"})
    tab.stage(2, {"status": "generating"})
    tab.stage(3, {"status": "error"})
    assert raw.write_batches == 0  # nothing sent yet

    tab.flush()

    assert raw.write_batches == 1
    assert raw.cells_written == 3
    _, records = raw.read_all()
    assert records[0]["title"] == "Renamed"
    assert records[0]["status"] == "generating"
    assert records[1]["status"] == "error"


def test_flush_with_nothing_staged_sends_nothing():
    raw = CountingSheet(ROWS)
    SheetTab(raw).flush()

    assert raw.write_batches == 0


def test_last_staged_value_for_a_cell_wins():
    raw = CountingSheet(ROWS)
    tab = SheetTab(raw)

    tab.stage(2, {"status": "generating"})
    tab.stage(2, {"status": "uploading"})
    tab.flush()

    assert raw.cells_written == 1
    _, records = raw.read_all()
    assert records[0]["status"] == "uploading"


def test_reading_back_a_staged_write_sees_it_before_flush():
    tab = SheetTab(CountingSheet(ROWS))

    tab.stage(2, {"status": "generating"})

    assert tab.records[0]["status"] == "generating"


def test_ensure_columns_appends_only_missing_headers():
    raw = CountingSheet(ROWS)
    tab = SheetTab(raw)

    tab.ensure_columns("status", "arc_number", "episode_number")

    assert tab.headers == [
        "title", "story_brief", "status", "youtube_url",
        "arc_number", "episode_number",
    ]
    # existing rows widen to match, so positional appends stay aligned
    _, records = raw.read_all()
    assert records[0]["arc_number"] == ""


def test_ensure_columns_is_idempotent():
    raw = CountingSheet(ROWS)
    tab = SheetTab(raw)

    tab.ensure_columns("status")
    before = list(tab.headers)
    tab.ensure_columns("status", "title")

    assert tab.headers == before


def test_append_row_maps_by_header_name():
    raw = CountingSheet(ROWS)
    tab = SheetTab(raw)

    tab.append_row({"title": "Three", "status": "pending"})

    assert raw.appends == 1
    _, records = raw.read_all()
    assert records[2] == {
        "title": "Three", "story_brief": "", "status": "pending", "youtube_url": "",
    }


def test_append_row_flushes_staged_writes_first():
    raw = CountingSheet(ROWS)
    tab = SheetTab(raw)

    tab.stage(2, {"status": "done"})
    tab.append_row({"title": "Three"})

    assert raw.write_batches == 1


def test_column_raises_with_the_headers_it_saw():
    tab = SheetTab(CountingSheet(ROWS))

    with pytest.raises(ValueError, match="not found in sheet headers"):
        tab.column("nope")


def test_refresh_flushes_then_rereads():
    raw = CountingSheet(ROWS)
    tab = SheetTab(raw)

    tab.records
    tab.stage(2, {"status": "done"})
    tab.refresh()

    assert raw.write_batches == 1
    assert tab.records[0]["status"] == "done"
    assert raw.reads == 2


def test_session_returns_the_same_tab_for_the_same_sheet():
    opened = []

    def opener(env_var, numericise):
        opened.append((env_var, numericise))
        return InMemorySheet(ROWS)

    session = SheetSession(opener=opener)
    first = session.tab("GOOGLE_SHEET_ID")
    second = session.tab("GOOGLE_SHEET_ID")

    assert first is second
    assert opened == [("GOOGLE_SHEET_ID", True)]


def test_session_keeps_numericised_and_raw_tabs_apart():
    def opener(env_var, numericise):
        return InMemorySheet(ROWS)

    session = SheetSession(opener=opener)

    # The characters sheet is opened with numericise=False so comma-separated
    # columns survive; it must not collide with the episodes tab.
    assert session.tab("SHEET", numericise=True) is not session.tab("SHEET", numericise=False)


def test_session_flush_flushes_every_tab():
    raws = {}

    def opener(env_var, numericise):
        raws[env_var] = CountingSheet(ROWS)
        return raws[env_var]

    session = SheetSession(opener=opener)
    session.tab("A").stage(2, {"status": "done"})
    session.tab("B").stage(2, {"status": "error"})
    session.flush()

    assert raws["A"].write_batches == 1
    assert raws["B"].write_batches == 1

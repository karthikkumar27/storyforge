# tests/modules/test_characters_reader.py
import pytest

from modules.characters_reader import CharactersReader, format_characters_context
from modules.sheet_access import SheetSession
from tests.support import CountingSheet

HEADERS = [
    "character_name", "alias", "role", "relation_to_main",
    "appearance_normal", "appearance_transformed",
    "ref_image_normal", "ref_image_transformed",
    "backstory", "first_episode", "status", "arcs_active",
]

ENV_VAR = "ALAN_STORY_CHARACTERS_GOOGLE_SHEET_ID"


def _char(**overrides):
    row = {h: "" for h in HEADERS}
    row.update(overrides)
    return row


ALAN = _char(
    character_name="Alan Vorne", alias="Zenith", role="main", relation_to_main="self",
    appearance_normal="Late 30s, dark coat, silver two-pointed-star pendant.",
    appearance_transformed="Crystalline plates, two-pointed stars where eyes should be.",
    ref_image_normal="https://img/alan.png",
    ref_image_transformed="https://img/zenith.png",
    first_episode="1", status="active", arcs_active="1,2,3",
)
MIRA = _char(
    character_name="Mira Okafor", role="ally", relation_to_main="lover",
    appearance_normal="Tall, close-cropped hair, field jacket.",
    first_episode="41", status="active", arcs_active="3,4",
)
BEAUMONT = _char(
    character_name="Sheriff Beaumont", role="ally",
    appearance_normal="Broad shouldered, grey moustache.",
    first_episode="61", status="dead",
)


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "chars-sheet-id")


def _session(rows):
    """A session whose only tab is an in-memory characters sheet."""
    raw = CountingSheet(rows, headers=HEADERS)
    return SheetSession(opener=lambda env_var, numericise: raw), raw


def test_reader_is_a_no_op_when_the_sheet_is_not_configured(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)

    reader = CharactersReader()

    assert reader.available is False
    assert reader.get_all_characters() == []
    assert reader.get_main_ref_image_for_form("normal") is None


def test_blank_rows_are_ignored(configured):
    session, _ = _session([ALAN, _char(), MIRA])

    names = [c["character_name"] for c in CharactersReader(session).get_all_characters()]

    assert names == ["Alan Vorne", "Mira Okafor"]


def test_arcs_active_selects_the_cast_for_an_arc(configured):
    session, _ = _session([ALAN, MIRA])

    reader = CharactersReader(session)

    assert [c["character_name"] for c in reader.get_active_for_arc(2)] == ["Alan Vorne"]
    assert [c["character_name"] for c in reader.get_active_for_arc(3)] == [
        "Alan Vorne", "Mira Okafor",
    ]


def test_arcs_active_survives_sheets_stripping_commas(configured):
    """The characters tab is opened with numericise=False precisely so
    "1,2,3" doesn't come back as the integer 123."""
    session, _ = _session([ALAN])

    reader = CharactersReader(session)

    assert reader.get_active_for_arc(2) != []


def test_characters_without_arcs_active_fall_back_to_first_episode_and_status(configured):
    session, _ = _session([BEAUMONT])
    reader = CharactersReader(session)

    # first_episode 61 -> arc 4; but status is "dead", so never active
    assert reader.get_active_for_arc(4) == []

    alive = dict(BEAUMONT, status="active")
    session2, _ = _session([alive])
    reader2 = CharactersReader(session2)

    assert reader2.get_active_for_arc(3) == []          # before their first arc
    assert len(reader2.get_active_for_arc(4)) == 1      # from their first arc on
    assert len(reader2.get_active_for_arc(9)) == 1


def test_main_character_is_the_row_marked_main(configured):
    session, _ = _session([MIRA, ALAN])

    assert CharactersReader(session).get_main_character()["character_name"] == "Alan Vorne"


@pytest.mark.parametrize("form,expected", [
    ("normal", "https://img/alan.png"),
    ("transformed", "https://img/zenith.png"),
    ("both", "https://img/zenith.png"),
    ("", "https://img/alan.png"),
    ("nonsense", "https://img/alan.png"),
])
def test_reference_image_is_chosen_by_character_form(configured, form, expected):
    session, _ = _session([ALAN])

    assert CharactersReader(session).get_main_ref_image_for_form(form) == expected


def test_transformed_falls_back_to_normal_when_unset(configured):
    session, _ = _session([dict(ALAN, ref_image_transformed="")])

    assert CharactersReader(session).get_main_ref_image_for_form("transformed") == (
        "https://img/alan.png"
    )


def test_no_reference_image_signals_the_caller_to_generate_one(configured):
    session, _ = _session([dict(ALAN, ref_image_normal="", ref_image_transformed="")])

    assert CharactersReader(session).get_main_ref_image_for_form("normal") is None


def test_context_block_carries_locked_appearances(configured):
    session, _ = _session([ALAN, MIRA])

    block = format_characters_context(3, 45, session=session)

    assert "CHARACTER ROSTER" in block
    assert "Alan Vorne (aka Zenith) — main" in block
    assert "LOCKED APPEARANCE: Late 30s, dark coat" in block
    assert "LOCKED APPEARANCE (transformed): Crystalline plates" in block
    assert "Mira Okafor" in block


def test_context_block_is_empty_when_nobody_is_active_in_the_arc(configured):
    session, _ = _session([MIRA])   # arcs_active 3,4

    assert format_characters_context(1, 5, session=session) == ""


def test_context_block_is_empty_without_a_configured_sheet(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)

    assert format_characters_context(1, 1) == ""


def test_one_session_reads_the_characters_sheet_once(configured):
    """A preset-7 episode builds three readers -- brief generator, script
    generator, orchestrator. Sharing the Run's session collapses three
    authentications and three reads into one."""
    session, raw = _session([ALAN, MIRA])

    format_characters_context(3, 45, session=session)     # brief generator
    format_characters_context(3, 45, session=session)     # script generator
    CharactersReader(session).get_main_ref_image_for_form("normal")   # orchestrator

    assert raw.reads == 1


def test_separate_sessions_do_not_share_a_snapshot(configured):
    """Edits made between Runs must be picked up -- see ADR-0001."""
    raw = CountingSheet([ALAN], headers=HEADERS)
    opener = lambda env_var, numericise: raw

    CharactersReader(SheetSession(opener=opener)).get_all_characters()
    CharactersReader(SheetSession(opener=opener)).get_all_characters()

    assert raw.reads == 2

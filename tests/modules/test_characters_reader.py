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


def test_record_ref_image_writes_the_column_for_that_form(configured):
    session, raw = _session([ALAN, MIRA])
    reader = CharactersReader(session)

    reader.record_ref_image("Mira Okafor", "normal", "https://img/mira.png")

    _, records = raw.read_all()
    assert records[1]["ref_image_normal"] == "https://img/mira.png"
    assert records[0]["ref_image_normal"] == "https://img/alan.png"   # untouched


def test_record_ref_image_lands_immediately(configured):
    """Each image costs money and ~90s; a crash mid-run must not discard the
    ones already paid for."""
    session, raw = _session([ALAN])

    CharactersReader(session).record_ref_image("Alan Vorne", "transformed", "https://new")

    assert raw.write_batches == 1        # flushed, not buffered
    assert raw.cells_written == 1


def test_record_ref_image_reads_back_through_the_reader(configured):
    session, _ = _session([dict(ALAN, ref_image_transformed="")])
    reader = CharactersReader(session)

    reader.record_ref_image("Alan Vorne", "transformed", "https://img/zenith2.png")

    assert reader.get_main_ref_image_for_form("transformed") == "https://img/zenith2.png"


def test_record_ref_image_rejects_an_unknown_character(configured):
    session, _ = _session([ALAN])

    with pytest.raises(ValueError, match="No character named"):
        CharactersReader(session).record_ref_image("Nobody", "normal", "https://x")


def test_record_ref_image_rejects_a_roster_without_the_column(configured):
    raw = CountingSheet(
        [{"character_name": "Alan Vorne", "appearance_normal": "x"}],
        headers=["character_name", "appearance_normal"],
    )
    session = SheetSession(opener=lambda env_var, numericise: raw)

    with pytest.raises(ValueError, match="not found in sheet headers"):
        CharactersReader(session).record_ref_image("Alan Vorne", "normal", "https://x")


def test_record_ref_image_is_a_no_op_target_without_a_configured_sheet(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)

    with pytest.raises(ValueError, match="not configured"):
        CharactersReader().record_ref_image("Alan Vorne", "normal", "https://x")


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


# -- locked appearance, form-aware --------------------------------------------

def test_appearance_form_selection_mirrors_the_ref_image_logic(configured):
    """The same episode's character_form already picks the image; it must pick
    the matching words, or the prompt describes Alan while the image shows
    Zenith."""
    session, _ = _session([ALAN])
    reader = CharactersReader(session)

    assert reader.get_main_appearance_for_form("normal").startswith("Late 30s")
    assert reader.get_main_appearance_for_form("transformed").startswith("Crystalline")
    assert reader.get_main_appearance_for_form("both").startswith("Crystalline")
    assert reader.get_main_appearance_for_form("").startswith("Late 30s")


def test_appearance_selection_matches_ref_image_selection_for_every_form(configured):
    """Pins the mirror explicitly: whichever form picks the transformed IMAGE
    must pick the transformed WORDS."""
    session, _ = _session([ALAN])
    reader = CharactersReader(session)

    for form in ("normal", "transformed", "both", "", "nonsense"):
        image_is_transformed = (
            reader.get_main_ref_image_for_form(form) == "https://img/zenith.png"
        )
        words_are_transformed = reader.get_main_appearance_for_form(form).startswith(
            "Crystalline"
        )
        assert image_is_transformed == words_are_transformed, form


def test_appearance_falls_back_when_the_requested_form_is_empty(configured):
    session, _ = _session([_char(
        character_name="Alan Vorne", role="main",
        appearance_normal="Late 30s, dark coat.",
        appearance_transformed="",
    )])

    assert CharactersReader(session).get_main_appearance_for_form(
        "transformed"
    ).startswith("Late 30s")


def test_appearance_falls_back_the_other_direction_too(configured):
    session, _ = _session([_char(
        character_name="Alan Vorne", role="main",
        appearance_normal="",
        appearance_transformed="Crystalline plates.",
    )])

    assert CharactersReader(session).get_main_appearance_for_form(
        "normal"
    ).startswith("Crystalline")


def test_no_appearance_anywhere_returns_none(configured):
    session, _ = _session([_char(
        character_name="Alan Vorne", role="main",
        appearance_normal="", appearance_transformed="",
    )])

    assert CharactersReader(session).get_main_appearance_for_form("normal") is None


def test_no_main_character_returns_none(configured):
    session, _ = _session([MIRA])   # role="ally", not "main"

    assert CharactersReader(session).get_main_appearance_for_form("normal") is None


def test_appearance_is_none_when_the_sheet_is_not_configured(monkeypatch):
    """Mirrors the existing no-op guarantee for get_main_ref_image_for_form."""
    monkeypatch.delenv(ENV_VAR, raising=False)

    assert CharactersReader().get_main_appearance_for_form("normal") is None

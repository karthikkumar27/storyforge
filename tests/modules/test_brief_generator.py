# tests/modules/test_brief_generator.py
import pytest

from config import GENRES, SERIES_PARTS, STORY_MODE
from modules.brief_generator import BriefGenerator
from modules.llm import MalformedJsonError
from modules.preset import active_preset
from tests.support import StubLlm

_preset = active_preset()

SAMPLE_BRIEF = {
    "story_brief": "A lone cosmonaut on a decommissioned station receives a signal "
                   "from a planet that shouldn't exist.",
    "genre": GENRES[0],
    "title_hint": "The Phantom Signal",
}


def test_generate_returns_the_parsed_brief():
    llm = StubLlm([dict(SAMPLE_BRIEF)])

    result = BriefGenerator(llm=llm).generate()

    assert result["story_brief"] == SAMPLE_BRIEF["story_brief"]
    assert result["genre"] == GENRES[0]


def test_generate_stamps_the_story_mode():
    llm = StubLlm([dict(SAMPLE_BRIEF)])

    result = BriefGenerator(llm=llm).generate()

    assert result["story_mode"] == STORY_MODE


@pytest.mark.skipif(
    _preset.is_single_shot_native,
    reason="single-shot presets write a video prompt, not a story — no craft skills",
)
def test_the_active_presets_skills_reach_the_system_prompt():
    llm = StubLlm([dict(SAMPLE_BRIEF)])

    BriefGenerator(llm=llm).generate()

    system = llm.calls[0]["system"]
    assert "SKILL: STORYTELLING CRAFT" in system
    assert "SKILL: EPISODE ARCHITECTURE" in system
    for skill in _preset.extra_skills:
        assert f"SKILL: {skill.upper().replace('-', ' ')}" in system


def test_past_stories_are_offered_as_anti_repetition():
    llm = StubLlm([dict(SAMPLE_BRIEF)])

    BriefGenerator(llm=llm).generate(past_stories=[
        {"title": "Old One", "story_brief": "a drifting probe", "genre": GENRES[0]},
    ])

    system = llm.calls[0]["system"]
    assert "Old One" in system
    assert "DO NOT repeat" in system


def test_an_unparseable_reply_surfaces_as_a_malformed_json_error():
    llm = StubLlm(errors=[MalformedJsonError("nope")])

    with pytest.raises(MalformedJsonError):
        BriefGenerator(llm=llm).generate()


@pytest.mark.skipif(STORY_MODE != "series", reason="preset is standalone")
def test_a_series_brief_carries_the_series_identifiers():
    llm = StubLlm([dict(SAMPLE_BRIEF)])

    result = BriefGenerator(llm=llm).generate(previous_parts=[])

    assert result["story_mode"] == "series"
    assert result["series_id"]
    assert result["part_number"] == 1


@pytest.mark.skipif(STORY_MODE != "series", reason="preset is standalone")
def test_previous_parts_are_recapped_for_continuity():
    llm = StubLlm([dict(SAMPLE_BRIEF)])

    BriefGenerator(llm=llm).generate(previous_parts=[
        {"series_id": "s1", "story_brief": "she found the door", "part_number": 1},
    ])

    system = llm.calls[0]["system"]
    assert "she found the door" in system
    assert llm.calls[0]["user"].count("Part 2") or "Part 2" in system


@pytest.mark.skipif(
    not _preset.serialized_canon, reason="preset has no serialized canon"
)
def test_serialized_presets_ask_for_a_character_form_and_default_it():
    """Claude is asked to declare normal/transformed/both; if it omits the field
    the pipeline still needs one to pick a Reference Image."""
    llm = StubLlm([dict(SAMPLE_BRIEF)])   # no character_form in the reply

    result = BriefGenerator(llm=llm).generate(previous_parts=[], episode_number=6)

    assert "character_form" in llm.calls[0]["system"]
    assert result["character_form"] == "normal"


@pytest.mark.skipif(
    not _preset.serialized_canon, reason="preset has no serialized canon"
)
def test_a_declared_character_form_is_kept():
    llm = StubLlm([dict(SAMPLE_BRIEF, character_form="transformed")])

    result = BriefGenerator(llm=llm).generate(previous_parts=[], episode_number=6)

    assert result["character_form"] == "transformed"


@pytest.mark.skipif(
    not _preset.serialized_canon, reason="preset has no serialized canon"
)
def test_arc_context_is_injected_for_a_numbered_episode():
    llm = StubLlm([dict(SAMPLE_BRIEF)])

    result = BriefGenerator(llm=llm).generate(previous_parts=[], episode_number=6)

    system = llm.calls[0]["system"]
    assert "EPISODE CONTEXT" in system
    assert "Episode: #6 of 200" in system
    assert result["episode_number"] == 6
    assert result["arc_number"] == 1


@pytest.mark.skipif(
    _preset.series_parts != 3, reason="preset is not a 3-part bounded series"
)
def test_the_final_part_gets_the_closure_rules():
    llm = StubLlm([dict(SAMPLE_BRIEF)])
    previous = [
        {"series_id": "s1", "story_brief": f"part {i}", "part_number": i}
        for i in (1, 2)
    ]

    BriefGenerator(llm=llm).generate(previous_parts=previous)

    system = llm.calls[0]["system"]
    assert "THIS IS THE FINAL PART" in system
    assert "DO NOT end on a setup sentence" in system


@pytest.mark.skipif(
    _preset.series_parts == 3, reason="bounded series always closes at part 3"
)
def test_a_mid_series_part_does_not_get_the_closure_rules():
    llm = StubLlm([dict(SAMPLE_BRIEF)])

    BriefGenerator(llm=llm).generate(previous_parts=[
        {"series_id": "s1", "story_brief": "part 1", "part_number": 1},
    ])

    assert "THIS IS THE FINAL PART" not in llm.calls[0]["system"]

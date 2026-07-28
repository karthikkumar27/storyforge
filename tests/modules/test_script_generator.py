# tests/modules/test_script_generator.py
import pytest

from config import DEFAULT_TAGS, SHOTS_COUNT, VIDEO_STYLE
from modules.llm import MalformedJsonError
from modules.preset import active_preset
from modules.script_generator import ScriptGenerator
from tests.support import StubLlm

_preset = active_preset()

SAMPLE_RESPONSE = {
    "narrative": "In the void between stars, a signal pulses...",
    "title": "The Last Signal",
    "description": "A haunting journey through deep space.",
    "tags": ["scifi", "space", "cinematic"],
    "visual_style": "Cel-shaded, deep blue palette.",
    "shots": [f"Shot {i}: cinematic description {i}." for i in range(1, SHOTS_COUNT + 1)],
}


def _sample():
    return {k: (list(v) if isinstance(v, list) else v) for k, v in SAMPLE_RESPONSE.items()}


def test_generate_returns_the_parsed_script():
    llm = StubLlm([_sample()])

    result = ScriptGenerator(llm=llm).generate("A ghost astronaut", "blend")

    assert result["narrative"] == SAMPLE_RESPONSE["narrative"]
    assert result["title"] == "The Last Signal"
    assert len(result["shots"]) == SHOTS_COUNT


def test_the_brief_and_genre_reach_the_model():
    llm = StubLlm([_sample()])

    ScriptGenerator(llm=llm).generate("A lost probe sends back alien signals", "sci-fi")

    user = llm.calls[0]["user"]
    assert "sci-fi" in user
    assert "A lost probe sends back alien signals" in user


def test_the_visual_style_is_prepended_to_every_shot():
    """Shots are sent to the video model individually, so each needs the art
    direction — the producer never sees `visual_style` on its own."""
    llm = StubLlm([_sample()])

    result = ScriptGenerator(llm=llm).generate("brief", "sci-fi")

    for shot in result["shots"]:
        assert shot.startswith("Cel-shaded, deep blue palette.")


def test_shots_are_untouched_when_no_visual_style_is_returned():
    llm = StubLlm([dict(_sample(), visual_style="")])

    result = ScriptGenerator(llm=llm).generate("brief", "sci-fi")

    assert result["shots"][0] == "Shot 1: cinematic description 1."


def test_default_tags_are_appended_after_the_content_tags():
    """YouTube weights leading tags more heavily, so Claude's specific tags go
    first and the generic AI-provenance tags follow."""
    llm = StubLlm([_sample()])

    result = ScriptGenerator(llm=llm).generate("brief", "sci-fi")

    assert result["tags"][:3] == ["scifi", "space", "cinematic"]
    for tag in DEFAULT_TAGS:
        assert tag in result["tags"]


def test_default_tags_are_not_duplicated():
    llm = StubLlm([dict(_sample(), tags=["scifi", DEFAULT_TAGS[0].upper()])])

    result = ScriptGenerator(llm=llm).generate("brief", "sci-fi")

    lowered = [t.lower() for t in result["tags"]]
    assert lowered.count(DEFAULT_TAGS[0].lower()) == 1


def test_the_system_prompt_carries_the_presets_style_and_skills():
    llm = StubLlm([_sample()])

    ScriptGenerator(llm=llm).generate("brief", "sci-fi")

    system = llm.calls[0]["system"]
    assert VIDEO_STYLE in system
    assert "SKILL: VIDEO PROMPT BUILDER" in system
    assert "SKILL: SCREENPLAY DIRECTOR" in system
    for skill in _preset.extra_skills:
        assert f"SKILL: {skill.upper().replace('-', ' ')}" in system


def test_an_unparseable_reply_surfaces_as_a_malformed_json_error():
    llm = StubLlm(errors=[MalformedJsonError("no JSON here")])

    with pytest.raises(MalformedJsonError):
        ScriptGenerator(llm=llm).generate("brief", "sci-fi")


def test_a_generator_survives_one_unparseable_reply():
    """End-to-end through the real Llm: the retry has to be wired up, not just
    present. Before this seam, this run would have aborted after paying for the
    first Claude call."""
    import json as _json
    from modules.llm import Llm
    from tests.modules.test_llm import FakeAnthropic

    client = FakeAnthropic([
        "Certainly! Here's your script:",          # unparseable
        _json.dumps(SAMPLE_RESPONSE),              # good
    ])
    generator = ScriptGenerator(llm=Llm(client, sleep=lambda _s: None))

    result = generator.generate("brief", "sci-fi")

    assert result["title"] == "The Last Signal"
    assert len(client.messages.calls) == 2


def test_the_script_asks_for_enough_tokens_for_a_full_shot_list():
    llm = StubLlm([_sample()])

    ScriptGenerator(llm=llm).generate("brief", "sci-fi")

    assert llm.calls[0]["max_tokens"] == 2000

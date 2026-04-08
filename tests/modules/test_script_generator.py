# tests/modules/test_script_generator.py
import json
import pytest
from unittest.mock import MagicMock, patch

SAMPLE_RESPONSE = {
    "narrative": "In the void between stars, a signal pulses...",
    "title": "The Last Signal",
    "description": "A haunting journey through deep space where silence speaks louder than fear.",
    "tags": ["scifi", "space", "horror", "cinematic", "shortfilm"],
    "shots": [
        "Slow orbital pan around a derelict space station, deep space black, distant nebula glow.",
        "Interior corridor, emergency red lighting flickers, dust particles float in zero-g.",
        "Close-up of cracked helmet visor reflecting a dying star.",
        "Wide dolly push through an airlock, cold blue light bleeds in from outside.",
        "Extreme close-up of a blinking distress beacon, pulse slowing.",
        "Pull back reveal: massive alien monolith drifts behind the station.",
        "Final wide shot: the station, the monolith, silence and stars.",
    ],
}


@patch("modules.script_generator.anthropic.Anthropic")
def test_generate_returns_parsed_dict(mock_anthropic_class, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    mock_client = MagicMock()
    mock_anthropic_class.return_value = mock_client
    mock_client.messages.create.return_value.content = [
        MagicMock(text=json.dumps(SAMPLE_RESPONSE))
    ]

    from modules.script_generator import ScriptGenerator
    gen = ScriptGenerator()
    result = gen.generate("A ghost astronaut haunts an abandoned station", "blend")

    assert result["narrative"] == "In the void between stars, a signal pulses..."
    assert len(result["shots"]) == 7
    assert result["title"] == "The Last Signal"
    assert "tags" in result
    assert "description" in result


@patch("modules.script_generator.anthropic.Anthropic")
def test_generate_passes_genre_and_brief_to_claude(mock_anthropic_class, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    mock_client = MagicMock()
    mock_anthropic_class.return_value = mock_client
    mock_client.messages.create.return_value.content = [
        MagicMock(text=json.dumps(SAMPLE_RESPONSE))
    ]

    from modules.script_generator import ScriptGenerator
    gen = ScriptGenerator()
    gen.generate("A lost probe sends back alien signals", "sci-fi")

    call_kwargs = mock_client.messages.create.call_args.kwargs
    user_content = call_kwargs["messages"][0]["content"]
    assert "sci-fi" in user_content
    assert "A lost probe sends back alien signals" in user_content


@patch("modules.script_generator.anthropic.Anthropic")
def test_generate_raises_on_invalid_json(mock_anthropic_class, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    mock_client = MagicMock()
    mock_anthropic_class.return_value = mock_client
    mock_client.messages.create.return_value.content = [
        MagicMock(text="not valid json at all")
    ]

    from modules.script_generator import ScriptGenerator
    gen = ScriptGenerator()

    with pytest.raises(json.JSONDecodeError):
        gen.generate("brief", "sci-fi")

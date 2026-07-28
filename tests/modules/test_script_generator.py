# tests/modules/test_script_generator.py
import json
import pytest
from unittest.mock import MagicMock, patch
from config import SHOTS_COUNT

SAMPLE_RESPONSE = {
    "narrative": "In the void between stars, a signal pulses...",
    "title": "The Last Signal",
    "description": "A haunting journey through deep space where silence speaks louder than fear.",
    "tags": ["scifi", "space", "horror", "cinematic", "shortfilm"],
    "shots": [f"Shot {i}: cinematic description {i}." for i in range(1, SHOTS_COUNT + 1)],
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
    assert len(result["shots"]) == SHOTS_COUNT
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

    # _extract_json raises ValueError with a diagnostic message when the response
    # contains no JSON object at all. (json.JSONDecodeError, raised when a braced
    # region is found but is malformed, is a subclass of ValueError — so this
    # assertion covers both failure shapes.)
    with pytest.raises(ValueError, match="No JSON object found"):
        gen.generate("brief", "sci-fi")

import json
import pytest
from unittest.mock import MagicMock, patch


SAMPLE_BRIEF = {
    "story_brief": "A lone cosmonaut on a decommissioned station receives a signal from a planet that shouldn't exist.",
    "genre": "sci-fi",
    "title_hint": "The Phantom Signal",
}


@patch("modules.brief_generator.anthropic.Anthropic")
def test_generate_returns_parsed_dict(mock_anthropic_class, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    mock_client = MagicMock()
    mock_anthropic_class.return_value = mock_client
    mock_client.messages.create.return_value.content = [
        MagicMock(text=json.dumps(SAMPLE_BRIEF))
    ]

    from modules.brief_generator import BriefGenerator
    gen = BriefGenerator()
    result = gen.generate()

    assert "story_brief" in result
    assert "genre" in result
    assert result["genre"] in ["sci-fi", "horror", "space", "blend"]


@patch("modules.brief_generator.anthropic.Anthropic")
def test_generate_raises_on_invalid_json(mock_anthropic_class, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    mock_client = MagicMock()
    mock_anthropic_class.return_value = mock_client
    mock_client.messages.create.return_value.content = [
        MagicMock(text="not json")
    ]

    from modules.brief_generator import BriefGenerator
    gen = BriefGenerator()

    with pytest.raises(Exception):
        gen.generate()

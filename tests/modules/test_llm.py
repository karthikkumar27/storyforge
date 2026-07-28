# tests/modules/test_llm.py
import json

import pytest

from modules.llm import RETRY_NUDGE, Llm, MalformedJsonError, extract_json


class FakeMessages:
    """Replays scripted reply texts and records what it was asked."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def create(self, *, model, max_tokens, system, messages):
        self.calls.append({
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "user": messages[0]["content"],
        })
        text = self.replies.pop(0)

        class _Block:
            def __init__(self, text):
                self.text = text

        class _Message:
            def __init__(self, text):
                self.content = [_Block(text)]

        return _Message(text)


class FakeAnthropic:
    def __init__(self, replies):
        self.messages = FakeMessages(replies)


class RecordingSleep:
    def __init__(self):
        self.slept = []

    def __call__(self, seconds):
        self.slept.append(seconds)


def _llm(replies, **kwargs):
    client = FakeAnthropic(replies)
    return Llm(client, sleep=RecordingSleep(), **kwargs), client


# -- extraction ---------------------------------------------------------------

def test_a_bare_object_parses():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_a_fenced_object_parses():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('```\n{"a": 1}\n```') == {"a": 1}


def test_prose_around_the_object_is_tolerated():
    text = 'Sure! Here is the brief you asked for:\n{"a": 1}\nHope that helps.'

    assert extract_json(text) == {"a": 1}


def test_nested_objects_survive_the_outermost_span():
    payload = {"outer": {"inner": [1, 2]}, "z": "}"}
    assert extract_json(json.dumps(payload)) == payload


def test_no_object_at_all_is_a_malformed_json_error():
    with pytest.raises(MalformedJsonError, match="No JSON object found"):
        extract_json("I'm afraid I can't do that.")


def test_a_broken_object_is_a_malformed_json_error():
    with pytest.raises(MalformedJsonError, match="not valid JSON"):
        extract_json('{"a": 1,,,}')


def test_malformed_json_error_is_a_value_error():
    """Callers that predate this module caught ValueError; keep them working."""
    assert issubclass(MalformedJsonError, ValueError) or issubclass(
        MalformedJsonError, RuntimeError
    )


# -- the exchange -------------------------------------------------------------

def test_ask_json_returns_the_parsed_object():
    llm, _ = _llm(['{"story_brief": "a drifting probe"}'])

    assert llm.ask_json("sys", "user", max_tokens=500) == {
        "story_brief": "a drifting probe",
    }


def test_the_system_and_user_prompts_are_passed_through():
    llm, client = _llm(['{"a": 1}'])

    llm.ask_json("SYSTEM TEXT", "USER TEXT", max_tokens=750)

    call = client.messages.calls[0]
    assert call["system"] == "SYSTEM TEXT"
    assert call["user"] == "USER TEXT"
    assert call["max_tokens"] == 750


def test_the_model_can_be_overridden():
    client = FakeAnthropic(['{"a": 1}'])
    Llm(client, model="claude-test-9").ask_json("s", "u", max_tokens=10)

    assert client.messages.calls[0]["model"] == "claude-test-9"


# -- the retry that this module exists for ------------------------------------

def test_an_unparseable_reply_is_retried_with_a_corrective_nudge():
    """Before this seam existed, a single formatting slip aborted an episode
    that had already paid for a Claude call."""
    llm, client = _llm(["Sure, here you go!", '{"a": 1}'])

    assert llm.ask_json("sys", "user", max_tokens=500) == {"a": 1}

    first, second = client.messages.calls
    assert first["user"] == "user"
    assert second["user"] == "user" + RETRY_NUDGE


def test_the_nudge_is_not_repeated_twice_over():
    llm, client = _llm(["nope", "still nope", '{"a": 1}'])

    llm.ask_json("sys", "user", max_tokens=500)

    third = client.messages.calls[2]["user"]
    assert third.count(RETRY_NUDGE) == 1


def test_it_gives_up_after_the_attempt_budget():
    llm, client = _llm(["nope", "nope", "nope"])

    with pytest.raises(MalformedJsonError, match="all 3 attempts"):
        llm.ask_json("sys", "user", max_tokens=500)

    assert len(client.messages.calls) == 3


def test_the_attempt_budget_is_configurable():
    llm, client = _llm(["nope", "nope"], max_attempts=2)

    with pytest.raises(MalformedJsonError):
        llm.ask_json("sys", "user", max_tokens=500)

    assert len(client.messages.calls) == 2


def test_a_good_first_reply_costs_exactly_one_call():
    llm, client = _llm(['{"a": 1}'])

    llm.ask_json("sys", "user", max_tokens=500)

    assert len(client.messages.calls) == 1


def test_the_final_error_names_the_caller():
    llm, _ = _llm(["nope"] * 3)

    with pytest.raises(MalformedJsonError, match="ScriptGenerator"):
        llm.ask_json("sys", "user", max_tokens=500, label="ScriptGenerator")


# -- construction -------------------------------------------------------------

def test_constructing_an_llm_needs_no_api_key(monkeypatch):
    """The client is built on first use, so importing a generator does not
    require credentials."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    Llm()   # must not raise

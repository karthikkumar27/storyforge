"""Asking Claude for JSON, in one place.

Both generators do the same three things: build a system prompt, send one user
message, and parse a JSON object out of the reply. That was written twice, along
with two near-identical copies of the extractor — and neither copy retried a
malformed reply, so a single formatting slip aborted an episode that had already
paid for a Claude call (and, in the pipeline, was about to pay for video).

`Llm.ask_json()` owns the whole exchange: the client, the model, tolerant
extraction, and a corrective retry when the model returns something unparseable.

The Anthropic client and the sleep function are injected, so tests can drive the
retry path without a real API or a real clock.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from config import CLAUDE_MODEL

# Appended to the user message when a reply could not be parsed. Kept blunt:
# the failure is almost always prose wrapped around the object, or a fence.
RETRY_NUDGE = (
    "\n\nIMPORTANT: your previous response could not be parsed as JSON. "
    "Return ONLY the JSON object — no prose before or after it, no markdown "
    "fences, no explanation."
)

DEFAULT_MAX_ATTEMPTS = 3


class LlmError(RuntimeError):
    """Any failure getting a usable answer out of the model."""


class MalformedJsonError(LlmError):
    """The model's reply could not be parsed as a JSON object."""


def extract_json(text: str) -> dict:
    """Pull a JSON object out of a model reply.

    Tolerant by design — models wrap objects in markdown fences, preambles and
    trailing commentary. Takes the outermost {...} span.
    """
    cleaned = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise MalformedJsonError(f"No JSON object found in model response: {text!r}")
    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise MalformedJsonError(
            f"Model response was not valid JSON ({exc}): {text[:400]!r}"
        ) from exc


class Llm:
    """One Claude exchange that returns a JSON object."""

    def __init__(
        self,
        client: Any = None,
        *,
        model: str = CLAUDE_MODEL,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        sleep: Any = time.sleep,
    ):
        self._client = client
        self._model = model
        self._max_attempts = max_attempts
        self._sleep = sleep

    @property
    def client(self):
        """Built on first use so constructing an Llm needs no API key."""
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        return self._client

    def ask_json(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int,
        label: str = "Claude",
    ) -> dict:
        """Send one message and return the JSON object in the reply.

        Retries with a corrective nudge when the reply cannot be parsed. Raises
        MalformedJsonError if every attempt fails.
        """
        last_error: MalformedJsonError | None = None
        for attempt in range(self._max_attempts):
            message = self.client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": self._user_message(user, attempt)}],
            )
            raw = message.content[0].text
            print(f"[{label}] raw response: {raw[:600]!r}", flush=True)
            try:
                return extract_json(raw)
            except MalformedJsonError as exc:
                last_error = exc
                remaining = self._max_attempts - attempt - 1
                if not remaining:
                    break
                print(
                    f"[{label}] Unparseable reply, retrying with a corrective "
                    f"nudge ({remaining} attempt(s) left)",
                    flush=True,
                )
                self._sleep(1)

        raise MalformedJsonError(
            f"{label} returned unparseable JSON on all {self._max_attempts} "
            f"attempts. Last error: {last_error}"
        )

    def _user_message(self, user: str, attempt: int) -> str:
        return user if attempt == 0 else f"{user}{RETRY_NUDGE}"

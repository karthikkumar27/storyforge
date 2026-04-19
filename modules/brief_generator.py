import json
import os
import random
import re
from datetime import date

import anthropic

from config import (
    CLAUDE_MODEL, GENRES, BRIEF_SYSTEM_CONTEXT, PRESET_NAME,
    STORY_MODE, SERIES_PARTS,
)


def _extract_json(text: str) -> dict:
    """Tolerant JSON extraction: handles markdown fences, preambles, trailing text."""
    cleaned = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"No JSON object found in model response: {text!r}")
    return json.loads(cleaned[start : end + 1])


STANDALONE_TEMPLATE = """{brief_context}

{anti_repetition}

LANGUAGE RULES:
- Use simple, everyday English. Short sentences.
- No big words. The idea should be easy to picture right away.
- It should make people curious: "what happens next?"

ORIGINALITY RULES — THIS IS CRITICAL:
- Every story must be COMPLETELY UNIQUE — different setting, different character, different conflict.
- NEVER reuse the same story structure as a previous story.
- Vary the time of day, location, character type, and type of mystery/conflict.
- Surprise the audience — go in an unexpected direction.

Return ONLY valid JSON:
{{"story_brief": "...", "genre": "{genre_options}", "title_hint": "3-5 word plain title"}}

No markdown. No explanation."""


SERIES_TEMPLATE = """{brief_context}

You are creating Part {part_number} of a {total_parts}-part series.

{series_context}

SERIES RULES:
- Part 1: Introduce the character and world. End with a strong cliffhanger that makes viewers NEED part 2.
- Middle parts: Escalate tension. Reveal a twist. End with an even bigger cliffhanger.
- Final part: Deliver a satisfying conclusion with an unexpected twist.
- Every part must work as a standalone video too — a new viewer should understand enough to enjoy it.
- Add "Part {part_number}" to the title_hint.

LANGUAGE RULES:
- Use simple, everyday English. Short sentences.
- No big words. The idea should be easy to picture right away.

Return ONLY valid JSON:
{{"story_brief": "...", "genre": "{genre_options}", "title_hint": "3-5 word plain title (Part {part_number})", "series_id": "{series_id}"}}

No markdown. No explanation."""


class BriefGenerator:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def generate(self, previous_parts: list[dict] | None = None, past_stories: list[dict] | None = None) -> dict:
        if STORY_MODE == "series":
            return self._generate_series(previous_parts or [], past_stories or [])
        return self._generate_standalone(past_stories or [])

    @staticmethod
    def _build_anti_repetition(past_stories: list[dict]) -> str:
        if not past_stories:
            return ""
        lines = ["STORIES ALREADY CREATED (DO NOT repeat any of these themes, settings, or plot structures):"]
        for s in past_stories:
            lines.append(f"- [{s.get('genre', '')}] \"{s.get('title', '')}\" — {s.get('story_brief', '')[:100]}")
        lines.append("")
        lines.append("Your new story MUST be completely different from ALL of the above.")
        return "\n".join(lines)

    def _generate_standalone(self, past_stories: list[dict]) -> dict:
        genre = random.choice(GENRES)
        seed = f"{date.today().isoformat()}-{random.randint(1000, 9999)}"

        system = STANDALONE_TEMPLATE.format(
            brief_context=BRIEF_SYSTEM_CONTEXT,
            genre_options="|".join(GENRES),
            anti_repetition=self._build_anti_repetition(past_stories),
        )

        prompt = (
            f"Today's seed: {seed}\n"
            f"Suggested genre: {genre}\n\n"
            "Generate a fresh, original story brief that is NOTHING like any previous story. "
            "You may use the suggested genre or blend it with others. Return JSON only."
        )
        print(f"[BriefGenerator] Standalone — Preset: {PRESET_NAME}, genre: {genre}", flush=True)

        message = self.client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=500,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text
        print(f"[BriefGenerator] raw response: {raw!r}", flush=True)
        result = _extract_json(raw)
        result["story_mode"] = "standalone"
        return result

    def _generate_series(self, previous_parts: list[dict], past_stories: list[dict]) -> dict:
        part_number = len(previous_parts) + 1
        genre = random.choice(GENRES)
        series_id = previous_parts[0]["series_id"] if previous_parts else f"series-{date.today().isoformat()}-{random.randint(1000, 9999)}"

        if previous_parts:
            recap = "\n".join(
                f"Part {i+1}: {p.get('story_brief', 'N/A')}"
                for i, p in enumerate(previous_parts)
            )
            series_context = f"PREVIOUS PARTS (continue this story):\n{recap}\n\nNow write Part {part_number}. Build on what happened before."
        else:
            anti_rep = self._build_anti_repetition(past_stories)
            series_context = (
                "This is Part 1 — the beginning of a BRAND NEW series.\n"
                "Introduce a unique world and character. End with a cliffhanger.\n\n"
                f"{anti_rep}"
            )

        system = SERIES_TEMPLATE.format(
            brief_context=BRIEF_SYSTEM_CONTEXT,
            genre_options="|".join(GENRES),
            part_number=part_number,
            total_parts=SERIES_PARTS,
            series_context=series_context,
            series_id=series_id,
        )

        seed = f"{date.today().isoformat()}-{random.randint(1000, 9999)}"
        prompt = (
            f"Today's seed: {seed}\n"
            f"Suggested genre: {genre}\n"
            f"Series: {series_id}, Part {part_number} of {SERIES_PARTS}\n\n"
            f"Generate Part {part_number} of the series. Return JSON only."
        )
        print(f"[BriefGenerator] Series — Part {part_number}/{SERIES_PARTS}, Preset: {PRESET_NAME}", flush=True)

        message = self.client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=500,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text
        print(f"[BriefGenerator] raw response: {raw!r}", flush=True)
        result = _extract_json(raw)
        result["story_mode"] = "series"
        result["series_id"] = series_id
        result["part_number"] = part_number
        return result

import json
import os
import random
import re
from datetime import date

import anthropic

from config import (
    CLAUDE_MODEL, GENRES, BRIEF_SYSTEM_CONTEXT, PRESET_NAME,
    STORY_MODE, SERIES_PARTS, ACTIVE_PRESET,
)
from modules.skill_loader import load_skills
from modules.arc_context import format_arc_context
from modules.characters_reader import format_characters_context

# --- BRIEF SKILL LOADING ------------------------------------------------------
# Brief generation needs storytelling craft (logline, want/need/lie) and the
# preset-specific lore. Visual / shot-level skills are reserved for the script
# generator since briefs are pre-visual.
_brief_skills = [
    "storytelling-craft",        # logline, character architecture, theme
    "episode-architecture",      # one-job-per-episode rule
]

_is_kids = ACTIVE_PRESET in ("preset-4", "preset-5", "preset-6")
if _is_kids:
    _brief_skills.append("kids-content-specialist")

if ACTIVE_PRESET == "preset-7":
    _brief_skills.append("chronicle-of-zenith-canon")

BRIEF_SKILLS = load_skills(*_brief_skills)


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
{{"story_brief": "...", "genre": "{genre_options}", "title_hint": "3-5 word plain title (Part {part_number})", "series_id": "{series_id}"{extra_fields}}}

No markdown. No explanation.{form_instruction}"""


# Extra instruction injected ONLY for preset-7 — asks Claude to declare which
# form the main character is in for this episode, so the pipeline can pick the
# right reference image (Alan vs Zenith).
PRESET_7_FORM_INSTRUCTION = """

CHARACTER FORM RULE (Chronicle of Zenith only):
- Decide whether the MAIN CHARACTER (Alan / Zenith) appears in their NORMAL form (Alan, the quiet human-passing space traveller) or TRANSFORMED form (Zenith, Veyl form — crystalline plates, two-pointed-star eyes) for this episode.
- The transformation is COSTLY (each one burns memory). Use it sparingly, only at peak emotional moments. Most episodes — especially in early arcs — Alan stays in normal form.
- Some episodes show BOTH forms in different shots (a transformation scene). When that happens, set "character_form" to "both".
- Add a "character_form" field to the JSON, value: "normal" | "transformed" | "both"."""


class BriefGenerator:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def generate(
        self,
        previous_parts: list[dict] | None = None,
        past_stories: list[dict] | None = None,
        episode_number: int | None = None,
    ) -> dict:
        if STORY_MODE == "series":
            return self._generate_series(previous_parts or [], past_stories or [], episode_number)
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
        full_system = f"{system}\n\n{BRIEF_SKILLS}"
        print(f"[BriefGenerator] Standalone — Preset: {PRESET_NAME}, genre: {genre}, skills: {', '.join(_brief_skills)}", flush=True)

        message = self.client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=500,
            system=full_system,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text
        print(f"[BriefGenerator] raw response: {raw!r}", flush=True)
        result = _extract_json(raw)
        result["story_mode"] = "standalone"
        return result

    def _generate_series(
        self,
        previous_parts: list[dict],
        past_stories: list[dict],
        episode_number: int | None = None,
    ) -> dict:
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

        # Preset-7 (Chronicle of Zenith) — inject the arc context block
        # AND the active character roster so Claude knows: which arc, which
        # question, which tone, which characters can appear, and their locked
        # appearance paragraphs.
        arc_context_block = ""
        characters_block = ""
        arc_number = None
        if ACTIVE_PRESET == "preset-7" and episode_number:
            arc_context_block = format_arc_context(episode_number)
            from modules.arc_context import resolve_arc
            arc_info = resolve_arc(episode_number)
            arc_number = arc_info["arc_number"] if arc_info else None
            if arc_number:
                characters_block = format_characters_context(arc_number, episode_number)

        # Preset-7 also gets a "character_form" field in the JSON output
        if ACTIVE_PRESET == "preset-7":
            extra_fields = ', "character_form": "normal|transformed|both"'
            form_instruction = PRESET_7_FORM_INSTRUCTION
        else:
            extra_fields = ""
            form_instruction = ""

        system = SERIES_TEMPLATE.format(
            brief_context=BRIEF_SYSTEM_CONTEXT,
            genre_options="|".join(GENRES),
            part_number=part_number,
            total_parts=SERIES_PARTS,
            series_context=series_context,
            series_id=series_id,
            extra_fields=extra_fields,
            form_instruction=form_instruction,
        )
        # Prepend in order: arc context (where we are) → characters (who's in play) → series template
        prefix_blocks = [b for b in (arc_context_block, characters_block) if b]
        if prefix_blocks:
            system = "\n\n".join(prefix_blocks) + "\n\n" + system

        seed = f"{date.today().isoformat()}-{random.randint(1000, 9999)}"
        ep_label = f"Episode {episode_number}" if episode_number else f"Part {part_number} of {SERIES_PARTS}"
        prompt = (
            f"Today's seed: {seed}\n"
            f"Suggested genre: {genre}\n"
            f"Series: {series_id}, {ep_label}\n\n"
            f"Generate this episode. Return JSON only."
        )
        full_system = f"{system}\n\n{BRIEF_SKILLS}"

        if arc_number:
            print(f"[BriefGenerator] Series — Episode {episode_number}, Arc {arc_number}, Preset: {PRESET_NAME}", flush=True)
        else:
            print(f"[BriefGenerator] Series — Part {part_number}/{SERIES_PARTS}, Preset: {PRESET_NAME}", flush=True)

        message = self.client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=500,
            system=full_system,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text
        print(f"[BriefGenerator] raw response: {raw!r}", flush=True)
        result = _extract_json(raw)
        result["story_mode"] = "series"
        result["series_id"] = series_id
        result["part_number"] = part_number
        if episode_number is not None:
            result["episode_number"] = episode_number
        if arc_number is not None:
            result["arc_number"] = arc_number
        # Default character_form for preset-7 if Claude omitted it.
        if ACTIVE_PRESET == "preset-7":
            form = str(result.get("character_form", "")).strip().lower()
            if form not in ("normal", "transformed", "both"):
                form = "normal"
            result["character_form"] = form
        return result

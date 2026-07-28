import random
from datetime import date

from config import (
    GENRES, BRIEF_SYSTEM_CONTEXT, PRESET_NAME,
    STORY_MODE, SERIES_PARTS,
)
from modules.llm import Llm
from modules.preset import active_preset
from modules.skill_loader import load_skills
from modules.arc_context import format_arc_context
from modules.characters_reader import format_characters_context

_preset = active_preset()

# --- BRIEF SKILL LOADING ------------------------------------------------------
# Brief generation needs storytelling craft (logline, want/need/lie) and the
# preset-specific lore. Visual / shot-level skills are reserved for the script
# generator since briefs are pre-visual.
_brief_skills = [
    "storytelling-craft",        # logline, character architecture, theme
    "episode-architecture",      # one-job-per-episode rule
] + list(_preset.extra_skills)

BRIEF_SKILLS = load_skills(*_brief_skills)


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


# Hard override appended when generating the LAST part of a bounded series
# (e.g. Part 3 of a 3-part trilogy for preset-1/3). The soft "Final part:
# satisfying conclusion with an unexpected twist" bullet in SERIES_TEMPLATE
# is not assertive enough — Claude tends to over-index on "unexpected twist"
# and ends on a new mystery (which demands a Part 4 that will never exist).
# This block is the closer.
FINAL_PART_RULES = """

============================================================
THIS IS THE FINAL PART. THE STORY ENDS HERE.
Treat it like the end of a movie, not the end of an episode.
============================================================

ABSOLUTE RULES FOR THIS BRIEF:

1. RESOLVE every open mystery from the previous parts. Re-read the FULL SCRIPT
   of each previous part below and list (silently to yourself) every question
   the audience is now asking — who, what, why, how. Your brief must give an
   answer or a clear emotional close to each one.

2. DO NOT introduce any NEW character, mystery, or question that isn't
   immediately answered in THIS SAME brief. A new figure appearing in the last
   shot is a sequel hook, not an ending.

3. DO NOT end on a setup sentence. Forbidden endings include:
   - "she knew this was only the beginning"
   - "what happened next would change everything"
   - "she looked up — and that's when she saw…"
   - "she already knew she wouldn't listen"
   - Any final line that creates anticipation for a Part 4.

4. The final beat MUST be a CLOSER. Closers look like:
   - A decisive action that ends the conflict ("she pulled the trigger")
   - A realisation that completes the mystery ("the mineral wasn't dreaming —
     she was")
   - A quiet emotional landing ("she finally let go and walked into the light")
   - A reveal that recontextualises everything ("the warning had been from
     herself — and she had always been the thing she was warning against")

5. An UNEXPECTED TWIST is welcome — but only as a twist in HOW THINGS RESOLVE,
   not as a brand-new puzzle. The twist must come WITH the resolution, not
   instead of it.

VERIFY before returning JSON: read your story_brief's last sentence aloud.
Does it feel like the end of a movie, or the start of the next scene?
If the latter, REWRITE THE BRIEF before answering.
"""


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
    def __init__(self, session=None, llm: Llm | None = None):
        """`session` is the Run's SheetSession, used to read the character
        roster. Pass it so the roster is read once per Run; omitting it falls
        back to a single-use session. `llm` is the Claude seam."""
        self._llm = llm or Llm()
        self._session = session

    def generate(
        self,
        previous_parts: list[dict] | None = None,
        past_stories: list[dict] | None = None,
        episode_number: int | None = None,
    ) -> dict:
        # Single-shot native presets (e.g. preset-8 Drone Shorts) don't have
        # stories or shot lists. They produce one Seedance 2.0 prompt per video.
        if _preset.is_single_shot_native:
            return self._generate_single_shot_prompt(past_stories or [])

        if STORY_MODE == "series":
            return self._generate_series(previous_parts or [], past_stories or [], episode_number)
        return self._generate_standalone(past_stories or [])

    def _generate_single_shot_prompt(self, past_stories: list[dict]) -> dict:
        """For single_shot_native presets: produce ONE video-gen prompt that
        Seedance will consume directly. No story, no shots, no script — the
        story_brief IS the Seedance prompt.

        For preset-8 (Cinematic Drone), the GENRES list IS the set of scenario
        archetypes (urban-chase / wildlife-encounter / impossible-vista /
        human-reaction). Picking one at random per video routes Claude to the
        matching archetype block in BRIEF_SYSTEM_CONTEXT.

        Returns: {"story_brief": <prompt>, "genre": <scenario tag>,
                  "title_hint": <3-5 word YouTube title>, "story_mode": "standalone"}
        """
        subject = random.choice(GENRES)
        seed = f"{date.today().isoformat()}-{random.randint(1000, 9999)}"

        anti_rep = self._build_anti_repetition(past_stories)
        system_template = (
            f"{BRIEF_SYSTEM_CONTEXT}\n\n"
            f"{anti_rep}\n\n"
            f"Return ONLY valid JSON in this exact shape:\n"
            f'{{"story_brief": "<the full 80-140 word Seedance prompt, one paragraph>", '
            f'"genre": "{subject}", '
            f'"title_hint": "<3-5 word evocative YouTube Shorts title, no emojis>"}}\n\n'
            f"No markdown. No explanation."
        )
        user = (
            f"Today's seed: {seed}\n"
            f"SCENARIO ASSIGNED: {subject.upper()}\n\n"
            f"Use the {subject.upper()} archetype from your system prompt — match its tone, "
            f"its motion shape, and its audio cues. Pick a SPECIFIC location, subject, and "
            f"moment that fits this archetype. The clip must end MID-ACTION (do not resolve, "
            f"do not cut to black, do not slow to a stop — the camera is still moving when the "
            f"12 seconds elapse). Return JSON only."
        )
        print(f"[BriefGenerator] Cinematic drone — scenario: {subject}", flush=True)

        result = self._llm.ask_json(
            system_template, user, max_tokens=600, label="BriefGenerator",
        )
        result["story_mode"] = "standalone"
        return result

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

        result = self._llm.ask_json(
            full_system, prompt, max_tokens=500, label="BriefGenerator",
        )
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
        # Final part of a bounded series — used to swap in stricter closure
        # rules and pass the prior scripts (not just briefs) so Claude can see
        # which threads need to be resolved.
        is_final_part = (SERIES_PARTS > 0 and part_number == SERIES_PARTS)

        if previous_parts:
            if is_final_part:
                # Include the full script text of each prior part so Claude
                # can identify the open mysteries it must resolve. Briefs
                # alone are too vague to support a real conclusion.
                recap_blocks = []
                for i, p in enumerate(previous_parts):
                    block = [f"--- Part {i+1} ---"]
                    block.append(f"BRIEF: {p.get('story_brief', 'N/A')}")
                    script = (p.get("script_text") or "").strip()
                    if script:
                        block.append(f"FULL SCRIPT: {script}")
                    recap_blocks.append("\n".join(block))
                recap = "\n\n".join(recap_blocks)
                series_context = (
                    f"PREVIOUS PARTS (with full scripts — these are the threads you MUST close):\n\n"
                    f"{recap}\n\n"
                    f"Now write Part {part_number} — the FINAL part. End the story."
                )
            else:
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
        if _preset.serialized_canon and episode_number:
            arc_context_block = format_arc_context(episode_number)
            from modules.arc_context import resolve_arc
            arc_info = resolve_arc(episode_number)
            arc_number = arc_info["arc_number"] if arc_info else None
            if arc_number:
                characters_block = format_characters_context(
                    arc_number, episode_number, session=self._session
                )

        # Preset-7 also gets a "character_form" field in the JSON output
        if _preset.serialized_canon:
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

        # Append the strict closure rules LAST so they're the final thing Claude
        # reads before generating — highest recency/salience in the prompt.
        if is_final_part:
            system = system + FINAL_PART_RULES

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

        result = self._llm.ask_json(
            full_system, prompt, max_tokens=500, label="BriefGenerator",
        )
        result["story_mode"] = "series"
        result["series_id"] = series_id
        result["part_number"] = part_number
        if episode_number is not None:
            result["episode_number"] = episode_number
        if arc_number is not None:
            result["arc_number"] = arc_number
        # Default character_form for preset-7 if Claude omitted it.
        if _preset.serialized_canon:
            form = str(result.get("character_form", "")).strip().lower()
            if form not in ("normal", "transformed", "both"):
                form = "normal"
            result["character_form"] = form
        return result

import os
import json
import anthropic
from config import CLAUDE_MODEL, SHOTS_COUNT, SHOT_DURATION, VIDEO_STYLE, PRESET_NAME, GENRES, BRIEF_SYSTEM_CONTEXT

SYSTEM_PROMPT = """You are a script writer for short {preset_name} videos. The genres you work with are: {genre_list}.

CONTEXT:
{brief_context}

LANGUAGE RULES:
- Use short, simple sentences. Max 15 words per sentence.
- Use everyday words. If a 12-year-old wouldn't know the word, replace it.
- No fancy vocabulary.
- Titles: 3-5 words max, plain English.
- The narrative should match the tone of {preset_name} — adapt your voice to the content style.

Your output MUST be valid JSON with exactly this structure:
{{
  "visual_style": "A reusable style prefix that EVERY shot must start with. The art style MUST be {video_style}. Describes: art style, color palette, lighting mood, and the main character's fixed appearance (species, clothing, build, features). Be very specific — every detail matters for visual consistency.",
  "character_image_prompt": "A detailed prompt for generating a SINGLE reference image of the main character in {video_style} style. This image will be used as the first frame of every video shot. Describe the character in a specific pose, in the story's environment. Include all physical details from visual_style. 9:16 vertical composition.",
  "narrative": "Full voiceover narration. MUST be timed to fit the video — write EXACTLY {word_count_min}-{word_count_max} words (about {total_duration} seconds of speaking). Match the tone to {preset_name}. Every second counts. No filler.",
  "title": "Short plain title (3-5 words, max 50 chars)",
  "description": "YouTube description (100-150 words)",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "shots": [
    "Shot 1: description WITHOUT the style prefix (it gets added automatically)",
    ...
  ]
}}

CRITICAL RULES for visual consistency:
- visual_style MUST describe the main character with SPECIFIC physical details. Be precise — "a cat" is too vague; "a fluffy orange tabby cat wearing a green apron and round glasses" is correct.
- Every shot must feature the same character/subject — never introduce a new character.
- Keep the same environment and lighting across all shots unless the story explicitly moves locations.

Shot prompt rules:
- 1-2 sentences per shot, highly specific and visual
- Include camera movement: slow pan, dolly push, orbital shot, tracking shot, etc.
- Include lighting/atmosphere appropriate for {preset_name}
- Each shot = ~{shot_duration} seconds of content
- Optimized for AI text-to-video generation
- No dialogue or text overlays — visual storytelling only
- Do NOT repeat the visual_style in the shot text — it will be prepended automatically

Return JSON only. No markdown fences, no explanation."""


class ScriptGenerator:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def generate(self, story_brief: str, genre: str) -> dict:
        total_duration = SHOTS_COUNT * SHOT_DURATION
        # ~2.5 words per second for narration pace
        word_count_min = int(total_duration * 2.3)
        word_count_max = int(total_duration * 2.8)

        system = SYSTEM_PROMPT.format(
            preset_name=PRESET_NAME,
            genre_list=", ".join(GENRES),
            brief_context=BRIEF_SYSTEM_CONTEXT,
            word_count_min=word_count_min,
            word_count_max=word_count_max,
            total_duration=total_duration,
            video_style=VIDEO_STYLE,
            shot_duration=SHOT_DURATION,
        )

        prompt = (
            f"Preset: {PRESET_NAME}\n"
            f"Art style: {VIDEO_STYLE}\n"
            f"Genre: {genre}\n"
            f"Story brief: {story_brief}\n"
            f"Total video duration: {total_duration} seconds ({SHOTS_COUNT} shots × {SHOT_DURATION}s each)\n\n"
            f"Generate a {SHOTS_COUNT}-shot script. "
            f"The narrative MUST be {word_count_min}-{word_count_max} words to fill exactly {total_duration} seconds. "
            f"Return valid JSON only."
        )
        print(f"[ScriptGenerator] Preset: {PRESET_NAME}, style: {VIDEO_STYLE}, target: {total_duration}s, {word_count_min}-{word_count_max} words", flush=True)

        message = self.client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2000,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        result = _extract_json(raw)

        # Prepend visual_style to every shot for consistent video generation
        style = result.get("visual_style", "")
        if style:
            result["shots"] = [f"{style} {shot}" for shot in result["shots"]]
            print(f"[ScriptGenerator] Style prefix: {style}", flush=True)

        return result


def _extract_json(text: str) -> dict:
    """Tolerant JSON extraction: handles markdown fences, preambles, trailing text."""
    import re
    cleaned = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"No JSON object found in model response: {text!r}")
    return json.loads(cleaned[start : end + 1])

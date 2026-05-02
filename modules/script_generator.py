import os
import json
import anthropic
from config import CLAUDE_MODEL, SHOTS_COUNT, SHOT_DURATION, VIDEO_STYLE, PRESET_NAME, GENRES, BRIEF_SYSTEM_CONTEXT, ACTIVE_PRESET
from modules.skill_loader import load_skills

# --- SKILL LOADING -----------------------------------------------------------
# Common skills apply to ALL presets — universal craft and consistency rules.
# Preset-specific skills layer on top.
COMMON_SKILLS = [
    "storytelling-craft",        # logline, want/need/wound/lie, value shifts, theme
    "episode-architecture",      # hook → development → turn → button format rules
    "character-consistency",     # locked paragraphs, outfit lock, hero ref, two-gen rule
    "video-prompt-builder",      # camera, shot variety, POV, lighting, genre techniques
    "screenplay-director",       # scene blocking, screen direction, action choreography
]
_skills = list(COMMON_SKILLS)

_is_kids = ACTIVE_PRESET in ("preset-4", "preset-5", "preset-6")
if _is_kids:
    _skills.append("kids-content-specialist")

if ACTIVE_PRESET == "preset-7":
    _skills.append("chronicle-of-zenith-canon")

SKILLS_CONTENT = load_skills(*_skills)

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
  "visual_style": "SHORT art direction prefix (max 25 words). ONLY include: art style ({video_style}), color palette, and lighting mood. Do NOT describe the character here — the reference image handles that.",
  "character_image_prompt": "A detailed prompt for generating a SINGLE reference image of the main character in {video_style} style. This image will be used as the first frame of every video shot. Describe the character with SPECIFIC physical details (species, clothing, build, features, accessories). Show a specific pose in the story's environment. 9:16 vertical composition.",
  "narrative": "Full voiceover narration. MUST be timed to fit the video — write EXACTLY {word_count_min}-{word_count_max} words (about {total_duration} seconds of speaking). Match the tone to {preset_name}. Every second counts. No filler. The story MUST feel COMPLETE within this video — beginning, middle, and end. No unfinished sentences, no trailing cliffhangers, no 'to be continued' feel. The viewer should feel satisfied at the end.",
  "title": "Short plain title (3-5 words, max 50 chars)",
  "description": "YouTube description (100-150 words)",
  "tags": ["10-15 YouTube SEO tags: mix broad terms (anime, sci-fi, shorts) + specific terms (character name, story topic) + trending terms (AI generated, anime shorts 2026). No duplicates."],
  "shots": [
    "Shot 1: description WITHOUT the style prefix (it gets added automatically)",
    ...
  ]
}}

CRITICAL RULES for visual consistency:
- visual_style must be SHORT (max 25 words) — art style, color palette, lighting mood ONLY. No character description.
- character_image_prompt must have ALL character details — this generates the reference image that keeps the character consistent across shots.
- Each shot description should focus on ACTION, CAMERA, and ENVIRONMENT — not re-describing the character's appearance.
- Every shot must feature the same character/subject — never introduce a new character.
- Keep the same environment and lighting across all shots unless the story explicitly moves locations.

MANDATORY REVERSE/POV SHOT RULE:
- At least ONE shot (ideally shot 3 or 4) MUST be a POV or over-the-shoulder shot showing WHAT THE CHARACTER SEES — not the character's face.
- In the POV shot: the character is NOT visible (or only their hand/shoulder at frame edge). The camera shows the object, threat, environment, or discovery from the character's viewpoint.
- Example: instead of "close-up of the woman's shocked face as fire erupts" → write "POV shot — the character's hand reaches toward the cracked altar, fire erupts from the cracks, orange light floods the frame"
- This makes the audience FEEL like they are the character. Without it, the video is just a portrait slideshow.

MOTION MANDATE — ZERO TOLERANCE FOR STATIC SHOTS:
- Every shot MUST contain at least ONE concrete physical action verb (walks, turns, reaches, lifts, leans, taps, brushes, tilts, exhales, sits, stands up, squints, etc.).
- Every shot MUST specify camera movement (dolly push, slow pan, orbit, handheld drift). Static cameras are allowed only if a story-beat reason demands it.
- Every shot MUST include at least ONE moving environmental element if the character is mostly still (wind in fabric, dust motes, light flicker, rain, water ripple, shadow shift).
- BANNED: "stands looking thoughtful", "is by the X", "watches", "contemplates", any phrasing where the character "is/was/looks" without an action verb.
- ALL SHOTS USE IMAGE-TO-VIDEO from the SAME locked reference image as first frame. This anchors the character's identity but means every shot starts from a static neutral pose. EVERY shot prompt MUST include a transition phrase that moves the character OUT of that pose: "Starting from a still standing pose, [character] then [action verb]..." or "From a neutral stance, [character] [action]..." or "[Character], previously still, now [action verb]...".
- For wide / pull-back / orbital shots: the character can transition out by the camera moving (e.g. "Camera pulls back rapidly while [character] stands at the center, the world widening around them, dust drifting past in the foreground").
- For POV shots: there's no character on-frame, so the transition is the camera itself ("From a held still frame, the camera dollies forward into the artifact, light rippling across its surface").
- A shot that doesn't include both a motion verb AND a transition out of the static pose will produce a flat, lifeless video. Reject any such shot you wrote — rewrite with concrete motion.

Shot prompt rules:
- 1-2 sentences per shot, highly specific and visual
- Include camera movement: slow pan, dolly push, orbital shot, tracking shot, POV push, over-the-shoulder, etc.
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
        # Combine system prompt with all loaded skills
        full_system = f"{system}\n\n{SKILLS_CONTENT}"

        print(f"[ScriptGenerator] Preset: {PRESET_NAME}, style: {VIDEO_STYLE}, skills loaded: {', '.join(_skills)}", flush=True)
        print(f"[ScriptGenerator] Target: {total_duration}s, {word_count_min}-{word_count_max} words", flush=True)

        message = self.client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2000,
            system=full_system,
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

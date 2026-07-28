from config import SHOTS_COUNT, SHOT_DURATION, VIDEO_STYLE, PRESET_NAME, GENRES, BRIEF_SYSTEM_CONTEXT, DEFAULT_TAGS
from modules.llm import Llm
from modules.preset import active_preset
from modules.skill_loader import load_skills

_preset = active_preset()

# --- SKILL LOADING -----------------------------------------------------------
# Common skills apply to ALL presets — universal craft and consistency rules.
# The active preset's `extra_skills` layer on top (kids specialist, series canon).
COMMON_SKILLS = [
    "storytelling-craft",        # logline, want/need/wound/lie, value shifts, theme
    "episode-architecture",      # hook → development → turn → button format rules
    "character-consistency",     # locked paragraphs, outfit lock, hero ref, two-gen rule
    "video-prompt-builder",      # camera, shot variety, POV, lighting, genre techniques
    "screenplay-director",       # scene blocking, screen direction, action choreography
    "youtube-shorts-optimizer",  # 3-sec hooks, title/description/tag patterns, retention
]
_skills = COMMON_SKILLS + list(_preset.extra_skills)

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
- Each shot description should focus on ACTION, CAMERA, and ENVIRONMENT — not re-describing the main character's appearance.
- DO NOT paste the MAIN character's locked appearance paragraph into shot prompts. The reference image handles the main character's identity automatically; restating it bloats the prompt and confuses the video model. Just refer to them by name and describe their action/pose.
- Don't invent characters not in the brief or the CHARACTER ROSTER (if one is provided below).
- When the CHARACTER ROSTER lists a SUPPORTING character (e.g. an AI hologram, a companion, a council figure) and the story beat involves them speaking or acting, INCLUDE THEM ON-SCREEN in that shot. Paste THE SUPPORTING CHARACTER'S LOCKED APPEARANCE description verbatim inside the shot prompt — but ONLY for supporting characters, never for the main character. Do not let supporting characters live only in the narration — if they speak or act, they must be visible in at least one shot.
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
    def __init__(self, session=None, llm: Llm | None = None):
        """`session` is the Run's SheetSession, used to read the character
        roster. Pass it so the roster is read once per Run; omitting it falls
        back to a single-use session. `llm` is the Claude seam."""
        self._llm = llm or Llm()
        self._session = session

    def generate(self, story_brief: str, genre: str, arc_number: int | None = None, episode_number: int | None = None) -> dict:
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

        # Preset-7: pull the locked appearance paragraphs of every character active
        # in this arc so the LLM can composite supporting characters (e.g. Veth-Ka
        # as a column of pale gold light) into the right shots — not just the main.
        characters_block = ""
        if _preset.serialized_canon and arc_number and episode_number:
            try:
                from modules.characters_reader import format_characters_context
                characters_block = format_characters_context(
                    int(arc_number), int(episode_number), session=self._session
                )
                if characters_block:
                    print(f"[ScriptGenerator] Roster injected: arc={arc_number}, ep={episode_number}", flush=True)
            except Exception as exc:
                print(f"[ScriptGenerator] Roster injection failed (non-fatal): {exc}", flush=True)

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
        # Combine system prompt with all loaded skills + roster (if any)
        full_system = f"{system}\n\n{SKILLS_CONTENT}"
        if characters_block:
            full_system = f"{full_system}\n\n{characters_block}"

        print(f"[ScriptGenerator] Preset: {PRESET_NAME}, style: {VIDEO_STYLE}, skills loaded: {', '.join(_skills)}", flush=True)
        print(f"[ScriptGenerator] Target: {total_duration}s, {word_count_min}-{word_count_max} words", flush=True)

        result = self._llm.ask_json(
            full_system, prompt, max_tokens=2000, label="ScriptGenerator",
        )

        # Prepend visual_style to every shot for consistent video generation
        style = result.get("visual_style", "")
        if style:
            result["shots"] = [f"{style} {shot}" for shot in result["shots"]]
            print(f"[ScriptGenerator] Style prefix: {style}", flush=True)

        # Merge base AI/model tags into Claude's content tags. Defaults go LAST
        # so the most discoverable, content-specific tags appear first in the
        # YouTube tag list (YouTube weights leading tags more heavily). Dedupe
        # case-insensitively while preserving original casing of the first occurrence.
        original_tags = list(result.get("tags") or [])
        seen = {t.lower() for t in original_tags}
        merged = list(original_tags) + [t for t in DEFAULT_TAGS if t.lower() not in seen]
        result["tags"] = merged
        print(f"[ScriptGenerator] Tags: {len(original_tags)} content + {len(merged) - len(original_tags)} default = {len(merged)}", flush=True)

        return result


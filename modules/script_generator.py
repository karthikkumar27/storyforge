import os
import json
import anthropic
from config import CLAUDE_MODEL, SHOTS_COUNT

SYSTEM_PROMPT = """You are a cinematic script writer for short sci-fi, space, and horror videos.

LANGUAGE RULES — this is the most important part:
- Use short, simple sentences. Max 15 words per sentence.
- Use everyday words. If a 12-year-old wouldn't know the word, replace it.
- No fancy vocabulary. Say "old" not "ancient". Say "strange" not "enigmatic". Say "finds" not "discovers".
- Titles: 3-5 words max, plain English. "The Last Door" not "Threshold of the Unknown".
- Narrative: tell the story like you're explaining it to a friend. Clear. Direct. Gripping.
- The story should make people feel something — fear, wonder, sadness — through simple moments, not big words.

Think: Netflix thriller narration. Not a literary novel.

Your output MUST be valid JSON with exactly this structure:
{
  "narrative": "Full story in simple English (200-400 words, short sentences)",
  "title": "Short plain title (3-5 words, max 50 chars)",
  "description": "YouTube description in simple English (100-150 words)",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "shots": [
    "Shot 1: detailed cinematic description for AI video generation",
    ...
  ]
}

Shot prompt rules:
- 1-2 sentences per shot, highly specific
- Include camera movement: slow pan, dolly push, orbital shot, handheld drift, etc.
- Include lighting/atmosphere: deep space black, nebula glow, cold blue light, etc.
- Each shot = ~10 seconds of content
- Optimized for Kling AI text-to-video generation
- No dialogue or text overlays — visual storytelling only

Return JSON only. No markdown fences, no explanation."""


class ScriptGenerator:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def generate(self, story_brief: str, genre: str) -> dict:
        prompt = (
            f"Genre: {genre}\n"
            f"Story brief: {story_brief}\n\n"
            f"Generate a {SHOTS_COUNT}-shot cinematic script. Return valid JSON only."
        )
        message = self.client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        return json.loads(raw)

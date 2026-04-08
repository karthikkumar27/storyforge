import os
import json
import anthropic
from config import CLAUDE_MODEL, SHOTS_COUNT

SYSTEM_PROMPT = """You are a cinematic script writer specializing in sci-fi, outer space, and subtle horror.
Write short-form cinematic scripts for AI video generation.

Your output MUST be valid JSON with exactly this structure:
{
  "narrative": "Full readable narrative script (200-400 words)",
  "title": "Compelling video title (max 70 chars)",
  "description": "YouTube description (100-150 words, includes genre mood)",
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

import os
import random
from datetime import date

import anthropic

GENRES = ["sci-fi", "horror", "space", "blend"]

SYSTEM_PROMPT = """You are a visionary cinematic storyteller specializing in atmospheric short films.
Your specialty: sci-fi, outer space, and subtle psychological horror — often blended.

Generate a single original story brief: a 2-3 sentence cinematic premise for a 60-90 second
AI-generated video. The brief should:
- Be atmospheric, evocative, and visually driven (not dialogue-heavy)
- Suggest strong visual imagery (locations, lighting, movement)
- Have emotional resonance: wonder, dread, isolation, awe, or mystery
- Feel like the premise of a festival short film, not a TV episode

Return ONLY valid JSON:
{"story_brief": "...", "genre": "sci-fi|horror|space|blend", "title_hint": "..."}

No markdown. No explanation."""


class BriefGenerator:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def generate(self) -> dict:
        genre = random.choice(GENRES)
        seed = f"{date.today().isoformat()}-{random.randint(1000, 9999)}"
        prompt = (
            f"Today's seed: {seed}\n"
            f"Suggested genre: {genre}\n\n"
            "Generate a fresh, original cinematic story brief. "
            "You may use the suggested genre or blend it with others. Return JSON only."
        )
        import json
        message = self.client.messages.create(
            model="claude-opus-4-6",
            max_tokens=300,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return json.loads(message.content[0].text.strip())

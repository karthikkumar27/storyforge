import os
import random
from datetime import date

import anthropic

GENRES = ["sci-fi", "horror", "space", "blend"]

SYSTEM_PROMPT = """You are a short film story writer for sci-fi, space, and horror videos.

Write a 2-3 sentence story idea for a 60-90 second video.

LANGUAGE RULES:
- Use simple, everyday English. Short sentences.
- No big words. Say "old ship" not "derelict vessel". Say "strange signal" not "anomalous transmission".
- The idea should be easy to picture in your head right away.
- Make it feel real and personal — one person, one moment, one mystery.
- It should make people curious: "what happens next?"

Good example: "A woman finds her dead mother's phone still sending texts. The messages know things only her mother could know. She has to decide — is this a gift or a warning?"

Bad example: "An astronaut encounters an inexplicable phenomenon of extraterrestrial origin that challenges her perception of mortality."

Return ONLY valid JSON:
{"story_brief": "...", "genre": "sci-fi|horror|space|blend", "title_hint": "3-5 word plain title"}

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

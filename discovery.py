"""
discovery.py — Run manually to evaluate and auto-select the best free AI video tool.
Usage: python discovery.py
Prints a ranked table of AI video tools and the winner.
"""
import json
import os

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

RUBRIC = """Evaluate each AI video generation tool against these criteria (score 0-5 each):
1. Free tier availability (5 = generous free credits daily, 0 = paid only)
2. API access (5 = full REST API, 0 = web UI only)
3. Cinematic quality (5 = photorealistic with cinematic camera movement, 0 = basic)
4. Story/narrative support (5 = long prompts with full scene control, 0 = short prompts only)
5. Reliability and uptime (5 = stable production API, 0 = frequently down)

Tools to evaluate:
- Kling AI (klingai.com)
- HailuoAI / MiniMax (hailuoai.com)
- Runway Gen-4 (runwayml.com)
- Luma Dream Machine (lumalabs.ai)
- Pika Labs (pika.art)

Return a JSON array sorted by total score descending:
[
  {
    "name": "Tool Name",
    "scores": {
      "free_tier": 0,
      "api_access": 0,
      "cinematic_quality": 0,
      "story_support": 0,
      "reliability": 0
    },
    "total": 0,
    "free_tier_notes": "brief description of free tier",
    "api_base_url": "https://..."
  }
]

Return JSON only. No markdown fences."""

SYSTEM = "You are an expert in AI video generation tools with up-to-date knowledge of their capabilities, pricing, and API availability."


def discover_best_tool() -> dict:
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2000,
        system=SYSTEM,
        messages=[{"role": "user", "content": RUBRIC}],
    )
    tools = json.loads(message.content[0].text.strip())
    winner = tools[0]

    print("\n=== AI Video Tool Discovery Results ===\n")
    print(f"{'Tool':<28} {'Total':>6}  Free tier")
    print("-" * 60)
    for t in tools:
        print(f"{t['name']:<28} {t['total']:>5}/25  {t['free_tier_notes']}")

    print(f"\n✓ Winner: {winner['name']} (score: {winner['total']}/25)")
    print(f"  API: {winner.get('api_base_url', 'check developer docs')}")
    print(f"\nTo use this tool, update VIDEO_TOOL in config.py\n")
    return winner


if __name__ == "__main__":
    discover_best_tool()

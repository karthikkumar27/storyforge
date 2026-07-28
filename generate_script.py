"""Generate brief + script only — no video, no audio, no upload.
Writes the story brief and script to the Google Sheet with status 'script_ready'.

Usage: python generate_script.py
"""
import json
from dotenv import load_dotenv
load_dotenv()

from config import PRESET_NAME
from modules.episode_ledger import get_episode_ledger
from modules.sheet_access import SheetSession
from modules.brief_generator import BriefGenerator
from modules.script_generator import ScriptGenerator


def main():
    # Same claim flow as the full pipeline, which is what makes this a genuine
    # rehearsal of it: anything that breaks claim_next() breaks here first, for
    # the price of a Claude call instead of a full episode.
    ledger = get_episode_ledger(SheetSession())
    claim = ledger.claim_next()

    if claim.needs_brief:
        brief_data = BriefGenerator().generate(**claim.brief_context.as_kwargs())
        claim = ledger.start(brief_data)

    if claim.episode is None:
        print("[ScriptOnly] No pending rows found")
        return

    episode = claim.episode
    print(f"\n[ScriptOnly] Preset: {PRESET_NAME}", flush=True)
    print(f"[ScriptOnly] Story: {episode.story_brief}", flush=True)
    print(f"[ScriptOnly] Genre: {episode.genre}", flush=True)

    script = ScriptGenerator().generate(episode.story_brief, episode.genre)
    ledger.record(episode.row_index, script=script["narrative"], status="script_ready")

    print(f"\n{'='*50}")
    print(f"Title:    {script['title']}")
    print(f"Style:    {script.get('visual_style', 'N/A')}")
    print(f"\nNarrative:\n{script['narrative']}")
    print(f"\nShots ({len(script['shots'])}):")
    for i, shot in enumerate(script["shots"], 1):
        print(f"  {i}. {shot}")
    print(f"\nTags: {', '.join(script.get('tags', []))}")
    print(f"{'='*50}")
    print(f"\n[ScriptOnly] Written to sheet with status 'script_ready'")
    print("[ScriptOnly] To produce the full video, change status to 'pending' and run the pipeline")


if __name__ == "__main__":
    main()

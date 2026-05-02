"""Generate brief + script only — no video, no audio, no upload.
Writes the story brief and script to the Google Sheet with status 'script_ready'.

Usage: python generate_script.py
"""
import json
from dotenv import load_dotenv
load_dotenv()

from config import STORY_MODE, PRESET_NAME, ACTIVE_PRESET, GENRES
from modules.gsheet_reader import get_episode_reader
from modules.brief_generator import BriefGenerator
from modules.script_generator import ScriptGenerator


def main():
    reader = get_episode_reader()
    row = reader.get_pending_row()

    if not row:
        previous_parts = []
        past_stories = reader.get_past_stories(limit=20)
        print(f"[ScriptOnly] {len(past_stories)} past stories loaded for anti-repetition", flush=True)

        if STORY_MODE == "series":
            series_id = reader.get_latest_incomplete_series()
            if series_id:
                previous_parts = reader.get_series_parts(series_id)
                print(f"[ScriptOnly] Continuing series {series_id}, part {len(previous_parts) + 1}", flush=True)
            else:
                print("[ScriptOnly] Starting new series", flush=True)

        # Preset-7 — compute next episode number across the continuous 200-ep series
        episode_number = None
        if ACTIVE_PRESET == "preset-7":
            episode_number = reader.get_next_episode_number(GENRES)
            print(f"[ScriptOnly] Preset-7 — generating episode #{episode_number}", flush=True)

        brief_data = BriefGenerator().generate(
            previous_parts=previous_parts,
            past_stories=past_stories,
            episode_number=episode_number,
        )
        reader.append_pending_row(brief_data)
        row = reader.get_pending_row()

    if not row:
        print("[ScriptOnly] No pending rows found")
        return

    print(f"\n[ScriptOnly] Preset: {PRESET_NAME}", flush=True)
    print(f"[ScriptOnly] Story: {row['story_brief']}", flush=True)
    print(f"[ScriptOnly] Genre: {row['genre']}", flush=True)

    script = ScriptGenerator().generate(row["story_brief"], row["genre"])
    reader.update_script(row["row_index"], script["narrative"])
    reader.update_status(row["row_index"], "script_ready")

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

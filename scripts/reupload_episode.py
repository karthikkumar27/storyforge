#!/usr/bin/env python3
"""Re-upload an already-archived episode MP4 to YouTube.

Use when the main pipeline failed at the upload step (most common cause:
expired YouTube OAuth refresh token) and you don't want to re-generate the
video. The MP4 is already in `videos/` thanks to the pre-upload archive in
orchestrator.py, so all we need is fresh title/description/tags + a working
YouTube token + a sheet patch.

Usage:
    python scripts/reupload_episode.py --row 4 --video videos/20260504-0000_The-Chronicle-of-Zenith-Ep-3-The-Blue-Dot.mp4

    # Allow re-upload of a row already marked done (will create a duplicate YouTube video):
    python scripts/reupload_episode.py --row 4 --video <path> --force
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(override=True)

from config import ACTIVE_PRESET
from modules.gsheet_reader import get_episode_reader
from modules.script_generator import ScriptGenerator
from modules.youtube_uploader import YouTubeUploader


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--row", type=int, required=True, help="1-based sheet row index of the episode to re-upload")
    ap.add_argument("--video", type=str, required=True, help="Path to the archived MP4")
    ap.add_argument("--force", action="store_true", help="Allow re-upload even if row is already 'done'")
    args = ap.parse_args()

    video_path = Path(args.video).expanduser().resolve()
    if not video_path.exists():
        raise SystemExit(f"Video not found: {video_path}")

    reader = get_episode_reader()
    records = reader.sheet.get_all_records()
    if args.row < 2 or args.row - 2 >= len(records):
        raise SystemExit(f"Row {args.row} out of range (sheet has {len(records) + 1} rows)")
    row = records[args.row - 2]
    row_index = args.row

    status = str(row.get("status", "")).strip().lower()
    youtube_url = str(row.get("youtube_url", "")).strip()
    title_raw = str(row.get("title", "")).strip()
    story_brief = str(row.get("story_brief", "")).strip()
    genre = str(row.get("genre", "")).strip()
    episode_number = row.get("episode_number", "")

    if status == "done" and youtube_url and not args.force:
        raise SystemExit(
            f"Row {row_index} is already 'done' with URL {youtube_url}. "
            "Pass --force to re-upload anyway (creates a duplicate YouTube video)."
        )
    if not story_brief:
        raise SystemExit(f"Row {row_index} has no story_brief — cannot regenerate metadata.")

    print(f"=== RE-UPLOAD ===")
    print(f"  Preset:   {ACTIVE_PRESET}")
    print(f"  Row:      {row_index}  (status={status!r})")
    print(f"  Title:    {title_raw}")
    print(f"  Episode#: {episode_number}")
    print(f"  Video:    {video_path}  ({video_path.stat().st_size / 1024 / 1024:.1f} MB)")
    print()

    confirm = input("Regenerate metadata + upload to YouTube? [y/N] ").strip().lower()
    if confirm not in ("y", "yes"):
        print("Cancelled.")
        return

    print("\n[1/3] Regenerating title/description/tags via ScriptGenerator (~$0.025)...")
    script_result = ScriptGenerator().generate(story_brief, genre)
    print(f"      → title:       {script_result['title']}")
    print(f"      → description: {len(script_result['description'])} chars")
    print(f"      → tags:        {len(script_result['tags'])} tags")

    # Mirror orchestrator.py title formatting so re-uploads match what a
    # fresh pipeline run would have produced.
    if ACTIVE_PRESET == "preset-7" and episode_number:
        episode_title = script_result["title"]
        script_result["title"] = f"The Chronicle of Zenith — Ep {episode_number}: {episode_title}"
        print(f"      → final YT title: {script_result['title']}")
    elif str(row.get("story_mode", "")).strip() == "series" and row.get("part_number"):
        part_num = row.get("part_number")
        episode_title = script_result["title"]
        series_id = str(row.get("series_id", "")).strip()
        series_title = episode_title  # fallback for Part 1
        if series_id:
            parts = reader.get_series_parts(series_id)
            if parts:
                series_title = parts[0].get("title", episode_title)
        if str(part_num) == "1":
            script_result["title"] = f"{episode_title} - Part 1"
        else:
            script_result["title"] = f"{series_title}: {episode_title} - Part {part_num}"
        print(f"      → final YT title: {script_result['title']}")

    print("\n[2/3] Uploading to YouTube...")
    reader.update_status(row_index, "uploading")
    try:
        url = YouTubeUploader().upload(str(video_path), script_result)
    except Exception as exc:
        reader.update_error(row_index, str(exc))
        raise SystemExit(f"Upload failed: {exc}")
    print(f"      → {url}")

    print("\n[3/3] Updating sheet to done...")
    reader.update_done(row_index, url)

    print(f"\n=== DONE ===\n  YouTube: {url}")


if __name__ == "__main__":
    main()

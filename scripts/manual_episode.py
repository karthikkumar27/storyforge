#!/usr/bin/env python3
"""Manual / à-la-carte episode generator.

Reads a single row from the MAIN GOOGLE_SHEET_ID (not preset-7's dedicated
sheet), generates a video using Atlas Cloud, and saves the MP4 locally.
Skips ElevenLabs voiceover, BGM mixing, title/end cards, and YouTube upload —
the result is just the stitched Seedance shots with their native audio.

Useful for:
- Ad-hoc tests when you don't want to burn through the preset-7 episode counter
- Iterating on shots/prompts without spending on narration + upload
- Generating videos for any preset using YOUR shots written directly in the sheet

Sheet input flexibility (in priority order):
1. If row has `shots` text in story_brief separated by `|`, use those verbatim
   (one shot per `|` segment). Bypasses Claude entirely.
2. Otherwise, runs ScriptGenerator on story_brief to produce shots normally.

Reference image:
- If `ref_image_url` cell is filled, use it as-is for image-to-video anchoring
- Otherwise generate a fresh one via GPT Image 2 (~$0.006)

Usage:
    python scripts/manual_episode.py                # process first 'pending' row
    python scripts/manual_episode.py --row 5        # process specific row by number
    python scripts/manual_episode.py --dry-run      # plan only, no API calls
    python scripts/manual_episode.py --no-storyboards  # use single ref image for all shots
    python scripts/manual_episode.py --chain        # each storyboard also sees the previous shot's last frame

--chain is independent of the active preset's `chain_reference_frames`
capability: this script deliberately bypasses the orchestrator so the same
sheet row can be run both ways and compared.
"""
import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Make project root importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from config import (
    SHOT_DURATION, SHOTS_COUNT, ASPECT_RATIO, VIDEO_STYLE,
    ATLAS_BASE_URL, ATLAS_VIDEO_MODEL_I2V, ATLAS_VIDEO_MODEL_T2V,
)
from modules.episode_ledger import get_episode_ledger
from modules.sheet_access import SheetSession
from modules.image_generator import AtlasImageGenerator
from modules.script_generator import ScriptGenerator
from modules.storyboard import build_storyboards, ChainedStoryboards
from modules.video_producer import AtlasVideoProducer

PROJECT_ROOT = Path(__file__).parent.parent
VIDEOS_DIR = PROJECT_ROOT / "videos" / "manual"


def slugify(text: str, max_len: int = 60) -> str:
    import re
    if not text:
        return "manual-episode"
    slug = text.replace("—", "-").replace("–", "-")
    slug = re.sub(r'[\\/*?:"<>|]', "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    slug = re.sub(r"-+", "-", slug)
    return slug[:max_len].rstrip("-_") or "manual-episode"


def pick_row(ledger, row_arg: int | None) -> tuple[int, dict]:
    """Return (row_index, row_dict). Row index is 1-based."""
    if row_arg is not None:
        # User passed an explicit row number (1-based, header is row 1)
        try:
            return row_arg, ledger.row(row_arg)
        except IndexError as exc:
            raise SystemExit(str(exc))

    # Auto-pick first pending row — same claim the pipeline would make
    claim = ledger.claim_next()
    if claim.episode is None:
        raise SystemExit(
            "No 'pending' rows in main sheet. Set status=pending on the row you "
            "want to process, or pass --row N."
        )
    return claim.episode.row_index, ledger.row(claim.episode.row_index)


def parse_inline_shots(story_brief: str) -> list[str] | None:
    """If the brief contains pipe-separated shots (Shot 1: ... | Shot 2: ...),
    return them as a list. Otherwise None — caller falls back to ScriptGenerator."""
    if "|" not in story_brief:
        return None
    parts = [p.strip() for p in story_brief.split("|") if p.strip()]
    if len(parts) >= 2:
        return parts
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--row", type=int, help="Specific 1-based row number to process (default: first pending)")
    ap.add_argument("--dry-run", action="store_true", help="Plan only — no API calls")
    ap.add_argument("--no-storyboards", action="store_true",
                    help="Use single ref image for all shots (skip per-shot GPT Image 2 Edit). Cheaper but may show character drift.")
    ap.add_argument("--chain", action="store_true",
                    help="Chain reference frames: each shot's storyboard also sees the "
                         "previous shot's last frame. Fixes character drift across shots.")
    args = ap.parse_args()

    # Always the main sheet, whichever preset is active — this script is for
    # ad-hoc work and must not touch preset-7's episode timeline.
    session = SheetSession()
    ledger = get_episode_ledger(session, sheet_env="GOOGLE_SHEET_ID")
    row_idx, row = pick_row(ledger, args.row)

    title = str(row.get("title", "")).strip() or "(untitled)"
    story_brief = str(row.get("story_brief", "")).strip()
    genre = str(row.get("genre", "")).strip() or "manual"
    ref_image_url = str(row.get("ref_image_url", "")).strip()
    # Saved alongside ref_image_url by an earlier run that generated it, so
    # the pair can never drift apart on a rerun -- see the priority chain
    # around step 2 below.
    saved_appearance = str(row.get("character_appearance", "")).strip()

    if not story_brief:
        raise SystemExit(f"Row {row_idx} has no story_brief. Add one and re-run.")

    print(f"=== MANUAL EPISODE — row {row_idx} ===")
    print(f"  Title:     {title}")
    print(f"  Genre:     {genre}")
    print(f"  Brief:     {story_brief[:100]}{'...' if len(story_brief) > 100 else ''}")
    print(f"  Ref image: {ref_image_url[:80] + '...' if ref_image_url else '(will generate)'}")

    inline_shots = parse_inline_shots(story_brief)
    if inline_shots:
        print(f"  Shots:     {len(inline_shots)} inline (parsed from `|`-separated story_brief)")
    else:
        print(f"  Shots:     will run ScriptGenerator on story_brief")

    # Cost preview
    n_shots = len(inline_shots) if inline_shots else SHOTS_COUNT
    # --chain wins over --no-storyboards (see step 3 below), so storyboards are
    # only actually free when neither asks for them.
    skip_storyboards = args.no_storyboards and not args.chain
    storyboard_cost = 0.0 if skip_storyboards else n_shots * 0.006
    image_gen_cost = 0.0 if ref_image_url else 0.006
    seedance_cost_per_clip = 0.144 if SHOT_DURATION == 8 else 0.18
    video_cost = n_shots * seedance_cost_per_clip
    script_cost = 0.0 if inline_shots else 0.025
    total = storyboard_cost + image_gen_cost + video_cost + script_cost

    print(f"\n=== ESTIMATED COST ===")
    if not inline_shots:
        print(f"  Script generation:           ${script_cost:.3f}")
    if not ref_image_url:
        print(f"  Reference image:             ${image_gen_cost:.3f}")
    if not skip_storyboards:
        print(f"  Per-shot storyboards ({n_shots}):    ${storyboard_cost:.3f}")
    print(f"  Video clips ({n_shots} × {SHOT_DURATION}s):       ${video_cost:.3f}")
    print(f"  ─────────────────────────────")
    print(f"  TOTAL:                        ${total:.3f}")

    if args.dry_run:
        print("\nDry run — no API calls.")
        return

    confirm = input("\nProceed? [y/N] ").strip().lower()
    if confirm not in ("y", "yes"):
        print("Cancelled.")
        return

    # ===== 1. Resolve shots and visual style =====
    if inline_shots:
        shots = inline_shots
        visual_style = ""
    else:
        print("\n[1/4] Generating script...")
        script_result = ScriptGenerator().generate(story_brief, genre)
        shots = script_result["shots"]
        visual_style = script_result.get("visual_style", "")
        print(f"      → {len(shots)} shots produced")

    # ===== 2. Resolve reference image =====
    # char_prompt is only trustworthy as this image's appearance when THIS
    # run is the one that used it to generate the reference image below --
    # a rerun's ScriptGenerator call is non-deterministic and must never be
    # paired with an image an earlier run saved. See the priority chain
    # after step 3.
    char_prompt = None
    image_generated_this_run = False
    if not ref_image_url:
        print("\n[2/4] Generating reference image...")
        if inline_shots:
            char_prompt = (
                f"A single-character 9:16 vertical {VIDEO_STYLE} portrait "
                f"based on this scene description: {shots[0][:300]}"
            )
        else:
            char_prompt = script_result.get(
                "character_image_prompt",
                f"9:16 vertical reference for {genre} short film, cinematic, no text",
            )
        ref_image_url = AtlasImageGenerator().generate(char_prompt)
        image_generated_this_run = True
        # Write back immediately so a rerun reuses it rather than paying
        # again. The prompt that produced it rides along in the same write,
        # as character_appearance, so the pair can never drift apart.
        try:
            ledger.record(row_idx, ref_image_url=ref_image_url, character_appearance=char_prompt)
            session.flush()
        except Exception as exc:
            print(f"      (could not save ref image to sheet: {exc})")
        print(f"      → {ref_image_url[:80]}...")
    else:
        print("\n[2/4] Using existing ref_image_url from sheet")

    # The locked appearance passed to the storyboard builders below. The rule
    # is one sentence: use the words that describe the image actually in
    # hand. Priority: if THIS run generated the reference image, its prompt
    # -- a fresh image always gets fresh words; else the sheet's saved
    # pairing, which matches the reused ref_image_url by construction; else
    # nothing.
    appearance = char_prompt if image_generated_this_run else (saved_appearance or None)

    # ===== 3. Per-shot storyboards (optional) =====
    storyboard_urls = None
    storyboard_supplier = None
    if args.chain:
        print("\n[3/4] Chained storyboards — each shot sees the previous frame")
        storyboard_supplier = ChainedStoryboards(
            ref_image_url, style=VIDEO_STYLE, appearance=appearance,
        )
    elif not args.no_storyboards:
        print("\n[3/4] Generating per-shot storyboards...")
        storyboard_urls = build_storyboards(
            shots, ref_image_url, style=VIDEO_STYLE, appearance=appearance,
        )
    else:
        print("\n[3/4] Skipping per-shot storyboards (--no-storyboards)")

    # ===== 4. Video generation + stitch =====
    print("\n[4/4] Generating video shots...")
    producer = AtlasVideoProducer()
    # Prepend visual_style to each shot prompt if present (matches main pipeline)
    if visual_style:
        shots = [f"{visual_style} {s}" for s in shots]
    stitched_path = producer.produce(
        shots,
        reference_image_url=ref_image_url,
        storyboard_urls=storyboard_urls,
        storyboard_supplier=storyboard_supplier,
    )
    print(f"      → stitched: {stitched_path}")

    # ===== Archive =====
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M")
    slug = slugify(title)
    dest = VIDEOS_DIR / f"{ts}_{slug}.mp4"
    shutil.copy2(stitched_path, dest)

    # Update sheet
    try:
        ledger.record(row_idx, status="manual_done")
    except Exception as exc:
        print(f"  (could not update sheet status: {exc})")

    print(f"\n=== DONE ===")
    print(f"  Saved to: {dest}")
    print(f"  Size:     {dest.stat().st_size / 1024 / 1024:.1f} MB")
    duration = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(dest)],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    print(f"  Duration: {duration}s")
    print(f"  Sheet status updated to 'manual_done'")
    print(f"\n  Open with: open {dest}")


if __name__ == "__main__":
    main()

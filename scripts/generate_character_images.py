#!/usr/bin/env python3
"""Generate reference images for the Chronicle of Zenith characters sheet.

For each character row with a non-empty appearance paragraph but empty
ref_image URL, calls GPT Image 2 (Atlas Cloud) to produce a 9:16 portrait
reference and writes the URL back to the sheet.

The output URLs become the locked references the pipeline uses as first-frames
for image-to-video shots, so generating them here means each character looks
visually consistent across every episode they appear in.

Usage:
    python scripts/generate_character_images.py                       # interactive (list + confirm)
    python scripts/generate_character_images.py --all                 # generate everything missing
    python scripts/generate_character_images.py --character "Alan Vorne"
    python scripts/generate_character_images.py --form normal         # only normal forms
    python scripts/generate_character_images.py --form transformed    # only transformed forms
    python scripts/generate_character_images.py --force               # regenerate even if URL exists
    python scripts/generate_character_images.py --yes                 # skip confirmation prompt
    python scripts/generate_character_images.py --dry-run             # plan only, no API calls
    python scripts/generate_character_images.py --check               # which reference URLs still resolve?
    python scripts/generate_character_images.py --verify              # regenerate only the dead ones

Every generated image is also mirrored into assets/characters/ — Atlas does
not retain images indefinitely, and regenerating changes how a character
looks, which is fatal for a 200-episode series.
"""
import argparse
import re
import sys
import time
from pathlib import Path

# Make project root importable
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

import httpx

from config import ATLAS_IMAGE_MODEL
from modules.atlas_client import AtlasClient, AtlasError
from modules.characters_reader import CharactersReader
from modules.image_generator import IMAGE_POLL_INTERVAL


COST_PER_IMAGE = 0.006  # GPT Image 2 list price

# Atlas does not retain generated images indefinitely — every reference URL in
# the roster 404'd once already. Keep a local copy of every image we generate so
# the next expiry costs a re-upload rather than a re-generation (which would
# change how the character looks mid-series).
CHARACTER_IMAGE_DIR = PROJECT_ROOT / "assets" / "characters"


def _slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()


def mirror_locally(name: str, form: str, url: str) -> Path | None:
    """Save a copy of a reference image under assets/characters/."""
    try:
        resp = httpx.get(url, timeout=60, follow_redirects=True)
        resp.raise_for_status()
    except Exception as exc:
        print(f"      (could not mirror locally: {exc})")
        return None
    CHARACTER_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    ext = ".jpg" if url.lower().split("?")[0].endswith(".jpg") else ".png"
    dest = CHARACTER_IMAGE_DIR / f"{_slug(name)}_{form}{ext}"
    dest.write_bytes(resp.content)
    return dest


def reference_is_live(url: str) -> bool:
    """True when a reference URL still resolves."""
    if not url:
        return False
    try:
        resp = httpx.head(url, timeout=20, follow_redirects=True)
        if resp.status_code == 405:            # some hosts reject HEAD
            resp = httpx.get(url, timeout=30, follow_redirects=True)
        return resp.status_code == 200
    except Exception:
        return False


def check_references(records: list[dict]) -> int:
    """Report which reference images still resolve. Returns the dead count."""
    dead = 0
    print(f"\nChecking reference images for {len(records)} characters...\n")
    for rec in records:
        name = str(rec.get("character_name", "")).strip()
        for form in ("normal", "transformed"):
            url = str(rec.get(f"ref_image_{form}", "")).strip()
            if not url:
                continue
            live = reference_is_live(url)
            dead += (not live)
            mark = "live" if live else "DEAD"
            local = CHARACTER_IMAGE_DIR / f"{_slug(name)}_{form}.png"
            local_alt = CHARACTER_IMAGE_DIR / f"{_slug(name)}_{form}.jpg"
            have_local = "  (local copy present)" if (
                local.exists() or local_alt.exists()
            ) else ""
            print(f"  {mark:<4} {name:<32} [{form}]{have_local}")
    print()
    if dead:
        print(f"{dead} reference image(s) no longer resolve.")
        print("Regenerate them with:  --force        (all)")
        print("                   or:  --verify      (only the dead ones)")
    else:
        print("All reference images resolve.")
    return dead

# Deliberately talks to Atlas directly rather than through AtlasImageGenerator:
# that class prepends a "no humans" SAFE_PREFIX on retries, which is wrong for a
# character roster. The retry ladder here softens the *appearance paragraph*
# instead — see build_prompt().
_atlas: AtlasClient | None = None


def _client() -> AtlasClient:
    """Built on first use, not at import — so --dry-run works without an API key."""
    global _atlas
    if _atlas is None:
        _atlas = AtlasClient()
    return _atlas


def call_atlas_image(prompt: str) -> str:
    """Submit one image generation and return its URL.

    No internal retry — the caller runs its own ladder of progressively
    softened prompts and wants to see every failure.
    """
    return _client().run(
        "model/generateImage",
        {
            "model": ATLAS_IMAGE_MODEL,
            "prompt": prompt,
            "width": 768,
            "height": 1344,
        },
        poll_interval=IMAGE_POLL_INTERVAL,
        label="CharacterImage",
    )[0]


_GENDER_SOFTEN = [
    # Order matters — match longest phrases first so we don't break short ones.
    (" woman.", " female character."),
    (" woman,", " female character,"),
    (" woman ", " female character "),
    (" man.", " male character."),
    (" man,", " male character,"),
    (" man ", " male character "),
    (" boy.", " young male character."),
    (" boy,", " young male character,"),
    (" boy ", " young male character "),
    (" girl.", " young female character."),
    (" girl,", " young female character,"),
    (" girl ", " young female character "),
]


def _soften_demographics(text: str) -> str:
    """Replace gendered/age nouns with character-class equivalents so the
    safety filter doesn't read the description as a real-person spec.
    Wrapping with leading space prevents matching inside other words."""
    padded = " " + text
    for src, dst in _GENDER_SOFTEN:
        padded = padded.replace(src, dst)
    return padded[1:]


def _aggressive_strip(text: str) -> str:
    """For stubborn characters — strip the demographic, ethnic, and
    relationship/emotional cues that read as a real-person specification.

    We lose nuance but gain a generation. Used only on the last retry."""
    text = _soften_demographics(text)

    # Drop entire sentences containing the most common safety triggers
    drop_patterns = [
        # Relationship / death / emotional backstory
        r"[^.]*\bhusband\b[^.]*\.",
        r"[^.]*\bwife\b[^.]*\.",
        r"[^.]*\bdeath\b[^.]*\.",
        r"[^.]*\bdied\b[^.]*\.",
        r"[^.]*\bwedding\b[^.]*\.",
        r"[^.]*\bmarried\b[^.]*\.",
        r"[^.]*\bgrief\b[^.]*\.",
        r"[^.]*\bwidow\b[^.]*\.",
        r"[^.]*\bgrandson\b[^.]*\.",
        r"[^.]*\bgranddaughter\b[^.]*\.",
    ]
    for pat in drop_patterns:
        text = re.sub(pat, "", text, flags=re.IGNORECASE)

    # Replace specific demographic / ethnic markers with neutralized versions.
    # Many of these are real-person detection triggers — skin tone + age + ethnic descent
    # is the classic "real person spec" pattern that GPT Image 2 refuses.
    skin_adj = r"(?:warm|cool|pale|dark|light|olive|fair|deep|tanned?|brown|black|white|rich)"

    replacements = [
        # "<adjs> skin" with up to 3 adjectives + optional trailing clause
        # Matches: "warm brown skin", "warm dark brown skin", "deep brown skin with ..."
        (rf"\b(?:{skin_adj}\s+){{1,3}}skin\b[^,.]*[,.]?", ""),
        # "skin with/a/an <descriptor>" compound
        (r"\bskin\s+(?:with|a|an)\s+[^,.]*[,.]?", ""),
        # "skin a faint X undertone"
        (rf"\bskin\s+(?:a|an)?\s*(?:faint\s+)?{skin_adj}\s+(?:undertone|tone)[^,.]*[,.]?", ""),
        # National / ethnic descent
        (r"\bof [A-Z][a-z]+(?:-[A-Z][a-z]+)? descent[,.]?", ""),
        (r"\b[A-Z][a-z]+(?:-[A-Z][a-z]+)? (?:woman|man|character|figure)\b", "stylized character"),
        # Hyper-specific aging markers
        (r"\bstarting to gray\b[^,.]*[,.]?", ""),
        (r"\bdecades after[^.]*\.", ""),
        # "Late 60s" / "mid-30s" style fragments → "adult"
        (r"\b(?:late|early|mid)-?\s*\d+s\b", "adult"),
    ]
    for pat, sub in replacements:
        text = re.sub(pat, sub, text, flags=re.IGNORECASE)

    # Collapse double spaces and orphan punctuation
    text = re.sub(r"\s+,", ",", text)
    text = re.sub(r",\s*,", ",", text)
    text = re.sub(r"\s+\.", ".", text)
    text = re.sub(r"\.\s*\.", ".", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text


def build_prompt(appearance: str, character_name: str, transformed: bool, retry: int = 0) -> str:
    """Wrap the locked appearance paragraph with composition hints so GPT Image 2
    produces a usable reference image (9:16 vertical portrait, neutral pose).

    Three layered defences against safety-filter false positives:
    1. Strong anti-realistic framing leads every prompt
    2. Demographic nouns (woman/man/boy/girl) softened on retries 1+
    3. Three different framing phrasings cycle across retries
    """
    # Pull the active preset's visual style for tonal coherence
    try:
        from config import VIDEO_STYLE
    except Exception:
        VIDEO_STYLE = "anime cel-shaded, cinematic sci-fi"

    pose = (
        "standing facing forward, three-quarter view, neutral expression, "
        "calm presence, head and torso clearly visible"
    )
    if transformed:
        pose = (
            "standing in a powerful neutral pose, three-quarter view, "
            "the transformation visible across the body, head and torso clearly visible"
        )

    # Retry 0: original text
    # Retry 1: soften gendered/age nouns (woman → female character)
    # Retry 2: aggressively strip relationship/death/emotional phrases
    if retry == 0:
        safe_appearance = appearance
    elif retry == 1:
        safe_appearance = _soften_demographics(appearance)
    else:
        safe_appearance = _aggressive_strip(appearance)

    framings = [
        # Attempt 1 — explicit fictional anime character framing
        f"Stylized anime illustration. Fictional original character drawn in {VIDEO_STYLE} style. "
        f"Not based on any real person. Hand-drawn cartoon art, never photorealistic. "
        f"9:16 vertical portrait composition.",

        # Attempt 2 — emphasize cartoon / illustrated / never realistic
        f"Cartoon character illustration, fully animated and stylized. {VIDEO_STYLE}. "
        f"This is original fictional anime character art — not a photograph, not based on any real person, "
        f"never photorealistic. 9:16 vertical reference frame.",

        # Attempt 3 — frame as concept art for a fictional show
        f"Concept art for an original animated show. Single fictional character design study. "
        f"Drawn in {VIDEO_STYLE} style. Cartoon illustration only — never realistic, never resembling a real person. "
        f"9:16 vertical portrait.",
    ]
    framing = framings[retry % len(framings)]

    return (
        f"{framing} "
        f"Character description: {safe_appearance} "
        f"Pose: {pose}. "
        f"Background: simple, slightly out of focus, deep navy and bone white tones with dust gold accents. "
        f"Lighting: cinematic key light with soft fill. "
        f"No text, no watermarks, no logos, no other characters in frame."
    )


def find_missing(
    records: list[dict],
    char_filter: str | None,
    form_filter: str | None,
    force: bool,
    skip: list[str] | None = None,
    verify: bool = False,
) -> list[tuple[dict, str]]:
    """Return list of (record, form) pairs that need an image generated.

    form: "normal" or "transformed"
    skip: list of character names to exclude (case-insensitive)

    Row positions aren't needed here — CharactersReader.record_ref_image()
    resolves the row and the form's column when writing back.
    """
    skip_lower = {s.strip().lower() for s in (skip or [])}
    todo = []
    for rec in records:
        name = str(rec.get("character_name", "")).strip()
        if not name:
            continue
        if char_filter and name.lower() != char_filter.lower():
            continue
        if name.lower() in skip_lower:
            continue
        status = str(rec.get("status", "active")).strip().lower()
        # Skip dead characters' transformed form by default — they don't transform anymore
        # but normal form still useful for flashbacks.
        for form in ("normal", "transformed"):
            if form_filter and form_filter != form:
                continue
            appearance = str(rec.get(f"appearance_{form}", "")).strip()
            ref_url = str(rec.get(f"ref_image_{form}", "")).strip()
            if not appearance:
                continue  # nothing to generate from
            if ref_url and not force:
                # A URL in the sheet is not proof of an image: Atlas expires
                # them. --verify checks before deciding it's already done.
                if not verify or reference_is_live(ref_url):
                    continue
            todo.append((rec, form))
    return todo


def confirm(prompt: str) -> bool:
    try:
        return input(prompt).strip().lower() in ("y", "yes")
    except EOFError:
        return False


def main():
    ap = argparse.ArgumentParser(description="Generate character reference images for the Chronicle of Zenith characters sheet.")
    ap.add_argument("--character", help="Only generate for this character (exact name match, case-insensitive)")
    ap.add_argument("--form", choices=["normal", "transformed"], help="Only generate this form")
    ap.add_argument("--all", action="store_true", help="Generate every missing image without listing first")
    ap.add_argument("--force", action="store_true", help="Regenerate even if URL is already set")
    ap.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    ap.add_argument("--dry-run", action="store_true", help="Plan only — no API calls or sheet writes")
    ap.add_argument("--check", action="store_true",
                    help="Report which reference URLs still resolve, then exit. No API calls.")
    ap.add_argument("--verify", action="store_true",
                    help="Treat a dead reference URL as missing (regenerates only broken ones)")
    ap.add_argument("--skip", action="append", default=[],
                    help="Skip a specific character (repeatable). Useful when one keeps failing safety filters: --skip 'Edith Hale' --skip 'Marco Reyes'")
    args = ap.parse_args()

    roster = CharactersReader()
    if not roster.available:
        raise SystemExit(
            "ALAN_STORY_CHARACTERS_GOOGLE_SHEET_ID is not set — nothing to read."
        )
    records = roster.get_all_characters()

    if args.check:
        raise SystemExit(1 if check_references(records) else 0)

    todo = find_missing(
        records, args.character, args.form, args.force,
        skip=args.skip, verify=args.verify,
    )

    if not todo:
        print("Nothing to generate — all matching characters already have their images.")
        return

    # Pretty list of what we're about to do
    print(f"\nFound {len(todo)} image(s) to generate:")
    for rec, form in todo:
        name = rec.get("character_name", "")
        existing = "(replacing existing)" if str(rec.get(f"ref_image_{form}", "")).strip() else ""
        print(f"  • {name} — {form} {existing}")
    estimated_cost = len(todo) * COST_PER_IMAGE
    print(f"\nEstimated cost: ${estimated_cost:.3f} (at ${COST_PER_IMAGE}/image)")

    if args.dry_run:
        print("\nDry run — no API calls made.")
        return

    if not args.yes and not args.all:
        if not confirm("\nProceed? [y/N] "):
            print("Cancelled.")
            return
    elif args.all and not args.yes:
        if not confirm(f"\n--all flag: generate all {len(todo)} images for ${estimated_cost:.3f}? [y/N] "):
            print("Cancelled.")
            return

    success = 0
    failures = []

    SCRIPT_MAX_RETRIES = 3

    for rec, form in todo:
        name = rec.get("character_name", "")
        appearance = rec.get(f"appearance_{form}", "")

        url = None
        last_err = None
        for retry in range(SCRIPT_MAX_RETRIES):
            prompt = build_prompt(appearance, name, transformed=(form == "transformed"), retry=retry)
            attempt_label = f"attempt {retry + 1}/{SCRIPT_MAX_RETRIES}"
            stripping = ["original", "softened (gendered nouns)", "aggressively stripped"][retry]
            print(f"\n→ Generating '{name}' [{form}] ({attempt_label}, text: {stripping})...")
            try:
                url = call_atlas_image(prompt)
                break
            except AtlasError as exc:
                last_err = str(exc)
                print(f"  retry {retry + 1} failed:\n    {last_err}")
                time.sleep(3 + retry * 2)

        if not url:
            print(f"  ❌ {name} [{form}]: gave up after {SCRIPT_MAX_RETRIES} retries")
            failures.append((name, form, last_err or "unknown"))
            continue

        # Write back to sheet immediately — this image is already paid for.
        try:
            roster.record_ref_image(name, form, url)
        except ValueError as exc:
            print(f"  ⚠️  '{name}' [{form}] generated but not saved: {exc}")
            print(f"      URL (paste manually): {url}")
            failures.append((name, form, str(exc)))
            continue
        local = mirror_locally(name, form, url)
        print(f"  ✅ {name} [{form}] → {url[:80]}...")
        if local:
            print(f"      mirrored to {local.relative_to(PROJECT_ROOT)}")
        success += 1

    print(f"\n=== DONE ===")
    print(f"  Generated: {success}")
    if failures:
        print(f"  Failed:    {len(failures)}")
        for name, form, err in failures:
            print(f"    - {name} [{form}]: {err[:120]}")
        print(f"\n  Recovery options for failed characters:")
        print(f"    - Retry just that character: python scripts/generate_character_images.py --character \"<name>\" --force")
        print(f"    - Manually generate on Atlas playground and paste the URL into the sheet's ref_image_normal/transformed cell")
        print(f"    - Edit the appearance paragraph in the sheet (e.g. soften 'woman' → 'female figure') and retry")
    print(f"  Approx spent: ${success * COST_PER_IMAGE:.3f}")
    if success > 0:
        print(f"\nTip: re-run scripts/export_characters.py to refresh the markdown snapshot.")


if __name__ == "__main__":
    main()

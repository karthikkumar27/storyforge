"""Characters sheet reader for preset-7 (Chronicle of Zenith).

Reads the characters Google Sheet pointed at by ALAN_STORY_CHARACTERS_GOOGLE_SHEET_ID.
Provides locked character paragraphs and arc-relevance filtering so the brief
generator can inject the right cast for each episode.

Graceful no-op when the sheet is empty or unconfigured — the canon SKILL.md
still covers character lore even without the sheet populated.

Expected columns (from the characters sheet schema):
    character_name | alias | role | relation_to_main |
    appearance_normal | appearance_transformed |
    ref_image_normal | ref_image_transformed |
    backstory | first_episode | status

Optional columns (if present, used for richer filtering):
    arcs_active           — comma-separated list of arc numbers (e.g. "1,5,8")
    last_episode_appeared — auto-updated by pipeline
"""

import json
import os

import gspread


class CharactersReader:
    def __init__(self, sheet_id_env: str = "ALAN_STORY_CHARACTERS_GOOGLE_SHEET_ID"):
        if sheet_id_env not in os.environ:
            self.sheet = None
            self.available = False
            print(f"[Characters] {sheet_id_env} not set; reader is no-op", flush=True)
            return
        creds_dict = json.loads(os.environ["GOOGLE_SHEETS_CREDENTIALS"])
        sheet_id = os.environ[sheet_id_env]
        self.sheet = gspread.service_account_from_dict(creds_dict).open_by_key(sheet_id).sheet1
        self.available = True

    def get_all_characters(self) -> list[dict]:
        """Return every character row from the sheet, excluding empty rows.

        Uses numericise_ignore=['all'] so comma-separated columns like
        arcs_active stay as strings — Sheets otherwise strips commas and
        returns them as giant integers (e.g. "1,2,3,4,5" → 12345).
        """
        if not self.available:
            return []
        records = self.sheet.get_all_records(numericise_ignore=["all"])
        return [r for r in records if str(r.get("character_name", "")).strip()]

    def get_active_for_arc(self, arc_number: int) -> list[dict]:
        """Return characters whose arcs_active list includes this arc, OR
        whose first_episode falls in or before this arc and status is 'active'.

        If a character row has no arcs_active value, falls back to
        first_episode + status check. This way you can populate either column
        and the reader still does the right thing.
        """
        all_chars = self.get_all_characters()
        relevant = []
        for c in all_chars:
            arcs_raw = str(c.get("arcs_active", "")).strip()
            if arcs_raw:
                # Explicit arcs_active list — use it directly
                arcs = [int(a.strip()) for a in arcs_raw.split(",") if a.strip().isdigit()]
                if arc_number in arcs:
                    relevant.append(c)
                continue
            # Fallback: use first_episode + status
            first_ep_raw = str(c.get("first_episode", "")).strip()
            try:
                first_ep = int(first_ep_raw) if first_ep_raw else 1
            except ValueError:
                first_ep = 1
            first_arc = ((first_ep - 1) // 20) + 1
            status = str(c.get("status", "active")).strip().lower()
            if first_arc <= arc_number and status in ("active", ""):
                relevant.append(c)
        return relevant

    def get_main_character(self) -> dict | None:
        """Return the row marked role='main' (typically Alan/Zenith)."""
        for c in self.get_all_characters():
            if str(c.get("role", "")).strip().lower() == "main":
                return c
        return None

    def get_main_ref_image_for_form(self, character_form: str) -> str | None:
        """Return the locked reference image URL for the main character matching
        the requested form ("normal" | "transformed" | "both").

        Selection logic:
        - "transformed" or "both" → ref_image_transformed if set, else ref_image_normal
        - "normal" or anything else → ref_image_normal if set, else ref_image_transformed
        - None if no URLs are set (signals to caller to fall back to GPT Image 2 generation)
        """
        main = self.get_main_character()
        if not main:
            return None
        normal = str(main.get("ref_image_normal", "")).strip()
        transformed = str(main.get("ref_image_transformed", "")).strip()

        form = (character_form or "").strip().lower()
        if form in ("transformed", "both"):
            return transformed or normal or None
        return normal or transformed or None


def format_characters_context(arc_number: int, episode_number: int) -> str:
    """Build a prompt-ready text block listing the characters who should be
    available for this episode, with their locked appearance paragraphs.

    Returned block is empty when the sheet is empty/unavailable, so callers
    can always concatenate without checking.
    """
    reader = CharactersReader()
    if not reader.available:
        return ""
    active = reader.get_active_for_arc(arc_number)
    if not active:
        return ""

    lines = ["=== CHARACTER ROSTER (this episode's available cast) ==="]
    for c in active:
        name = c.get("character_name", "").strip()
        alias = c.get("alias", "").strip()
        role = c.get("role", "").strip()
        relation = c.get("relation_to_main", "").strip()
        backstory = c.get("backstory", "").strip()
        appearance = c.get("appearance_normal", "").strip()
        appearance_t = c.get("appearance_transformed", "").strip()

        header = f"\n• {name}"
        if alias:
            header += f" (aka {alias})"
        if role:
            header += f" — {role}"
        if relation and relation != "self":
            header += f", {relation} to main"
        lines.append(header)

        if backstory:
            lines.append(f"  Backstory: {backstory}")
        if appearance:
            lines.append(f"  LOCKED APPEARANCE: {appearance}")
        if appearance_t:
            lines.append(f"  LOCKED APPEARANCE (transformed): {appearance_t}")

    lines.append("\nWhen any of these characters appears in your script's shots, paste their LOCKED APPEARANCE description into the shot prompt verbatim. Do not paraphrase or invent new details.")
    lines.append("Do not introduce characters that are NOT in this list — if you need a new character, mark them as a generic unnamed presence ('a tall man with white hair').")
    return "\n".join(lines)

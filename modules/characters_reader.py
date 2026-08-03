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

import os

from modules.sheet_access import SheetSession


class CharactersReader:
    def __init__(
        self,
        session: SheetSession | None = None,
        sheet_id_env: str = "ALAN_STORY_CHARACTERS_GOOGLE_SHEET_ID",
    ):
        """Read the roster through a SheetSession.

        Pass the Run's session so the sheet is read once per Run rather than
        once per reader — the brief generator, the script generator and the
        orchestrator each construct one. Omitting it creates a single-use
        session, which is safe but wasteful; never share one across Runs.
        See docs/adr/0001-run-scoped-ledger-cache.md.
        """
        self.available = sheet_id_env in os.environ
        if not self.available:
            self._tab = None
            print(f"[Characters] {sheet_id_env} not set; reader is no-op", flush=True)
            return
        # numericise=False keeps arcs_active as a string — Sheets otherwise
        # strips the commas and returns "1,2,3,4,5" as the integer 12345.
        self._tab = (session or SheetSession()).tab(sheet_id_env, numericise=False)

    def get_all_characters(self) -> list[dict]:
        """Return every character row from the sheet, excluding empty rows."""
        if not self.available:
            return []
        return [
            r for r in self._tab.records
            if str(r.get("character_name", "")).strip()
        ]

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

    def record_ref_image(self, character_name: str, form: str, url: str) -> None:
        """Write a generated Reference Image URL back to a character's row.

        Lands immediately rather than buffering: each image costs money and
        ~90 seconds to produce, so a crash part-way through a bulk run must not
        throw away the ones already paid for.

        Raises ValueError if the roster has no column for that form, or if the
        character isn't in the sheet.
        """
        if not self.available:
            raise ValueError("characters sheet is not configured")
        column = "ref_image_transformed" if form == "transformed" else "ref_image_normal"
        for i, row in enumerate(self._tab.records, start=2):
            if str(row.get("character_name", "")).strip() == character_name.strip():
                self._tab.stage(i, {column: url})
                self._tab.flush()
                return
        raise ValueError(f"No character named {character_name!r} in the roster")

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

    def get_main_appearance_for_form(self, character_form: str) -> str | None:
        """Return the locked appearance paragraph for the main character matching
        the requested form ("normal" | "transformed" | "both").

        Deliberately mirrors get_main_ref_image_for_form's selection logic. The
        episode's character_form already chooses the reference image; it must
        choose the matching words, or the prompt describes Alan while the image
        shows Zenith.

        Selection logic:
        - "transformed" or "both" → appearance_transformed if set, else appearance_normal
        - "normal" or anything else → appearance_normal if set, else appearance_transformed
        - None if neither is set (signals the caller to inject no appearance)
        """
        main = self.get_main_character()
        if not main:
            return None
        normal = str(main.get("appearance_normal", "")).strip()
        transformed = str(main.get("appearance_transformed", "")).strip()

        form = (character_form or "").strip().lower()
        if form in ("transformed", "both"):
            return transformed or normal or None
        return normal or transformed or None


def format_characters_context(
    arc_number: int,
    episode_number: int,
    session: SheetSession | None = None,
) -> str:
    """Build a prompt-ready text block listing the characters who should be
    available for this episode, with their locked appearance paragraphs.

    Returned block is empty when the sheet is empty/unavailable, so callers
    can always concatenate without checking. Pass the Run's session so repeated
    calls within one Run share a single read.
    """
    reader = CharactersReader(session=session)
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

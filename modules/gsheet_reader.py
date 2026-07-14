import os
import json
import gspread


class GSheetReader:
    def __init__(self, sheet_id_env: str = "GOOGLE_SHEET_ID"):
        """Construct a reader pointed at the sheet whose ID is in the named env var.

        Defaults to GOOGLE_SHEET_ID (the main sheet used by every preset except
        preset-7). For preset-7 (Zenith), pass sheet_id_env="ALAN_STORY_GOOGLE_SHEET_ID"
        to point this reader at the dedicated Zenith episodes sheet.
        """
        creds_dict = json.loads(os.environ["GOOGLE_SHEETS_CREDENTIALS"])
        sheet_id = os.environ[sheet_id_env]
        self.sheet_id_env = sheet_id_env
        self.sheet = gspread.service_account_from_dict(creds_dict).open_by_key(sheet_id).sheet1

    def get_pending_row(self) -> dict | None:
        records = self.sheet.get_all_records()
        for i, row in enumerate(records, start=2):
            if row.get("status") == "pending":
                return {
                    "row_index": i,
                    "title": row.get("title", ""),
                    "story_brief": row["story_brief"],
                    "genre": row.get("genre", "blend"),
                    "duration_sec": int(row.get("duration_sec") or 75),
                    "series_id": row.get("series_id", ""),
                    "part_number": row.get("part_number", ""),
                    "story_mode": row.get("story_mode", "standalone"),
                    "arc_number": row.get("arc_number", ""),
                    "episode_number": row.get("episode_number", ""),
                    "character_form": row.get("character_form", ""),
                    "ref_image_url": row.get("ref_image_url", ""),
                }
        return None

    def ensure_columns(self, *column_names: str) -> None:
        """Ensure the given columns exist in the header row. Append any missing.
        Idempotent — safe to call on every pipeline run."""
        headers = self.sheet.row_values(1)
        missing = [c for c in column_names if c not in headers]
        if not missing:
            return
        new_headers = headers + missing
        self.sheet.update("A1", [new_headers])
        print(f"[GSheet] Added missing columns: {missing}", flush=True)

    def update_arc_metadata(self, row_index: int, arc_number: int, episode_number: int) -> None:
        """Write arc_number and episode_number to a row. Auto-adds columns if missing."""
        self.ensure_columns("arc_number", "episode_number")
        self.sheet.update_cell(row_index, self._col("arc_number"), arc_number)
        self.sheet.update_cell(row_index, self._col("episode_number"), episode_number)

    def get_next_episode_number(self, preset_genres: list[str]) -> int:
        """For a continuous-series preset (e.g. preset-7), the next episode_number
        is the max existing episode_number for this preset's genres + 1.
        Returns 1 if no episodes exist yet."""
        records = self.sheet.get_all_records()
        max_ep = 0
        for row in records:
            if row.get("genre", "") not in preset_genres:
                continue
            ep_raw = row.get("episode_number", "")
            try:
                ep = int(ep_raw) if ep_raw not in ("", None) else 0
            except (ValueError, TypeError):
                ep = 0
            if ep > max_ep:
                max_ep = ep
        return max_ep + 1

    def update_status(self, row_index: int, status: str) -> None:
        self.sheet.update_cell(row_index, self._col("status"), status)

    def update_script(self, row_index: int, script_text: str) -> None:
        self.sheet.update_cell(row_index, self._col("script_text"), script_text)

    def update_ref_image(self, row_index: int, ref_image_url: str) -> None:
        self.sheet.update_cell(row_index, self._col("ref_image_url"), ref_image_url)

    def update_done(self, row_index: int, youtube_url: str) -> None:
        self.sheet.update_cell(row_index, self._col("status"), "done")
        self.sheet.update_cell(row_index, self._col("youtube_url"), youtube_url)

    def update_error(self, row_index: int, error_msg: str) -> None:
        self.sheet.update_cell(row_index, self._col("status"), "error")
        self.sheet.update_cell(row_index, self._col("error_msg"), error_msg)

    def append_pending_row(self, brief_data: dict) -> None:
        """Append a new row with generated brief, setting status=pending."""
        self.ensure_columns("arc_number", "episode_number", "character_form")
        headers = self.sheet.row_values(1)
        row = [""] * len(headers)
        field_map = {
            "title_hint": "title",
            "story_brief": "story_brief",
            "genre": "genre",
            "series_id": "series_id",
            "part_number": "part_number",
            "story_mode": "story_mode",
            "arc_number": "arc_number",
            "episode_number": "episode_number",
            "character_form": "character_form",
        }
        for src_key, col_name in field_map.items():
            if src_key in brief_data and col_name in headers:
                row[headers.index(col_name)] = brief_data[src_key]
        if "status" in headers:
            row[headers.index("status")] = "pending"
        if "duration_sec" in headers:
            row[headers.index("duration_sec")] = 75
        self.sheet.append_row(row)

    def get_series_parts(self, series_id: str) -> list[dict]:
        """Get all completed parts of a series, ordered by part number."""
        records = self.sheet.get_all_records()
        parts = []
        for row in records:
            if row.get("series_id") == series_id and row.get("status") == "done":
                parts.append(row)
        parts.sort(key=lambda r: int(r.get("part_number") or 0))
        return parts

    def get_latest_incomplete_series(self) -> str | None:
        """Find the most recent series that has completed parts but isn't finished yet.
        Only considers series whose genre matches the current preset's genres."""
        from config import SERIES_PARTS, GENRES
        records = self.sheet.get_all_records()
        series_info = {}  # sid -> {"count": int, "genre": str, "last_row": int}
        for i, row in enumerate(records):
            sid = row.get("series_id")
            if sid and row.get("status") == "done":
                if sid not in series_info:
                    series_info[sid] = {"count": 0, "genre": row.get("genre", ""), "last_row": i}
                series_info[sid]["count"] += 1
                series_info[sid]["last_row"] = i
        # Filter to current preset's genres, then pick the most recent
        candidates = [
            (sid, info) for sid, info in series_info.items()
            if info["count"] < SERIES_PARTS and info["genre"] in GENRES
        ]
        if not candidates:
            return None
        # Return the series with the highest last_row (most recent in sheet)
        candidates.sort(key=lambda x: x[1]["last_row"], reverse=True)
        return candidates[0][0]

    def get_past_stories(self, limit: int = 20) -> list[dict]:
        """Get recent completed stories to avoid repetition.
        Only returns stories whose genre matches the current preset."""
        from config import GENRES
        records = self.sheet.get_all_records()
        stories = []
        for row in records:
            if row.get("status") == "done" and row.get("story_brief") and row.get("genre", "") in GENRES:
                stories.append({
                    "title": row.get("title", ""),
                    "story_brief": row.get("story_brief", ""),
                    "genre": row.get("genre", ""),
                })
        return stories[-limit:]

    def _col(self, name: str) -> int:
        headers = self.sheet.row_values(1)
        if name not in headers:
            raise ValueError(f"Column '{name}' not found in sheet headers: {headers}")
        return headers.index(name) + 1


def get_episode_reader() -> GSheetReader:
    """Return the GSheetReader pointed at the right sheet for the active preset.

    - preset-7 (Zenith Chronicles): the dedicated ALAN_STORY_GOOGLE_SHEET_ID sheet
    - all other presets: the main GOOGLE_SHEET_ID sheet

    This isolates Zenith's 200-episode timeline from the other presets' simpler
    rosters, so schemas can evolve independently and continuity tracking columns
    (outfits, callbacks, time-of-day, etc.) only live where they're needed.
    """
    from config import ACTIVE_PRESET
    if ACTIVE_PRESET == "preset-7":
        env_var = "ALAN_STORY_GOOGLE_SHEET_ID"
        if env_var in os.environ:
            print(f"[GSheet] Using Alan Story sheet (preset-7)", flush=True)
            return GSheetReader(sheet_id_env=env_var)
        print(f"[GSheet] WARNING: {env_var} not set; falling back to GOOGLE_SHEET_ID", flush=True)
    return GSheetReader(sheet_id_env="GOOGLE_SHEET_ID")

import os
import json
import gspread


class GSheetReader:
    def __init__(self):
        creds_dict = json.loads(os.environ["GOOGLE_SHEETS_CREDENTIALS"])
        sheet_id = os.environ["GOOGLE_SHEET_ID"]
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
                    "duration_sec": int(row.get("duration_sec", 75)),
                }
        return None

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
        headers = self.sheet.row_values(1)
        row = [""] * len(headers)
        field_map = {
            "title_hint": "title",
            "story_brief": "story_brief",
            "genre": "genre",
            "series_id": "series_id",
            "part_number": "part_number",
            "story_mode": "story_mode",
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
        parts.sort(key=lambda r: int(r.get("part_number", 0)))
        return parts

    def get_latest_incomplete_series(self) -> str | None:
        """Find a series that has completed parts but isn't finished yet."""
        from config import SERIES_PARTS
        records = self.sheet.get_all_records()
        series_counts = {}
        for row in records:
            sid = row.get("series_id")
            if sid and row.get("status") == "done":
                series_counts[sid] = series_counts.get(sid, 0) + 1
        for sid, count in series_counts.items():
            if count < SERIES_PARTS:
                return sid
        return None

    def get_past_stories(self, limit: int = 20) -> list[dict]:
        """Get recent completed stories to avoid repetition."""
        records = self.sheet.get_all_records()
        stories = []
        for row in records:
            if row.get("status") == "done" and row.get("story_brief"):
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

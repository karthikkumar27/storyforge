import os
import json
import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class GSheetReader:
    def __init__(self):
        creds_json = os.environ["GOOGLE_SHEETS_CREDENTIALS"]
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        gc = gspread.authorize(creds)
        sheet_id = os.environ["GOOGLE_SHEET_ID"]
        self.sheet = gc.open_by_key(sheet_id).sheet1

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

    def update_done(self, row_index: int, youtube_url: str) -> None:
        self.sheet.update_cell(row_index, self._col("status"), "done")
        self.sheet.update_cell(row_index, self._col("youtube_url"), youtube_url)

    def update_error(self, row_index: int, error_msg: str) -> None:
        self.sheet.update_cell(row_index, self._col("status"), "error")
        self.sheet.update_cell(row_index, self._col("error_msg"), error_msg)

    def _col(self, name: str) -> int:
        headers = self.sheet.row_values(1)
        return headers.index(name) + 1

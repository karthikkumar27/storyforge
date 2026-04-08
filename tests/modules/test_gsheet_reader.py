# tests/modules/test_gsheet_reader.py
import json
import pytest
from unittest.mock import MagicMock, patch


@patch("modules.gsheet_reader.gspread")
def test_get_pending_row_returns_first_pending(mock_gspread, monkeypatch):
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS", json.dumps({"type": "service_account"}))
    monkeypatch.setenv("GOOGLE_SHEET_ID", "sheet123")

    mock_sheet = MagicMock()
    mock_sheet.get_all_records.return_value = [
        {"title": "Test", "story_brief": "A spaceship drifts", "genre": "sci-fi",
         "duration_sec": 75, "status": "pending"},
    ]
    mock_gspread.service_account_from_dict.return_value.open_by_key.return_value.sheet1 = mock_sheet

    from modules.gsheet_reader import GSheetReader
    reader = GSheetReader()
    row = reader.get_pending_row()

    assert row["story_brief"] == "A spaceship drifts"
    assert row["genre"] == "sci-fi"
    assert row["row_index"] == 2


@patch("modules.gsheet_reader.gspread")
def test_get_pending_row_skips_done_rows(mock_gspread, monkeypatch):
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS", json.dumps({"type": "service_account"}))
    monkeypatch.setenv("GOOGLE_SHEET_ID", "sheet123")

    mock_sheet = MagicMock()
    mock_sheet.get_all_records.return_value = [
        {"title": "Old", "story_brief": "Old story", "genre": "blend",
         "duration_sec": 75, "status": "done"},
        {"title": "New", "story_brief": "New idea", "genre": "horror",
         "duration_sec": 75, "status": "pending"},
    ]
    mock_gspread.service_account_from_dict.return_value.open_by_key.return_value.sheet1 = mock_sheet

    from modules.gsheet_reader import GSheetReader
    reader = GSheetReader()
    row = reader.get_pending_row()

    assert row["story_brief"] == "New idea"
    assert row["row_index"] == 3


@patch("modules.gsheet_reader.gspread")
def test_get_pending_row_returns_none_when_all_done(mock_gspread, monkeypatch):
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS", json.dumps({"type": "service_account"}))
    monkeypatch.setenv("GOOGLE_SHEET_ID", "sheet123")

    mock_sheet = MagicMock()
    mock_sheet.get_all_records.return_value = [
        {"title": "Done", "story_brief": "Old", "genre": "sci-fi",
         "duration_sec": 75, "status": "done"},
    ]
    mock_gspread.service_account_from_dict.return_value.open_by_key.return_value.sheet1 = mock_sheet

    from modules.gsheet_reader import GSheetReader
    reader = GSheetReader()
    assert reader.get_pending_row() is None


@patch("modules.gsheet_reader.gspread")
def test_update_status_writes_correct_cell(mock_gspread, monkeypatch):
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS", json.dumps({"type": "service_account"}))
    monkeypatch.setenv("GOOGLE_SHEET_ID", "sheet123")

    mock_sheet = MagicMock()
    mock_sheet.row_values.return_value = [
        "title", "story_brief", "script_text", "genre", "duration_sec",
        "status", "youtube_url", "error_msg"
    ]
    mock_gspread.service_account_from_dict.return_value.open_by_key.return_value.sheet1 = mock_sheet

    from modules.gsheet_reader import GSheetReader
    reader = GSheetReader()
    reader.update_status(2, "generating")

    mock_sheet.update_cell.assert_called_with(2, 6, "generating")  # status is col 6


@patch("modules.gsheet_reader.gspread")
def test_append_pending_row_writes_correct_fields(mock_gspread, monkeypatch):
    import json
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS", json.dumps({"type": "service_account"}))
    monkeypatch.setenv("GOOGLE_SHEET_ID", "sheet123")

    mock_sheet = MagicMock()
    mock_sheet.row_values.return_value = [
        "title", "story_brief", "script_text", "genre", "duration_sec",
        "status", "youtube_url", "error_msg"
    ]
    mock_gspread.service_account_from_dict.return_value.open_by_key.return_value.sheet1 = mock_sheet

    from modules.gsheet_reader import GSheetReader
    reader = GSheetReader()
    reader.append_pending_row({
        "story_brief": "A ghost in the machine",
        "genre": "sci-fi",
        "title_hint": "Static",
    })

    appended = mock_sheet.append_row.call_args[0][0]
    assert appended[1] == "A ghost in the machine"   # story_brief col
    assert appended[3] == "sci-fi"                    # genre col
    assert appended[5] == "pending"                   # status col
    assert appended[4] == 75                          # duration_sec col

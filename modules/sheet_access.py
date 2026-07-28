"""Cached, batched access to the Google Sheets behind the Episode Ledger.

Three layers, smallest first:

  RawSheet      a four-method protocol: read everything, append a row, write
                some cells, replace the header row. Two adapters satisfy it —
                GspreadSheet (production) and InMemorySheet (tests).

  SheetTab      wraps a RawSheet with the behaviour every caller wanted and
                nobody should reimplement: read once and remember, resolve
                column names to indices without another round trip, and buffer
                writes until something asks for them to land.

  SheetSession  one Run's view of every tab it touches. Created per pipeline
                run and discarded afterwards.

The session boundary is deliberate and load-bearing — see
docs/adr/0001-run-scoped-ledger-cache.md. Do not memoise any of this at module
level: Flask is long-lived, and the sheets are the runtime source of truth that
an operator edits between Runs.
"""

from __future__ import annotations

import json
import os
from typing import Callable, Protocol


class RawSheet(Protocol):
    """The minimum a storage backend must provide. Deliberately tiny — every
    other convenience is built once, in SheetTab, on top of these four."""

    def read_all(self) -> tuple[list[str], list[dict]]:
        """Return (header row, records) where each record maps header -> value."""
        ...

    def append(self, values: list) -> None:
        """Append one row, positionally aligned to the current header row."""
        ...

    def write_cells(self, updates: list[tuple[int, int, object]]) -> None:
        """Apply (row_index, column_index, value) triples. Both indices 1-based."""
        ...

    def set_headers(self, headers: list[str]) -> None:
        """Replace the header row."""
        ...


class GspreadSheet:
    """RawSheet backed by a real Google Sheet.

    numericise=False keeps comma-separated columns as strings. The characters
    sheet needs it: Sheets otherwise reads arcs_active "1,2,3,4,5" as the
    integer 12345.
    """

    def __init__(self, worksheet, numericise: bool = True):
        self._ws = worksheet
        self._numericise = numericise

    def read_all(self) -> tuple[list[str], list[dict]]:
        kwargs = {} if self._numericise else {"numericise_ignore": ["all"]}
        records = self._ws.get_all_records(**kwargs)
        headers = self._ws.row_values(1)
        return headers, records

    def append(self, values: list) -> None:
        self._ws.append_row(values)

    def write_cells(self, updates: list[tuple[int, int, object]]) -> None:
        if not updates:
            return
        from gspread.utils import rowcol_to_a1
        self._ws.batch_update([
            {"range": rowcol_to_a1(row, col), "values": [[value]]}
            for row, col, value in updates
        ])

    def set_headers(self, headers: list[str]) -> None:
        self._ws.update("A1", [headers])


class InMemorySheet:
    """RawSheet backed by a list of dicts. The test adapter.

    Ships alongside GspreadSheet on purpose: if SheetTab starts needing a fifth
    operation, this fails immediately rather than quietly passing on a mock that
    answers every question.
    """

    def __init__(self, rows: list[dict] | None = None, headers: list[str] | None = None):
        rows = rows or []
        if headers is None:
            headers = []
            for row in rows:
                for key in row:
                    if key not in headers:
                        headers.append(key)
        self.headers = list(headers)
        self.rows = [[row.get(h, "") for h in self.headers] for row in rows]

    def read_all(self) -> tuple[list[str], list[dict]]:
        records = [dict(zip(self.headers, row)) for row in self.rows]
        return list(self.headers), records

    def append(self, values: list) -> None:
        padded = list(values) + [""] * (len(self.headers) - len(values))
        self.rows.append(padded[: len(self.headers)])

    def write_cells(self, updates: list[tuple[int, int, object]]) -> None:
        for row_index, col_index, value in updates:
            # row_index is 1-based and includes the header row
            target = self.rows[row_index - 2]
            while len(target) < col_index:
                target.append("")
            target[col_index - 1] = value

    def set_headers(self, headers: list[str]) -> None:
        added = len(headers) - len(self.headers)
        self.headers = list(headers)
        if added > 0:
            for row in self.rows:
                row.extend([""] * added)


class SheetTab:
    """One tab, read once per Run and written in batches.

    Reads are served from a snapshot taken on first access. Writes accumulate in
    a buffer and land when flush() is called — or immediately, when the caller
    marks them urgent. Callers that need to see their own writes reflected in
    subsequent reads should call refresh().
    """

    def __init__(self, raw: RawSheet):
        self._raw = raw
        self._headers: list[str] | None = None
        self._records: list[dict] | None = None
        self._pending: dict[tuple[int, int], object] = {}

    # -- reads ----------------------------------------------------------------

    def _load(self) -> None:
        if self._records is None:
            self._headers, self._records = self._raw.read_all()

    @property
    def headers(self) -> list[str]:
        self._load()
        return self._headers or []

    @property
    def records(self) -> list[dict]:
        """Every data row, in sheet order. Index 0 is sheet row 2."""
        self._load()
        return self._records or []

    def refresh(self) -> None:
        """Drop the snapshot so the next read re-fetches. Flushes first, so the
        re-read includes anything still buffered."""
        self.flush()
        self._headers = None
        self._records = None

    def column(self, name: str) -> int:
        """1-based column index for a header name. Resolved from the cached
        header row — no round trip, unlike the per-write lookup this replaces."""
        headers = self.headers
        if name not in headers:
            raise ValueError(f"Column {name!r} not found in sheet headers: {headers}")
        return headers.index(name) + 1

    # -- writes ---------------------------------------------------------------

    def ensure_columns(self, *names: str) -> None:
        """Append any missing columns to the header row. Idempotent."""
        missing = [n for n in names if n not in self.headers]
        if not missing:
            return
        new_headers = self.headers + missing
        self._raw.set_headers(new_headers)
        self._headers = new_headers
        print(f"[Sheet] Added missing columns: {missing}", flush=True)

    def stage(self, row_index: int, values: dict[str, object]) -> None:
        """Buffer cell writes for a row. Nothing hits the network until flush()."""
        for name, value in values.items():
            self._pending[(row_index, self.column(name))] = value
            # Keep the snapshot consistent with what we've staged, so a caller
            # that reads back a row it just wrote sees its own write.
            if self._records is not None and 0 <= row_index - 2 < len(self._records):
                self._records[row_index - 2][name] = value

    def flush(self) -> None:
        """Send every buffered write as one batch."""
        if not self._pending:
            return
        updates = [(row, col, value) for (row, col), value in self._pending.items()]
        self._pending.clear()
        self._raw.write_cells(updates)

    def append_row(self, values: dict[str, object]) -> None:
        """Append a row from a {header: value} mapping. Flushes buffered writes
        first so ordering is preserved."""
        self.flush()
        row = [values.get(h, "") for h in self.headers]
        self._raw.append(row)
        if self._records is not None:
            self._records.append({h: values.get(h, "") for h in self.headers})


class SheetSession:
    """One Run's view of the sheets. Construct per run; never cache globally."""

    def __init__(self, opener: Callable[[str, bool], RawSheet] | None = None):
        self._opener = opener or _open_gspread_tab
        self._tabs: dict[tuple[str, bool], SheetTab] = {}

    def tab(self, sheet_id_env: str, numericise: bool = True) -> SheetTab:
        """Return the tab for the sheet whose id lives in the named env var.
        The same tab is returned for the lifetime of this session."""
        key = (sheet_id_env, numericise)
        if key not in self._tabs:
            self._tabs[key] = SheetTab(self._opener(sheet_id_env, numericise))
        return self._tabs[key]

    def flush(self) -> None:
        for tab in self._tabs.values():
            tab.flush()


def _open_gspread_tab(sheet_id_env: str, numericise: bool) -> RawSheet:
    import gspread
    creds = json.loads(os.environ["GOOGLE_SHEETS_CREDENTIALS"])
    sheet_id = os.environ[sheet_id_env]
    worksheet = gspread.service_account_from_dict(creds).open_by_key(sheet_id).sheet1
    return GspreadSheet(worksheet, numericise=numericise)

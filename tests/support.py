"""Shared test doubles."""

from modules.sheet_access import InMemorySheet


class CountingSheet:
    """InMemorySheet that records how often it was asked to do network-ish work.

    Round-trip counts are part of the ledger's interface — "reads the sheet once
    per Run" is a promise callers rely on — so they're asserted, not assumed.
    """

    def __init__(self, rows=None, headers=None):
        self._inner = InMemorySheet(rows, headers)
        self.reads = 0
        self.write_batches = 0
        self.cells_written = 0
        self.appends = 0

    @property
    def round_trips(self) -> int:
        return self.reads + self.write_batches + self.appends

    def read_all(self):
        self.reads += 1
        return self._inner.read_all()

    def append(self, values):
        self.appends += 1
        return self._inner.append(values)

    def write_cells(self, updates):
        self.write_batches += 1
        self.cells_written += len(updates)
        return self._inner.write_cells(updates)

    def set_headers(self, headers):
        return self._inner.set_headers(headers)

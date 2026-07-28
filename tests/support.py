"""Shared test doubles."""

from modules.sheet_access import InMemorySheet


class StubLlm:
    """Stands in for modules.llm.Llm. Records prompts, replays scripted replies."""

    def __init__(self, results=None, errors=None):
        self.results = list(results or [])
        self.errors = list(errors or [])   # one entry per call: exception or None
        self.calls = []

    def ask_json(self, system, user, *, max_tokens, label="Claude"):
        self.calls.append({
            "system": system,
            "user": user,
            "max_tokens": max_tokens,
            "label": label,
        })
        if self.errors:
            error = self.errors.pop(0)
            if error is not None:
                raise error
        if self.results:
            return self.results.pop(0)
        return {}


class StubAtlasClient:
    """Stands in for AtlasClient. Records requests, replays scripted results.

    Callers take a client rather than building one, so this substitutes at the
    same seam production code uses -- no patching of module internals.
    """

    def __init__(self, outputs=None, errors=None):
        self.outputs = list(outputs or ["https://cdn/output.png"])
        self.errors = list(errors or [])   # one entry per run(): exception or None
        self.calls = []
        self.downloads = []

    def _record(self, endpoint, body, poll_interval, label):
        self.calls.append({
            "endpoint": endpoint,
            "body": body,
            "poll_interval": poll_interval,
            "label": label,
        })

    def run(self, endpoint, body, *, poll_interval=None, label="Atlas"):
        self._record(endpoint, body, poll_interval, label)
        if self.errors:
            error = self.errors.pop(0)
            if error is not None:
                raise error
        return list(self.outputs)

    def submit(self, endpoint, body, *, label="Atlas"):
        self._record(endpoint, body, None, label)
        return "pred_stub"

    def await_outputs(self, prediction_id, *, poll_interval=None, label="Atlas"):
        return list(self.outputs)

    def download(self, url, path, *, timeout=180):
        self.downloads.append((url, path))
        with open(path, "wb") as handle:
            handle.write(b"fake-mp4")
        return path


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

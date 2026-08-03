"""The Episode Ledger — the authoritative record of every Episode.

Replaces the thirteen row-and-cell methods of the old GSheetReader with an
episode-shaped interface:

    claim_next()  take the next Episode to work on, or learn that a Brief must
                  be written first
    start()       append a freshly written Brief and claim it
    record()      note progress against an Episode
    finish()      publish
    fail()        record an error
    row()         fetch one row by sheet position
    series_parts()  the completed Episodes of a Series, in order

Reads come from a single snapshot taken per Run. Writes are buffered and land
in one batch per stage — except status transitions, which land immediately
because they are the only progress signal an operator watching the sheet has,
and the only breadcrumb a hard kill leaves behind.

This module imports nothing from config. It receives a LedgerSpec; the
get_episode_ledger() factory is what reads the active preset.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from modules.sheet_access import SheetSession, SheetTab


@dataclass(frozen=True)
class LedgerSpec:
    """The preset-derived rules the ledger needs, and nothing else."""

    genres: tuple[str, ...]
    story_mode: str
    series_parts: int
    tracks_episode_numbers: bool = False


@dataclass(frozen=True)
class Episode:
    """One row of the Episode Ledger, as the pipeline sees it."""

    row_index: int
    title: str = ""
    story_brief: str = ""
    genre: str = "blend"
    duration_sec: int = 75
    series_id: str = ""
    part_number: str = ""
    story_mode: str = "standalone"
    arc_number: str = ""
    episode_number: str = ""
    character_form: str = ""
    ref_image_url: str = ""
    character_appearance: str = ""


@dataclass(frozen=True)
class BriefContext:
    """What the brief generator needs when the ledger has no work to hand out."""

    previous_parts: list[dict] = field(default_factory=list)
    past_stories: list[dict] = field(default_factory=list)
    episode_number: int | None = None

    def as_kwargs(self) -> dict:
        return {
            "previous_parts": self.previous_parts,
            "past_stories": self.past_stories,
            "episode_number": self.episode_number,
        }


@dataclass(frozen=True)
class Claim:
    """The result of asking the ledger for work: either an Episode, or the
    context needed to write a Brief so one can exist."""

    episode: Episode | None = None
    brief_context: BriefContext | None = None

    @property
    def needs_brief(self) -> bool:
        return self.episode is None and self.brief_context is not None


# Sheet columns the ledger writes, keyed by the name callers use.
_WRITE_COLUMNS = {
    "script": "script_text",
    "ref_image_url": "ref_image_url",
    "character_appearance": "character_appearance",
    "status": "status",
    "youtube_url": "youtube_url",
    "error_msg": "error_msg",
}


class EpisodeLedger:
    def __init__(self, tab: SheetTab, spec: LedgerSpec):
        self._tab = tab
        self._spec = spec

    # -- claiming work --------------------------------------------------------

    def claim_next(self) -> Claim:
        """Take the next Episode to work on.

        Returns a Claim carrying an Episode when a pending row exists, otherwise
        one carrying the BriefContext needed to write a new Brief. Replaces the
        five separate reads (pending row, past stories, incomplete series, series
        parts, next episode number) the callers used to assemble themselves.
        """
        episode = self._pending_episode()
        if episode is not None:
            return Claim(episode=episode)
        return Claim(brief_context=self._brief_context())

    def start(self, brief: dict) -> Claim:
        """Append a freshly written Brief as a pending row, then claim it."""
        self._append_pending(brief)
        self._tab.refresh()
        return Claim(episode=self._pending_episode())

    # -- recording progress ---------------------------------------------------

    def record(
        self,
        row_index: int,
        *,
        script: str | None = None,
        ref_image_url: str | None = None,
        character_appearance: str | None = None,
        status: str | None = None,
    ) -> None:
        """Note progress against an Episode.

        Content fields buffer; a status transition flushes everything buffered
        so far along with itself. So the common shape — record some content,
        then advance the status — costs one round trip, and the sheet still
        shows the status change as it happens.
        """
        values = {}
        if script is not None:
            values[_WRITE_COLUMNS["script"]] = script
        if ref_image_url is not None:
            values[_WRITE_COLUMNS["ref_image_url"]] = ref_image_url
        if character_appearance is not None:
            values[_WRITE_COLUMNS["character_appearance"]] = character_appearance
        if status is not None:
            values[_WRITE_COLUMNS["status"]] = status
        if not values:
            return
        # A hand-added row can predate a column this release introduced (e.g.
        # character_appearance). ensure_columns is idempotent and reads from
        # the cached header row, so this costs nothing on sheets that already
        # have every column.
        self._tab.ensure_columns(*_WRITE_COLUMNS.values())
        self._tab.stage(row_index, values)
        if status is not None:
            self._tab.flush()

    def finish(self, row_index: int, youtube_url: str) -> None:
        """Mark an Episode published. Lands immediately — the next Run reads it."""
        self._tab.stage(row_index, {
            _WRITE_COLUMNS["status"]: "done",
            _WRITE_COLUMNS["youtube_url"]: youtube_url,
        })
        self._tab.flush()

    def fail(self, row_index: int, error_msg: str) -> None:
        """Record an error. Lands immediately — this is the breadcrumb a crashed
        Run leaves behind."""
        self._tab.stage(row_index, {
            _WRITE_COLUMNS["status"]: "error",
            _WRITE_COLUMNS["error_msg"]: error_msg,
        })
        self._tab.flush()

    # -- direct lookups -------------------------------------------------------

    def row(self, row_index: int) -> dict:
        """One row by sheet position (1-based, header is row 1). Used by the
        re-upload script, which addresses a specific episode by row number."""
        records = self._tab.records
        offset = row_index - 2
        if offset < 0 or offset >= len(records):
            raise IndexError(
                f"Row {row_index} out of range (sheet has {len(records) + 1} rows)"
            )
        return records[offset]

    def latest_incomplete_series(self) -> str | None:
        """The most recent Series of this preset's genres that still has parts
        left to make. Used both to continue a Series and to find an earlier
        part's Reference Image to reuse."""
        return self._latest_incomplete_series()

    def series_parts(self, series_id: str) -> list[dict]:
        """Completed Episodes of a Series, ordered by Part Number."""
        parts = [
            r for r in self._tab.records
            if r.get("series_id") == series_id and r.get("status") == "done"
        ]
        parts.sort(key=lambda r: int(r.get("part_number") or 0))
        return parts

    # -- internals ------------------------------------------------------------

    def _pending_episode(self) -> Episode | None:
        for i, row in enumerate(self._tab.records, start=2):
            if row.get("status") == "pending":
                return Episode(
                    row_index=i,
                    title=row.get("title", ""),
                    story_brief=row["story_brief"],
                    genre=row.get("genre", "blend"),
                    duration_sec=int(row.get("duration_sec") or 75),
                    series_id=row.get("series_id", ""),
                    part_number=row.get("part_number", ""),
                    story_mode=row.get("story_mode", "standalone"),
                    arc_number=row.get("arc_number", ""),
                    episode_number=row.get("episode_number", ""),
                    character_form=row.get("character_form", ""),
                    ref_image_url=row.get("ref_image_url", ""),
                    character_appearance=row.get("character_appearance", ""),
                )
        return None

    def _brief_context(self) -> BriefContext:
        past_stories = self._past_stories()
        previous_parts: list[dict] = []
        if self._spec.story_mode == "series":
            series_id = self.latest_incomplete_series()
            if series_id:
                previous_parts = self.series_parts(series_id)
                print(
                    f"[Ledger] Continuing series {series_id}, "
                    f"part {len(previous_parts) + 1}",
                    flush=True,
                )
            else:
                print("[Ledger] Starting new series", flush=True)

        episode_number = None
        if self._spec.tracks_episode_numbers:
            episode_number = self._next_episode_number()
            print(f"[Ledger] Next episode #{episode_number}", flush=True)

        print(
            f"[Ledger] {len(past_stories)} past stories loaded for anti-repetition",
            flush=True,
        )
        return BriefContext(
            previous_parts=previous_parts,
            past_stories=past_stories,
            episode_number=episode_number,
        )

    def _past_stories(self, limit: int = 20) -> list[dict]:
        stories = [
            {
                "title": r.get("title", ""),
                "story_brief": r.get("story_brief", ""),
                "genre": r.get("genre", ""),
            }
            for r in self._tab.records
            if r.get("status") == "done"
            and r.get("story_brief")
            and r.get("genre", "") in self._spec.genres
        ]
        return stories[-limit:]

    def _latest_incomplete_series(self) -> str | None:
        series_info: dict[str, dict] = {}
        for i, row in enumerate(self._tab.records):
            sid = row.get("series_id")
            if sid and row.get("status") == "done":
                if sid not in series_info:
                    series_info[sid] = {
                        "count": 0, "genre": row.get("genre", ""), "last_row": i,
                    }
                series_info[sid]["count"] += 1
                series_info[sid]["last_row"] = i
        candidates = [
            (sid, info) for sid, info in series_info.items()
            if info["count"] < self._spec.series_parts
            and info["genre"] in self._spec.genres
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[1]["last_row"], reverse=True)
        return candidates[0][0]

    def _next_episode_number(self) -> int:
        """One past the highest Episode Number seen for this preset's genres.

        KNOWN DIVERGENCE: this counts every row, while Part Number counts only
        completed ones — so a single errored Episode splits them permanently.
        Behaviour preserved verbatim from the GSheetReader this replaces; see the
        Episode Number / Part Number entries in CONTEXT.md.
        """
        max_ep = 0
        for row in self._tab.records:
            if row.get("genre", "") not in self._spec.genres:
                continue
            raw = row.get("episode_number", "")
            try:
                ep = int(raw) if raw not in ("", None) else 0
            except (ValueError, TypeError):
                ep = 0
            max_ep = max(max_ep, ep)
        return max_ep + 1

    def _append_pending(self, brief: dict) -> None:
        self._tab.ensure_columns(
            "arc_number", "episode_number", "character_form", "character_appearance",
        )
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
        headers = self._tab.headers
        values = {
            column: brief[source]
            for source, column in field_map.items()
            if source in brief and column in headers
        }
        if "status" in headers:
            values["status"] = "pending"
        if "duration_sec" in headers:
            values["duration_sec"] = 75
        self._tab.append_row(values)


def get_episode_ledger(
    session: SheetSession | None = None,
    sheet_env: str | None = None,
) -> EpisodeLedger:
    """Build the ledger for the active preset.

    This is the only place preset knowledge enters — EpisodeLedger itself takes
    a LedgerSpec and imports nothing from config, so tests can construct one
    without touching the environment.

    `sheet_env` overrides the preset's sheet routing. Pass "GOOGLE_SHEET_ID" for
    tools that always work against the main sheet regardless of which preset is
    active (e.g. scripts/manual_episode.py).
    """
    import os
    from modules.preset import active_preset

    preset = active_preset()
    session = session or SheetSession()

    if sheet_env is None:
        sheet_env = "GOOGLE_SHEET_ID"
        dedicated = preset.episode_sheet_env
        if dedicated:
            if dedicated in os.environ:
                sheet_env = dedicated
                print(f"[Ledger] Using dedicated episode sheet ({preset.name})", flush=True)
            else:
                print(
                    f"[Ledger] WARNING: {dedicated} not set; "
                    "falling back to GOOGLE_SHEET_ID",
                    flush=True,
                )

    spec = LedgerSpec(
        genres=preset.genres,
        story_mode=preset.story_mode,
        series_parts=preset.series_parts,
        tracks_episode_numbers=preset.tracks_episode_numbers,
    )
    return EpisodeLedger(session.tab(sheet_env), spec)

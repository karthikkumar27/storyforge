# Sheet reads are cached per Run, never per process

The Episode Ledger and the character roster are read from Google Sheets, and a
single Run re-reads them several times (five reads of the episodes sheet, three
of the characters sheet). We cache those reads for the lifetime of one Run and
throw the cache away afterwards, rather than memoising at module level, because
the sheets are the runtime source of truth that an operator edits between Runs.

## Consequences

Module-level memoisation (`@lru_cache`, a module global, a singleton reader) is
the obvious optimisation here and it is **wrong for this codebase**. Flask is
long-lived: a process-wide cache means editing a Locked Appearance paragraph or
fixing a Brief has no effect until the server restarts. That silently produces
Episodes from stale canon — expensive to notice, since the output looks fine.
It would also contradict `docs/alan-story-sheets-schema.md`, which promises that
sheet edits take effect on the next Run with no code change.

The cost is that the cached view has to be threaded through as an argument
(`brief_generator`, `script_generator`, `orchestrator`) instead of being reachable
from anywhere. That is deliberate: passing it makes the cache's lifetime visible
at every call site, which is what keeps it correct.

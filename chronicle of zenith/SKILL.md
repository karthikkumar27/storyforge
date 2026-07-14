---
name: fe-to-be-sync
description: |
  Orchestrates FE → TSD → BE sync for SkyIQ 2.0. When invoked via /sync-be {feature-name},
  or when FE source changes are detected in skyiq-fe/src/features/, this skill:
  (1) extracts API contracts from React/Vite frontend code,
  (2) generates or updates the Technical Specification Document (TSD) with complexity scoring
      and BE recommendations,
  (3) scaffolds or patches the corresponding NestJS module with Prisma schema, Zod DTOs,
      Swagger decorators, and Jest tests,
  (4) runs biome + tsc + jest validation gates with bounded retries.
  Use this skill any time the FE leads the BE contract. Do NOT use for FSD-to-spec conversion
  (use fsd-to-prd) or pure DB schema work (use backend-gcp-expert).

allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Grep
  - Glob
  - Task
  - mcp__gitlab__*
  - mcp__postgres__*

triggers:
  - "/sync-be"
  - "sync backend for"
  - "regenerate BE for"
  - "update TSD for"
---

# FE → TSD → BE Sync

This skill turns frontend API contracts into a documented, validated NestJS backend. It runs in
four phases with explicit gates between each. Each phase delegates to a focused subagent via the
Task tool to keep contexts clean.

---

## Workspace layout (configurable)

The skill reads these paths from the workspace root `CLAUDE.md` under the `## Repository layout`
heading. Defaults are shown below — override in root CLAUDE.md if your structure differs.

```
~/work/skyiq/
├── skyiq-fe/                    # FE_REPO
├── skyiq-be/                    # BE_REPO
├── docs/tsd/                    # TSD_DIR
└── .claude/skills/fe-to-be-sync/  # this skill
```

If the user invokes `/sync-be` from within a single-repo (no workspace root), use Pattern 2 from
the project README — read `FE_REPO_PATH` and `BE_REPO_PATH` from the local CLAUDE.md instead.

---

## Phase 1 — API extraction

**Goal:** Build a structured list of every API endpoint the feature touches.

**Inputs:**
- `feature-name` from invocation (e.g. `airport-view`)
- FE source: `${FE_REPO}/src/features/${feature-name}/`
- Last sync SHA from TSD frontmatter (if exists)

**Steps:**

1. Run `git -C ${FE_REPO} log -1 --format=%H` to capture current HEAD.
2. If TSD exists, read `last_fe_sync` SHA from frontmatter and run:
   ```bash
   git -C ${FE_REPO} diff ${last_fe_sync}..HEAD -- src/features/${feature-name}/api/
   ```
   Otherwise scan the full `api/` directory.
3. For every file in scope, extract:
   - HTTP method + path (from fetch/axios/tanstack-query call signatures)
   - Request schema (Zod schema, TS interface, or inline type)
   - Response schema (return type of the query/mutation)
   - Auth requirement (presence of `Authorization` header or auth context)
   - Query, path, and body params with types
4. Also scan `*.types.ts` and `*.schema.ts` siblings for shared schemas.
5. Output a JSON manifest at `/tmp/sync-be-${feature-name}-extract.json` with one entry per
   endpoint. This becomes the input to Phase 2.

**Subagent invocation:**
```
Task: "Extract API contracts from skyiq-fe/src/features/${feature-name}/. Output structured
JSON to /tmp/sync-be-${feature-name}-extract.json. Follow the schema in
.claude/skills/fe-to-be-sync/reference/extraction-schema.md."
```

**Failure modes to handle:**
- Endpoint uses dynamic path construction → flag as `path: "DYNAMIC"`, capture the construction
  expression, surface for human review in Phase 2 output.
- Response type is `any` or `unknown` → flag as `complexity_blocker: "untyped_response"`.
- No matching files found → exit with `status: "no_changes"`, do not proceed to Phase 2.

---

## Phase 2 — Complexity analysis & TSD update

**Goal:** Score each endpoint and write the BE recommendation block to the TSD.

**Scoring rubric** (apply to each endpoint, sum the weighted factors):

| Factor | Weight | Notes |
|---|---|---|
| Joined tables in response | ×2 per join | Count distinct entities returned |
| Write side-effects | ×1.5 per write | Each insert/update/delete on a table |
| Real-time / streaming | ×3 if present | WebSocket, SSE, polling <5s |
| External API calls | ×2 per integration | Third-party services, including AIMS |
| Aggregation depth | ×1.5 per level | GROUP BY, window functions, rollups |
| File upload/download | ×2 if present | Multipart, signed URL flows |

**Tier mapping:**

- **Tier 1 (1–3): Pure CRUD** — Controller + Prisma direct, single DTO, no service layer.
- **Tier 2 (4–6): Joins + pagination** — Service layer, cursor pagination, composite indexes.
- **Tier 3 (7–8): Transactional** — `prisma.$transaction`, repository pattern, optimistic locking.
- **Tier 4 (9–10): Async / real-time** — BullMQ queue, WebSocket gateway, Redis cache, idempotency.

**Steps:**

1. Read the manifest from Phase 1.
2. For each endpoint, compute the score and assign the tier.
3. For Tier 3+ endpoints, **pause and surface the recommendation block before generating code**.
   Print to chat and wait for user confirmation. Tiers 1–2 proceed automatically.
4. Open or create `${TSD_DIR}/${feature-name}.md` and write/merge using the template at
   `reference/tsd-template.md`.
5. Update frontmatter:
   ```yaml
   last_fe_sync: <new-FE-HEAD-sha>
   last_be_sync: <existing-or-null>
   schema_version: <bump>
   ```
6. Stage the TSD change: `git -C ${TSD_DIR} add ${feature-name}.md` (do not commit yet — Phase 4
   batches the commit).

**Subagent invocation:**
```
Task: "Score each endpoint in /tmp/sync-be-${feature-name}-extract.json using the rubric in
.claude/skills/fe-to-be-sync/reference/complexity-rubric.md. Generate the BE recommendation
block and merge into ${TSD_DIR}/${feature-name}.md following the template at
reference/tsd-template.md. Pause on Tier 3+ endpoints."
```

---

## Phase 3 — BE generation

**Goal:** Scaffold or patch NestJS modules so they match the TSD.

**Stack constraints (non-negotiable, from PROJECT_EXECUTION_INSTRUCTIONS.md):**
- Framework: NestJS (latest stable)
- ORM: Prisma with PostgreSQL
- Validation: Zod (NOT class-validator) — use `nestjs-zod` for DTO integration
- TypeScript style: follow `matt-pocock-typescript-style` skill conventions
- Linter/formatter: Biome (NOT ESLint/Prettier)
- Test framework: Jest with supertest for e2e
- API docs: Swagger via `@nestjs/swagger` decorators
- Database connection: route via the appropriate Postgres MCP — `skyiq_db`, `analytics_db`,
  or `aims_db` based on the table being read/written

**Generation patterns by tier:**

### Tier 1 — Pure CRUD
```
src/modules/${feature}/
├── ${feature}.module.ts
├── ${feature}.controller.ts
├── dto/
│   ├── create-${feature}.dto.ts    # Zod schema
│   └── ${feature}-response.dto.ts
└── ${feature}.controller.spec.ts
```
No service layer. Controller injects PrismaService directly. ~80 lines total.

### Tier 2 — Joins + pagination
```
src/modules/${feature}/
├── ${feature}.module.ts
├── ${feature}.controller.ts
├── ${feature}.service.ts
├── dto/
│   ├── list-${feature}.dto.ts      # cursor + filters
│   ├── ${feature}-filter.schema.ts # Zod with refinements
│   └── ${feature}-response.dto.ts
├── ${feature}.service.spec.ts
└── ${feature}.controller.spec.ts
```
Service owns the Prisma query. Use `select`/`include` carefully to avoid N+1.
Cursor pagination using indexed columns. Add Prisma `@@index` if missing.

### Tier 3 — Transactional
```
src/modules/${feature}/
├── ${feature}.module.ts
├── ${feature}.controller.ts
├── ${feature}.service.ts
├── ${feature}.repository.ts        # repository pattern
├── domain/
│   ├── ${feature}.entity.ts
│   └── events/                     # domain events
├── dto/
└── tests/
    ├── ${feature}.service.spec.ts
    ├── ${feature}.repository.spec.ts
    └── ${feature}.e2e-spec.ts
```
Wrap multi-table writes in `prisma.$transaction`. Use optimistic locking via `version` column.
Emit domain events for downstream consumers (use the existing event bus, do not create a new one).

### Tier 4 — Async / real-time
Adds:
- `${feature}.processor.ts` — BullMQ worker
- `${feature}.gateway.ts` — WebSocket gateway (if real-time)
- `${feature}.cache.ts` — Redis caching layer
- Idempotency middleware on the controller
- Circuit breaker for external calls

**For Tier 4, ALWAYS pause for human review before generating.** This tier introduces
infrastructure dependencies (Redis, BullMQ workers, WebSocket scaling) that need ops sign-off.

**Steps:**

1. Read the TSD's BE Recommendation blocks for each endpoint.
2. Determine action per endpoint:
   - **New endpoint** → generate full module
   - **Modified contract** → patch existing files, update tests
   - **Removed endpoint** → mark `@Deprecated`, add usage logging, schedule removal in 2 sprints
3. Update `prisma/schema.prisma` if the TSD specifies new tables/indexes.
4. If schema changes are **additive** (new column, new index, new table) → run
   `pnpm prisma migrate dev --name sync_${feature}_${timestamp}` automatically.
5. If schema changes are **breaking** (drop column, change type, rename) → STOP. Surface the
   migration plan and recommend the expand-contract pattern. Do not generate the migration.
6. Run `pnpm prisma generate` to refresh the client.
7. Mark the BE module path in the TSD frontmatter as `last_be_sync: <new-BE-HEAD-sha>` (set
   after Phase 4 commit).

**Subagent invocation:**
```
Task: "Generate or patch NestJS modules in skyiq-be/src/modules/${feature}/ to match the
TSD at ${TSD_DIR}/${feature-name}.md. Follow the tier-specific patterns in
.claude/skills/fe-to-be-sync/reference/be-patterns.md. Use Zod for DTOs (via nestjs-zod),
Biome for linting. Pause on breaking schema changes."
```

---

## Phase 4 — Validation gates

**Goal:** Prove the generated code compiles, passes lint, and passes tests before commit.

**Gates (run in order, fail fast):**

```bash
cd ${BE_REPO}

# Gate 1: Type check
pnpm tsc --noEmit
# If fail → Phase 3 retry with type errors as input

# Gate 2: Lint + format
pnpm biome check --write ./src
# Auto-fixes safe issues; surfaces unsafe ones

# Gate 3: Unit tests
pnpm jest --testPathPattern="${feature}" --passWithNoTests=false
# If fail → Phase 3 retry with failing test names + error output

# Gate 4: e2e tests (Tier 2+)
pnpm jest --config=jest.e2e.config.ts --testPathPattern="${feature}"
# Requires test DB; skip if TEST_DB_URL not set with warning

# Gate 5: Prisma schema validation
pnpm prisma validate
# Catches schema drift between schema.prisma and migrations
```

**Retry policy:**
- Max 3 retries to Phase 3 with accumulated error context
- After 3 failures → escalate to human with diagnostic report at
  `/tmp/sync-be-${feature-name}-failure.md` containing: failed gate, error output, last 3
  generation attempts, suggested manual fix
- Do NOT commit on failure. Leave staged changes for human inspection.

**On success:**
1. Commit using conventional commits format:
   ```
   feat(be/${feature}): sync from FE contract ${fe-head-short-sha}

   - Added: <new endpoints>
   - Modified: <changed endpoints>
   - Deprecated: <removed endpoints>

   TSD: docs/tsd/${feature-name}.md
   FE-Sync-SHA: <fe-head-sha>
   ```
2. Append to `CHANGELOG.md` under "Unreleased → Backend".
3. Update TSD `last_be_sync` to the new BE HEAD SHA.
4. If invoked via webhook (not interactively), push to a branch named
   `auto/sync-be-${feature-name}-${timestamp}` and open an MR via the GitLab MCP, assigning
   the FE author as reviewer.

---

## Reference files (create these alongside SKILL.md)

This SKILL.md is the orchestrator. For progressive disclosure, split the long-form details into:

```
.claude/skills/fe-to-be-sync/
├── SKILL.md                        # this file
└── reference/
    ├── extraction-schema.md        # Phase 1 JSON schema spec
    ├── complexity-rubric.md        # Phase 2 scoring detail + examples
    ├── tsd-template.md             # Phase 2 markdown template
    ├── be-patterns.md              # Phase 3 NestJS patterns by tier
    └── validation-gates.md         # Phase 4 commands + retry logic
```

The skill loads `SKILL.md` always; reference files are loaded only when the relevant phase runs.
This keeps context lean for simple Tier 1 syncs.

---

## Integration with existing skills

This skill **delegates** to:
- `matt-pocock-typescript-style` — when generating TS code in Phase 3
- `backend-gcp-expert` — when DB or deployment-shaped questions arise during Phase 3
- `react-vite-mfe-reviewer` — NEVER called by this skill (FE is read-only here)
- `aviation-po-domain` — consulted in Phase 2 for domain term verification (e.g. "is this a
  crew-scheduling concept that should live in the crew module instead?")

Use the Task tool to invoke each, passing only the relevant subset of context. Do not load
all skills into the parent context.

---

## Webhook entry point (for GitLab CI alternation pattern)

When invoked via GitLab webhook with payload `{trigger: "fe-push", feature, diff_sha, repo}`:
1. Skip interactive Tier 3+ pauses (auto-fail to human review instead)
2. Skip interactive breaking-schema pauses (auto-fail to human review instead)
3. Always push to `auto/sync-be-*` branch + open MR (never commit to main)
4. Notify via Channels MCP on completion or failure

When invoked via GitLab webhook with payload `{trigger: "be-push", feature, diff_sha, repo}`:
- Run **contract drift check only** — compare `skyiq-be/src/modules/${feature}/dto/` against
  the TSD's expected contracts. If drift detected, append a `## Drift detected` section to
  the TSD and notify the BE author. Do NOT regenerate from BE side.

---

## Things this skill must never do

- Run `prisma migrate deploy` (production migrations are human-gated)
- Drop tables or columns without expand-contract approval
- Commit secrets or `.env` files
- Call any LLM directly (delegate via Task tool only)
- Modify the FE repo (FE is the source of truth, BE follows)
- Skip the validation gates "just this once" — if gates fail, stop and escalate

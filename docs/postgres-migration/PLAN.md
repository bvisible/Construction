# PostgreSQL migration plan

Status: draft for review (2026-05-30, after v5.9.1).
Author: DataDrivenConstruction.

## TL;DR

The codebase is in much better shape for Postgres than the first look
suggested. The engine layer already branches on dialect, every datetime
column is timezone-naive (so `TIMESTAMP WITHOUT TIME ZONE` behaves exactly
like today), and the only real porting work is one BIM query builder that
leans on SQLite's `json_extract`. Realistic effort is **3 to 4 focused days**,
not the 5 to 8 originally feared.

The recommended end state keeps SQLite as the zero-config default for
`pip install` and local dev, and makes Postgres the supported production
backend selected purely by `DATABASE_URL` / `DATABASE_SYNC_URL`. Nothing about
the "runs on a small VPS, `docker compose up` and go" promise changes.

## What we actually run today

- Default DB is SQLite (`sqlite+aiosqlite:///./openestimate.db`), used in dev
  AND on the live VPS (systemd sets the 4-slash absolute SQLite URLs).
- `docker-compose.yml` and `.env.example` already describe Postgres 16, but no
  `.env` is present, so SQLite is what boots.
- `backend/app/database.py` already creates the async engine with separate
  branches per dialect: SQLite gets `StaticPool` + `check_same_thread=False`,
  Postgres gets `pool_size` / `max_overflow` (or `NullPool`), and a
  `json_serializer` is set for both. So switching is mostly a URL + infra job,
  not an engine rewrite.

## Findings, grounded in the current tree

### 1. `json_extract` — the one true blocker

- 254 calls to `func.json_extract(...)`, all in a single file:
  `backend/app/modules/bim_hub/repository.py` (the BIM property-search /
  quantity query builder).
- The columns it reads are portable `JSON` columns
  (`bim_hub/models.py`: `properties`, `raw_data` are `mapped_column(JSON)`).
- `json_extract(col, '$.path')` is SQLite syntax. Postgres uses `col ->> 'key'`
  (text) or `col #>> '{a,b}'` (deep path) on `json`/`jsonb`.

Plan: introduce one tiny dialect-aware helper, e.g.

```python
def json_path(col, *path):
    # SQLite: json_extract(col, '$.a.b')
    # Postgres: col #>> '{a,b}'
    ...
```

resolved from `bind.dialect.name`, and replace the 254 call sites with it.
Because they are all in one file with the same shape, this is a mechanical but
careful refactor. For Postgres, prefer `JSONB` over `JSON` for these two
columns (indexable, faster `#>>`); that is a one-line model change plus a
Postgres-only column type, transparent on SQLite.

Effort: ~1.5 to 2 days including re-testing BIM property search end to end.

### 2. Timezone handling — NON-issue (was over-stated)

- `grep timezone=True` across `backend/app` returns **0**. No column is
  timezone-aware. ~558 `datetime.utcnow()` calls all produce naive UTC values.
- Naive Python datetimes map cleanly to Postgres `TIMESTAMP WITHOUT TIME ZONE`
  and round-trip identically to today. There is no naive/aware conflict to
  resolve, so the earlier "2 to 3 day aware-UTC sweep" is not needed.
- Optional hygiene (not required for the migration): migrate
  `datetime.utcnow()` to `datetime.now(UTC)` over time, since `utcnow()` is
  deprecated in 3.12+. This can be a separate, unrelated cleanup.

### 3. `LIKE` case-sensitivity

- 35 `.like(...)` and 23 `.ilike(...)` today.
- SQLite `LIKE` is case-insensitive for ASCII by default; Postgres `LIKE` is
  case-sensitive. Any `.like()` used for user-facing search must become
  `.ilike()` for parity. Pure structural/glob matches can stay.
- Action: audit the 35 `.like()` sites, convert the search-facing ones.

Effort: ~0.5 day.

### 4. Engine / connection args

- Already dialect-branched in `database.py`. Verify the SQLite-only
  `connect_args` (`check_same_thread`) and `StaticPool` are guarded so they are
  never sent to the asyncpg driver. This looks already handled; budget a short
  verification only.

Effort: ~0.25 day.

### 5. Alembic / schema creation

- The app also supports `create_all` for fresh installs. For a fresh Postgres
  we have two options:
  1. Run `alembic upgrade head` on an empty Postgres and fix any
     SQLite-specific migration ops (no `batch_alter_table` usage was found,
     which is the usual SQLite-ism, so this should be mostly clean).
  2. Or `create_all` + the seed pipeline for a clean bring-up, and keep alembic
     as the forward path.
- Recommended: stand up a throwaway Postgres 16, run `alembic upgrade head`,
  and fix anything that trips. Most migrations are additive and dialect-neutral.

Effort: ~0.5 to 1 day (mostly testing).

### 6. Data

- Production data is essentially the showcase/demo set. Cleanest path is to
  re-seed fresh on Postgres rather than copy SQLite rows. If any real
  non-showcase data exists on the VPS that must survive, we use a one-shot
  `pgloader` or a small Python copy script instead.

Effort: ~0.25 day for re-seed; +0.5 day if a real data copy is required.

## Proposed sequence

1. Spin up Postgres 16 locally (`docker compose up db`) and point a dev backend
   at it via `DATABASE_URL` / `DATABASE_SYNC_URL`. Confirm boot + health.
2. Land the `json_path` helper and port `bim_hub/repository.py`; switch the two
   BIM JSON columns to `JSONB` on Postgres. Re-test BIM search.
3. Audit and fix the search-facing `.like()` -> `.ilike()`.
4. Run `alembic upgrade head` on empty Postgres; fix any dialect issues.
5. Seed showcase; run the full backend test suite against Postgres in CI
   (add a Postgres service to the test workflow).
6. Stage on a Postgres-backed environment, run the QA smoke pass.
7. Cut over the VPS: provision Postgres, set the env URLs, deploy, re-seed,
   verify `/api/health`.

## Performance note (answer to "will it be faster?")

- For the current single-tenant demo load, Postgres will not feel faster than
  SQLite, and for tiny single-user reads SQLite can even be quicker.
- Postgres wins where it matters as we grow: real concurrent writes (no
  single-writer lock), large analytical queries, JSONB indexing for BIM search,
  pgvector/PostGIS later, and safe multi-tenant RLS. It is the right base for
  scale and concurrency, not a magic speed-up for the demo.

## Open questions (need your call)

1. Keep dual-support (SQLite default for pip/dev, Postgres for production) or
   make Postgres mandatory everywhere?
2. Where does production Postgres live: managed instance, or self-hosted on the
   current VPS? (The VPS root partition is ~95% full and would need cleanup or
   a bigger disk first.)
3. Plain Postgres 16 first, adding pgvector/PostGIS only when needed (Qdrant
   already handles vectors today), or provision the extensions up front?
4. Re-seed the showcase fresh on Postgres, or migrate the existing VPS SQLite
   data across?

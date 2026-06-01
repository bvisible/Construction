# Decision memo: drop SQLite, or keep dual-dialect?

Status: decision draft (2026-05-30, after v5.9.1). Author: DataDrivenConstruction.
Inputs: 5 investigator findings (coupling, simplification, test/CI, onboarding,
embedded-PG) + `PLAN.md` + `_pg_code_review.md` + `_vps_cutover_plan.md`.

---

## 1. TL;DR verdict

Dropping SQLite is worth it on the *code* side: it deletes a real, recurring
tax (~1,000+ LOC of shims/tests become removable and the per-migration
`batch_alter_table`/dialect-fork ceremony ends), and it collapses the app to one
code path tested by one backend, which kills both the "works-on-SQLite /
breaks-on-PG" bug class and its reverse (PG-only arms nobody tests today). But
"Postgres-only" is not free: it breaks the product's single strongest
distribution claim — *"No Docker, no Postgres, no Redis, no Node ... falls back
to SQLite"* (`backend/README.md:18-22`) — and it is a hard dealbreaker for the
Tauri desktop sidecar, whose entire model is *"All data is stored locally in
~/.openestimate/"* (`desktop-release.yml:149`). The code-level migration itself
is small and largely done (the old "one true blocker," 254 `json_extract` calls
in `bim_hub/repository.py`, is **already** ported to the dialect-aware
`json_path_text()` helper per `_pg_code_review.md`). **THE single blocking
question is therefore not technical — it is product: must the zero-config,
one-command, no-server install survive?** If yes, the answer is dual-support (or
embedded-PG as the default delivery vehicle), never BYO-Postgres-mandatory.

## 2. The real cost of the status quo (the dual-dialect tax)

This is the honest case *for* dropping SQLite. Quantified from the
simplification investigator:

- **~1,000+ LOC removable.** Two modules deletable in full on PG-only:
  `sql_json.py` (80 LOC `json_path_text` shim, 20 call sites) +
  `sqlite_retry.py` (79 LOC middleware, explicit no-op on PG) = 159 source LOC,
  plus their 328 LOC of tests. Add `db_types.py` MoneyType/SafeDate branching
  (~50-60 LOC), the `pg_optimizations.py` JSON→JSONB `@compiles` trick (~40 LOC,
  needed only because models declare generic `JSON` for SQLite portability), the
  `_tolerant_json_loads` + SQLite PRAGMA listener (~50 LOC), and the 7 runtime
  JSONB-containment-vs-LIKE-scan forks.
- **The per-migration ceremony never ends under dual-dialect.** Of 198 alembic
  files: 52 use `batch_alter_table` (the SQLite-only table-rebuild ALTER),
  54 branch on `bind.dialect.name`, 44 carry `0 if is_sqlite else false`
  boolean-default forks, and 94 branch on both. Every *future* migration pays
  this. (Note: PLAN.md's claim of "no `batch_alter_table` found" was wrong — the
  simplification audit found 144 occurrences across 52 files.)
- **A latent correctness liability.** 95 `.like(` vs 47 `.ilike(` call sites:
  SQLite `LIKE` is case-insensitive, PG `LIKE` is case-sensitive, so any
  search-facing `.like()` tested only on SQLite is a latent PG bug. Money is
  stored as `VARCHAR` on SQLite (`db_types.py`) — a lexical-sort/aggregate
  footgun. 803 GUID columns store UUIDs as untyped `String(36)` to satisfy
  SQLite.
- **The whole suite is blind to PG today.** Tests run on in-memory/per-module
  SQLite (`conftest.py:25-29`); CI does `pip install -e .[dev]` then bare
  `pytest` with **no Postgres service** (`ci.yml:30-67`), and `asyncpg` is gated
  behind the `[server]` extra so `.[dev]` doesn't even install it. So every
  `dialect=='postgresql'` arm and `to_tsvector` full-text path
  (`file_search/service.py:349-354`) ships **untested**.

Bottom line: the tax is real and ongoing, but it is *maintenance drag and risk*,
not a fire. None of it crashes the running app.

## 3. What "Postgres-only" actually breaks (ranked)

1. **Tauri desktop — hard dealbreaker.** The desktop sidecar *is* the CLI
   (`pyinstaller.spec:84` entry = `cli.py`; `aiosqlite` bundled at line 26);
   `main.rs:76-102` just spawns `openestimate-server` and waits for
   `/api/health`. No DB server is in the bundle, and a non-technical end user
   cannot be asked to install Postgres. There is no embedded-PG machinery in the
   tree today (no `initdb`/`pg_ctl`). SQLite is the only realistic embedded DB
   unless we adopt an embedded-PG package (see §4-B).
2. **First-run / pip onboarding — near-dealbreaker.** The happy path is exactly
   3 commands (`pip install` → `openestimate init-db` → `serve`) and the README
   headline sells *no server required*. PG-only deletes that: every user must
   provision Postgres before first launch (friction), or run docker-compose
   (Docker is explicitly *not* a default requirement), or we bundle PG (wheel
   bloat vs the deliberately-lean build that excludes numpy/pandas/torch).
3. **Tests / CI — real work, not a flip.** Requiring PG needs: (a) un-gate
   `asyncpg`+`psycopg2` from `[server]`; (b) a CI `services: postgres:16` or
   testcontainers; (c) porting the SQLite-locked cluster — `sqlite_master`
   FK-index introspection (`test_boq_fk_indexes.py`), the boq-events
   dialect-behavior test (`test_boq_events.py:62-104`), MoneyType/SafeDate dual
   branches, and FK-OFF orphan-insert IDOR fixtures that **cannot** disable FKs
   per-connection on PG; (d) an isolation rewrite — today's isolation is a fresh
   *file* per module via 346 `create_all` rebuilds, which over a socket ×346 on
   PG turns into minutes unless reworked to session-schema + per-test SAVEPOINT
   rollback. Also loses the zero-dependency `clone + pip install + pytest` dev
   flow on Windows boxes.
4. **Demo/eval friction.** The frictionless single-file SQLite-on-VPS eval
   disappears; evaluators land on Docker or managed PG.
5. **Behavioural divergence to load-test (not a break).** `boq/events.py:286`
   *registers* the activity-log wildcard handler on PG (skipped on SQLite), so
   more event/subscriber fan-out goes live on Postgres and must be load-tested.

What does **not** block: the engine is already dialect-branched, both PG drivers
already ship as deps, 0 timezone-aware columns (naive→`TIMESTAMP WITHOUT TIME
ZONE` round-trips identically), a `migrate_sqlite_to_postgres.py` copier already
exists, and the `json_extract` cluster is already ported. Per `_pg_code_review.md`
there are **0 runtime PG blockers** — only 3 HIGH cutover items (truncate
cyclic-FK, GIN opclass, pool sizing).

## 4. The three viable strategies

**A) Keep dual — SQLite default + PG opt-in via `DATABASE_URL` (status quo).**
Zero onboarding/desktop risk and ships today; but you keep paying the
dual-dialect tax forever and the PG paths stay under-tested unless you add a PG
CI lane anyway.

**B) Postgres-only, with EMBEDDED Postgres as the universal default (pip/desktop
spin up a managed local PG).**
Preserves the one-command UX *and* lets you delete the entire dual-dialect tax —
the best-of-both option, viable today via `pixeltable-pgserver` (Apache-2.0,
v0.5.1 Jan-2026, real PG-16 wheels for Linux/macOS/Windows x86+arm at only
~10-13 MB; the integration drops into the existing `cli.py` serve seam with no
engine change); but it makes you the owner of PG major-version upgrades, stale
`pgdata` lock recovery, and Windows loopback port conflicts for every embedded
user, riding on a single team's niche package (with a yank history) — so it is
sound as the default *only* if you accept that operational ownership.

**C) Postgres-only, BYO Postgres (user provides / docker-compose).**
Simplest, cleanest code (one dialect, no embedded lifecycle, smallest wheel);
but the worst onboarding and an outright dealbreaker for the desktop channel and
the "runs anywhere, no server" promise.

## 5. Recommendation + the one founder decision

**Recommended: B as the strategic target, reached by way of A — but only if the
founder commits to embedded-PG operational ownership; otherwise stay on A.**

Concretely, regardless of A vs B, do the no-regret work now because it is owed
either way and de-risks everything: stand up a PG CI lane (un-gate `asyncpg`,
add `services: postgres:16`, run the suite on PG so the PG arms stop shipping
blind), and land the 3 HIGH cutover fixes from `_pg_code_review.md`. That makes
Postgres a fully supported, tested production backend selected by `DATABASE_URL`
— which already answers the VPS/scale need without touching onboarding.

Then the choice between staying at A and advancing to B (which is what *retires*
the dual-dialect tax) collapses to one product judgment only the founder can
make:

> **Is the zero-config, one-command, no-server-required install (pip happy path
> AND the Tauri desktop "all data in ~/.openestimate") a permanent product
> promise we must preserve — even at the cost of owning an embedded-Postgres
> lifecycle (initdb, pgdata lock recovery, PG major-version upgrades, Windows
> port retries) for every default user?**

- **Yes, preserve it, and yes, we'll own embedded-PG** → go **B**: ship
  embedded-PG as the default, delete SQLite and the dual-dialect tax.
- **Yes, preserve it, but no, we won't own embedded-PG** → stay **A**: keep
  SQLite default, add the PG CI lane, accept the ongoing tax as the price of
  zero-friction distribution.
- **No, the no-server install is not sacred (we're fine targeting teams who run
  real infra)** → go **C**: simplest code, but knowingly kill the desktop
  channel and the headline promise.

Do **not** adopt C-style "PG mandatory, BYO" while still advertising the
no-server install or shipping the desktop app — that combination is internally
contradictory.

---

### One reconciliation note for the record
The embedded-PG investigator lists "254 `json_extract` in `bim_hub/repository.py`"
and the `.like→.ilike` audit as still-open code blockers (echoing PLAN.md). The
more recent `_pg_code_review.md` confirms the `json_extract` cluster is **already
migrated** to `json_path_text()` (lines 25, 224, 232, 238, 244) and finds **0
runtime PG blockers**. Treat the code-review as current: the remaining work is
the `.like()` search audit (~0.5 day) plus the 3 HIGH cutover items, not a
blocker that gates the decision above.

# PostgreSQL Readiness — Models & Alembic Assessment

**VERDICT: models: 0 real PG breakers; alembic: 0 reachable on fresh PG.**

## Deploy strategy (confirmed in code)

On a fresh PostgreSQL deployment the schema is built at app startup by
`Base.metadata.create_all`, which fires the JSONB `@compiles` hook + the performance-index
`after_create` event in `backend/app/core/pg_optimizations.py`; the alembic revision is then
recorded with `stamp head`. The alembic upgrade chain is **not** replayed on PostgreSQL.
SQLite stays the default for `pip install` users.

This is reinforced by `backend/alembic/env.py` (`_is_fresh_blank_db` + `_bootstrap_fresh_db` +
`run_migrations_online`, lines 148-212): even `alembic upgrade head` against an empty DB
short-circuits to `create_all` + `stamp heads`. So the migration chain is **doubly**
unreachable on a fresh PG — neither the app-boot path nor the alembic-CLI path replays it.

## Scope scanned (verified counts)

- 98 model files (96 `app/modules/*/models.py` + core `audit.py` / `audit_log.py`)
- 915 `server_default` declarations across 90 model files
- 198 migration `.py` files under `backend/alembic/versions/`
- `backend/alembic/env.py`, `backend/alembic.ini`, `backend/app/core/pg_optimizations.py`

Note on model design: the models **deliberately** put a `server_default` on every NOT NULL
column (their docstrings say so, e.g. accommodation/geo_hub/formwork: "Every NOT NULL column
carries a `server_default` so a fresh `create_all` works"). The right question is whether any
of those default *literals* are SQLite-specific. None are.

---

## Models

Distinct `server_default` right-hand-side values (counts) — the entire universe of model
defaults: `"{}"` ×292, `"0"` ×181, `"[]"` ×125, `""` ×75, `"1"` ×40, `func.now()` ×8, plus
~120 short text-enum / numeric / JSON-literal strings (`"pending"`, `"active"`, `"100"`,
`"0.0"`, `"0.01"`, `'{"x":0,"y":0,"z":0}'`, `'["boq_quality"]'`, `"#16a34a"`, `"UTC"`, etc.).
All PostgreSQL-safe:

- **JSON literals** (`"{}"`, `"[]"`, `'{"x":0...}'`, `'["*"]'`) sit on generic `JSON` columns.
  `create_all` rewrites the column to `JSONB` via `@compiles(JSON,"postgresql")` in
  `pg_optimizations.py`, and `DEFAULT '{}'`/`'[]'` are valid JSONB input literals on PG. OK
- **Numeric strings** (`"0"`, `"1"`, `"100"`, `"0.0"`, `"0.01"`, `"3600"`, `"0.95"`) on
  Integer/Numeric/Float columns — PG coerces the quoted literal to the column type. OK
- **Boolean `server_default="0"`/`"1"`** (34 columns) — PG accepts `'0'`/`'1'` as boolean
  input literals (→ `false`/`true`). OK
- **Text enums** (`"pending"`, `"draft"`, `"active"`, …) — plain `DEFAULT '...'`. OK
- **Timestamps** use `server_default=func.now()` (8 columns) — renders `now()` on PG,
  `CURRENT_TIMESTAMP` on SQLite, via SQLAlchemy. Correct on both. OK

The thing a prior audit feared — a bare string `server_default="CURRENT_TIMESTAMP"` that PG
would emit as `DEFAULT 'CURRENT_TIMESTAMP'` and fail to coerce — **does not exist**: 0
occurrences of `CURRENT_TIMESTAMP` and 0 bare `now()`/`NOW()` strings in the model layer. The
8 timestamp defaults correctly use the `func.now()` SQL expression, not a string.

Money is `Numeric(p,s)` (`Numeric(18,2)`/`Numeric(14,2)`/`Numeric(10,4)`) with Python-side
`default=Decimal("0")`. `Float` is used on 34 columns, all non-money (clash
tolerance/clearance/penetration/distance, lat/lng/GPS, AI confidence, markup opacity, BCF
field-of-view, temperature). The scan found **0** Float columns with money-style names — no
Float-money latent bug.

| file:line | issue | breaks-on-PG? | recommended action |
|---|---|---|---|
| 915 `server_default` decls across 90 files | literal defaults: JSON `"{}"`/`"[]"`, numeric `"0"`/`"1"`/`"0.0"`, text enums | **NO** — all PG-coercible literals | no-op |
| 34 `Boolean ... server_default="0"`/`"1"` (e.g. `safety/models.py:48,53`; `boq/models.py:39`; `crm/models.py:55-57`; `finance/models.py:127,256`; `notifications/models.py:64`) | boolean default given as `'0'`/`'1'` | **NO** — PG accepts `'0'`/`'1'` boolean literals | no-op (optionally `sa.text("false")`/`"true"`) |
| 8 `server_default=func.now()` (`cde:120`, `costs:170`, `eac:280,523,717`, `geo_hub:762`, `progress:89`, `schedule:484`) | timestamp default via SQL expr | **NO** — renders `now()` on PG | no-op |
| 292 JSON-literal `server_default="{}"`/`"[]"` on generic `JSON` cols | relies on JSONB compile hook | **NO** — neutralized by `pg_optimizations.py` `@compiles(JSON,"postgresql")`; `DEFAULT '{}'` valid JSONB literal | no-op |
| Money cols `Numeric(18,2)` etc. (53 files; e.g. `accommodation:137,244`, `crm:211,223,358-365`, `property_dev:80,93,376-382`) | correctly Decimal, not Float | **NO** | no-op |
| `Float` cols ×34 (e.g. `clash:82,86,198,200,240`, `clash_ai_triage:95`, `daily_diary:132-133`, `markups:56`) | Float for non-money quantities | **NO** (cross-dialect, not money) | no-op |
| `JSONB` literal in models = 7 hits — **all in comments/docstrings**, 0 real column types (e.g. `property_dev:1427` comment "JSON (not JSONB) because SQLite-compat") | cosmetic | **NO** | no-op |
| 14 `CheckConstraint(...)` (`clash_ai_triage:70`, `dashboards:206,210`, `erp_chat:123`, `progress:46,50,54,123`, `schedule:407`) | CHECK constraints | **NO** — standard ANSI CHECK, fully supported (better) on PG | no-op |
| Integer PKs `Integer primary_key=True` (all modules) | autoincrement | **NO** — create_all maps Integer PK → IDENTITY/SERIAL on PG | no-op |
| UUID PKs/FKs via `GUID()` TypeDecorator ×777 | custom cross-dialect UUID type | **NO** — `GUID` renders native `UUID` on PG, `CHAR(36)` on SQLite (by design) | no-op |

Negative findings (scanned app-wide, none present): bare `CURRENT_TIMESTAMP` (0), bare
`now()`/`NOW()` string defaults (0), hardcoded `JSONB` column types (0 — the 7 hits are
comments), `dialects.sqlite` imports in models (0), explicit `autoincrement=` (0), real
`UUID`/`ARRAY` dialect types hardcoded (0 — UUID goes through the portable `GUID` decorator).

The prior audit's "~6 high findings in models.py about PG incompatibility" do not correspond
to anything real in the current tree — most likely substring false-positives (matching
`default`, or the word `JSONB`/`sqlite` inside comments), or findings that predate the move to
`func.now()` for timestamps and the `GUID` decorator for UUIDs.

---

## Alembic

`backend/alembic/env.py` and `alembic.ini` contain **no** `render_as_batch` and **no**
`compare_type` (verified: grep returns nothing). env.py's only SQLite-relevant logic is the
fresh-blank-DB short-circuit (create_all + stamp heads). So there is no env-level forced batch
mode and no autogenerate-time SQLite coupling.

Across 198 migration files the raw keyword counts look alarming but resolve to safe patterns:

- **`batch_alter_table` in ~78 source files, but `recreate=` in 0.** Without
  `recreate="always"`, Alembic's batch context falls back to a direct `ALTER TABLE` on any
  non-SQLite backend — it only does the copy-and-rename table rebuild on SQLite. The blocks
  wrap simple `add_column`/`create_index`/`alter_column`/`drop_column` ops (e.g.
  `v3036_linked_positions.py:54-102`). Portable if ever replayed; irrelevant on fresh PG.
- **`sqlite` / `dialect.name` references in ~78 / ~59 files are the *correct* portability
  pattern**, not a bug: `is_sqlite = bind.dialect.name == "sqlite"` then a `JSONB if
  postgresql else sa.JSON` choice, or comments explaining the fresh-SQLite-dev re-run guard
  (e.g. `v090_add_all_new_modules.py:39`, `v2934_match_search_log.py:51`,
  `7f3ab0f2d4e1_phase2e_money_numeric.py:69` MoneyType). These branches do the right thing on PG.
- **`json_extract` appears in exactly 2 migrations** (`v2940_assemblies_resource_type.py:38-55`
  and `v3148_remove_example_webhook_orphans.py:35-50`), and **both are already dialect-guarded**:
  each has `if dialect == "sqlite": ...json_extract(metadata,'$.x')...` plus an explicit
  PostgreSQL branch using the jsonb `->>` operator (`metadata ->> 'x'`). v3148's own comment
  states "SQLite (dev) supports json_extract; PostgreSQL (prod) supports the ->> operator."
  Correct on both dialects, and never reached on a fresh PG anyway.
- **0 PRAGMA, 0 `INSERT OR IGNORE`/`OR REPLACE`, 0 SQLite-only SQL** (`AUTOINCREMENT` /
  `WITHOUT ROWID` / `strftime` / json1 funcs / `||` concat) inside `op.execute` payloads.
- **0 boolean-as-integer `SET col = 0/1` UPDATEs.** The one `is_preset = 1` hit
  (`v3114_propdev_house_type_catalogue.py:194`) is inside a `SELECT COUNT(*) ... WHERE
  is_preset = 1` read guard, not a column write. `updated = 0` (`v3145:131`) is a Python loop
  counter, not SQL.

Decisive point for Question 2: **none of these are reachable on a fresh PG deploy** — the
upgrade chain never runs there (create_all + stamp; env.py also short-circuits the CLI path).
They would only matter if someone forced the chain on a non-fresh PG, and even then they are
dialect-aware or portable.

| file:line | issue | breaks-on-PG? | recommended action |
|---|---|---|---|
| `backend/alembic/env.py` + `alembic.ini` | NO render_as_batch / compare_type; fresh-blank-DB short-circuit create_all + stamp heads (env.py 148-212) | **NO** — env actively prevents chain replay on fresh DB | no-op (already correct) |
| `versions/*.py` — `batch_alter_table` in ~78 files (e.g. `v3036:54-102`), **`recreate=` count 0** | SQLite-style batch ALTER; no table rebuild | **NO** on fresh PG (chain not run) | safe-to-defer; ONLY-IF-CHAIN-REPLAYED still works (batch → direct ALTER on PG, no recreate) |
| `versions/*.py` — ~59 files branch on `bind.dialect.name` (e.g. `v090:39`, `v2934:51`, `phase2e_money_numeric:69`) | JSON→JSONB / MoneyType dialect branch | **NO** — this is the correct PG-aware pattern, not a bug | no-op (good pattern) |
| `versions/v2940_assemblies_resource_type.py:38-55` & `v3148_remove_example_webhook_orphans.py:35-50` | `json_extract(...)` in op.execute SQL | **NO** — both have explicit PG branches using `metadata ->> 'x'`; never reached on fresh PG | no-op (already dialect-guarded) |
| `versions/v3114_propdev_house_type_catalogue.py:194` | `WHERE is_preset = 1` in a `SELECT COUNT(*)` guard | **NO** — read predicate, portable; not reached on fresh PG | no-op |
| `versions/*.py` — all `op.execute` payloads | raw SQL | **NO** — portable ANSI (UPDATE/DELETE/INSERT/DDL); 0 SQLite-only constructs; not reached on fresh PG anyway | no-op |

---

## Bottom line

- **Models:** 0 fresh-PG breakers. All 915 `server_default` literals are PG-coercible
  (JSON `{}`/`[]` → JSONB, numeric/boolean strings, text enums, `func.now()` timestamps).
  0 `CURRENT_TIMESTAMP`. Money is `Numeric`; Integer PKs become IDENTITY; UUID via portable
  `GUID` decorator; JSON becomes JSONB via the compile hook. Nothing in the model layer needs
  a fix for the PG migration.
- **Alembic:** 0 reachable SQLite-isms on a fresh PG deploy. The chain is never replayed on PG
  (create_all + stamp head; env.py short-circuits the CLI path too). The high `batch_alter_table`
  / `sqlite` keyword counts are either the *correct* JSON→JSONB dialect-branch pattern or
  batch-without-`recreate` (which becomes a plain ALTER on PG). Both `json_extract` migrations
  are already PG-guarded with jsonb `->>` else branches. No PRAGMA / INSERT OR IGNORE /
  SQLite-only SQL / boolean-as-int write / `recreate=` exists. No fix required.

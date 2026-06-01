# SQLite Coupling Inventory (beyond the engine layer)

Dimension: how deeply SQLite is wired into the app *beyond* the SQLAlchemy engine
layer (where dual-dialect is cheap). Read-only audit, 2026-05-30.

Repo: `backend/app`. `python` (Windows). `grep` counts below are from ripgrep.

## Headline numbers

- **524** total textual `sqlite` occurrences across **169** files in `backend/app`.
  The overwhelming majority (~440+) are **comments / docstrings** explaining a
  *portability choice already made* (e.g. "money stored as String for SQLite
  REAL precision", "SQLite returns naive datetimes — normalise to UTC", "publish
  detached to avoid SQLite single-writer deadlock"). These are NOT coupling — they
  are notes that the code path is already dialect-neutral and runs on Postgres.
- **~21 true runtime dialect branches** (`if 'sqlite' in ...`, `_is_sqlite(...)`,
  `_is_sqlite_dialect()`, `use_sqlite`, `.startswith('sqlite')`) in app code.
- **~8 `dialect.name == 'postgresql'`** branches (the *inverse* check — already
  PG-aware, the cheap/correct pattern).
- Direct `import sqlite3` (raw driver, bypasses SQLAlchemy) in **2 runtime modules**
  + the migration script + ~10 dev/seed scripts.
- **0** Tauri/Electron/Rust desktop build, **0** `services/` SQLite. "Desktop mode"
  is just the Python CLI.

## 1. `_is_sqlite(` call sites + `'sqlite' in` / dialect branches (app runtime)

`def _is_sqlite(url)` lives in `backend/app/database.py:161` (`return "sqlite" in url`).
`def _is_sqlite_dialect()` in `backend/app/modules/boq/events.py:34`.
`def _is_sqlite_lock(exc)` in `backend/app/middleware/sqlite_retry.py:38`.

Runtime branch sites (the load-bearing ones):

| file:line | what it gates |
|---|---|
| `database.py:194` | engine setup — apply SQLite PRAGMAs (cheap engine layer) |
| `database.py:217` | engine setup — pool sizing only on non-sqlite (cheap) |
| `cli.py:328` | `doctor` — validate DATABASE_URL scheme |
| `cli.py:962` | `info` — print DB path+size (sqlite) vs "PostgreSQL" |
| `main.py:509` | `_resolve_sqlite_db_path()` — None unless sqlite |
| `main.py:1014` | mount `SQLiteLockRetryMiddleware` only on sqlite |
| `main.py:1312` | `/api/health` reports `engine: sqlite|postgresql` |
| `main.py:2094` | startup create_all gate (accepts both sqlite OR postgresql) |
| `main.py:2143` | run `sqlite_auto_migrate` only on sqlite |
| `main.py:2150` | log "SQLite"/"PostgreSQL" |
| `main.py:2469` | shutdown / engine-url check |
| `main.py:1908` | `conn.dialect.name == "postgresql"` (register bootstrap INSERT) |
| `module_state.py:43` | derive data-dir from sqlite URL path |
| `boq/events.py:286` | **skip** activity-log wildcard handler on sqlite |
| `costs/router.py:2247` | CWICR JSON query dialect pick |
| `costs/router.py:3185` | CWICR import: sqlite raw path vs PG sync-URL helper |
| `costs/router.py:3703,3706` | `use_sqlite` bulk-insert branch |
| `costs/router.py:4091` | CWICR delete: raw sqlite3 vs sync engine |
| `costs/repository.py:69,252,381` | JSON access: `json_extract` vs `->>` / array-length |
| `projects/file_manager_service.py:678` | format DB-path summary for API response |

Other inverse `dialect.name == "postgresql"` branches (already PG-aware, no fix
needed): `core/db_types.py:69,81,111,133`, `core/pg_optimizations.py:145`,
`bim_hub/service.py:2755`, `property_dev/service.py:6718`,
`file_search/service.py:328` (defaults to `"sqlite"` when bind is None),
`tasks/service.py:312`, `scripts/migrate_sqlite_to_postgres.py:271`.

Dialect-neutral JSON helper: `core/sql_json.py` compiles `json_path_text` to
`json_extract` on sqlite and `#>>`/`->>` on PG via `@compiles` — the *correct*
abstraction; widely used so most JSON reads are already portable.

## 2. Raw `sqlite3` / `aiosqlite` / PRAGMA / INSERT OR IGNORE/REPLACE / BEGIN IMMEDIATE

- `import aiosqlite` / `from aiosqlite`: **0** in app code. aiosqlite is only the
  SQLAlchemy async driver (declared `aiosqlite>=0.20.0` in pyproject:48). BOTH Postgres
  drivers are ALSO already hard deps: `asyncpg>=0.30.0` (pyproject:85, the async driver)
  AND `psycopg2-binary>=2.9.10` (pyproject:86, the sync driver used by the migration
  script and the CWICR sync bulk path). The PG drivers ship today — no new dependency
  needed to run on Postgres.
- Raw `import sqlite3` in **runtime** code (bypasses ORM):
  - `modules/costs/router.py:3340, 4003` — CWICR bulk import/delete fast path.
    Uses `PRAGMA journal_mode=WAL / synchronous=NORMAL / busy_timeout / temp_store /
    cache_size` (router.py:3714-3718, 4009-4010), `INSERT OR IGNORE INTO oe_costs_item`
    (3720, 4013), and `BEGIN IMMEDIATE` (3733). **HAS a working Postgres branch**
    (sync SQLAlchemy + `ON CONFLICT DO NOTHING`) — see router.py:3185-3190, 3251.
  - `core/translation/cache.py:30` + connects at 178/208/249/297/317 — the
    translation cache is a **dedicated standalone SQLite file** (`cache.db`, see
    `core/translation/paths.py:41`), independent of the main DB. Stays SQLite even
    on a PG deployment; not part of the app data DB. Low risk but a separate
    embedded SQLite that survives the migration.
- `import sqlite3` in dev/seed/migration scripts (NOT shipped runtime, but several
  are invoked operationally):
  - `scripts/seed_showcase_snapshot.py` (raw `INSERT OR REPLACE` + `PRAGMA
    foreign_keys=OFF` + `PRAGMA table_info`) — **the first-run demo loader**, sqlite-only.
  - `scripts/export_showcase_snapshot.py` (reads via `sqlite_master` + `PRAGMA`).
  - `scripts/migrate_sqlite_to_postgres.py` — the actual SQLite→PG copier.
  - `scripts/seed_demo_v2.py` (`INSERT OR IGNORE`, `PRAGMA foreign_keys`),
    `seed_demo_v2_resume.py`, `seed_demo_showcase.py`, `enrich_demo_v2.py`,
    `cleanup_local_db.py`, `cleanup_demo_projects.py`, `inject_test_variants.py`,
    `export_catalog_csv.py` — dev tooling, SQLite-hardcoded, not on the prod path.

Engine-layer PRAGMAs (`database.py:199-205`): `journal_mode=WAL`,
`busy_timeout=30000`, `foreign_keys=ON` — gated behind `_is_sqlite`, the cheap layer.

## 3. CLI bootstrap (`backend/app/cli.py`)

`init-db` / `serve` / `doctor` **assume a local SQLite file by default**:

- `_setup_env` (cli.py:185-188):
  ```python
  db_path = data_dir / "openestimate.db"
  os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
  os.environ.setdefault("DATABASE_SYNC_URL", f"sqlite:///{db_path}")
  ```
  `setdefault` — so a pre-set `DATABASE_URL=postgresql://...` env/.env WINS. The CLI
  does not *force* SQLite, it only defaults to it.
- `cmd_init_db` (cli.py:625-746): docstring "create the SQLite database"; on
  `--reset` it unlinks the `.db`, `.db-shm`, `.db-wal` siblings (SQLite WAL files,
  cli.py:634-642) — meaningless on PG. Then imports module models and runs
  `sqlite_auto_migrate(engine, Base)` (cli.py:740-742) + `create_all`. The
  `sqlite_auto_migrate` step is wrapped in try/except and logs "skipped" on failure,
  and `create_all` is dialect-neutral, so `init-db` would *partially* work against PG
  but the WAL-unlink + auto-migrate are no-ops/irrelevant there.
- `doctor` `check_database_url` (cli.py:275-286): accepts `sqlite`/`postgresql`,
  warns on anything else, prints "PostgreSQL mode" or "SQLite mode (default)".
- `info` (cli.py:962): `if "sqlite" in settings.database_url:` prints the file path
  and size, else prints "PostgreSQL".
- Data-dir handling — **TWO namespaces coexist (a known typo split):**
  - The **DB + CLI** dir is `DEFAULT_DATA_DIR = Path.home() / ".openestimate"`
    (cli.py:51, no "r"); `module_state.py:52` and `main.py:2005` agree.
  - But **uploads / photos / sheets / vectors / converters / qdrant / CWICR cache /
    takeoff** all live under `~/.openestimator` **WITH the "r"** — e.g.
    `documents/service.py:92` UPLOAD_BASE, `vector.py:252`, `costs/router.py:2945`
    cache, `match_elements/qdrant_supervisor.py:78`, `config.py:245,280`,
    `boq/cad_import.py:57`. `file_manager_service.py:17,641-649` and `main.py:2000-2010`
    explicitly document the `.openestimator`-vs-`.openestimate` typo and even warn the
    user about it; the JWT secret persists to whichever dir exists.
  - This is **orthogonal to the SQLite→PG migration** (it is filesystem layout, not DB
    dialect) but matters for "first-run data dir" reasoning: only the `.db` file moves
    to PG; all the embedded-file state (vectors, uploads, qdrant, translation cache)
    stays on the local filesystem regardless of DB backend.
  - (The demo *login* email is `demo@openconstructionerp.com`; the historical
    `demo@openestimator.io` used by `seed_demo_v2.py:83` is a separate credentials
    gotcha, not a data path.)

## 4. config.py defaults

`backend/app/config.py:168-169`:
```python
database_url: str = "sqlite+aiosqlite:///./openestimate.db"
database_sync_url: str = "sqlite:///./openestimate.db"
```
Pool-tuning fields (config.py:170+) noted "PostgreSQL only — SQLite ignores".
Defaults are SQLite; overridable by env. Flipping defaults to PG is a one-line change.

## 5. Showcase / demo SEED mechanism — IS it SQLite-specific?

Two-path design, and the answer is **mixed but safe for PG fresh-install**:

- **Fast path = SQLite-only.** `main.py:_seed_demo_data` (around 655-679):
  `_resolve_sqlite_db_path()` returns the on-disk file ONLY for `sqlite:` URLs
  (main.py:507) → `seed_from_snapshot(db_path)`. `seed_showcase_snapshot.py` is
  explicitly "**SQLite only**" (header line 9) and uses raw `sqlite3` +
  `INSERT OR REPLACE` + `PRAGMA table_info`. On a PG URL, `_resolve_sqlite_db_path()`
  is None → `seeded` stays False → **fall through**.
  Note: the *snapshot file format itself is dialect-neutral JSON* (column→value,
  `showcase_snapshot.json.gz`); only the loader is sqlite-bound. So a PG snapshot
  loader could be written reusing the same artifact, but none exists today.
- **Fallback path = dialect-neutral ORM.** `main.py:677-679` →
  `app.core.demo_projects.seed_demo_projects()`. Its docstring (demo_projects.py:1-14):
  "Builds ... directly through the SQLAlchemy ORM (sync Session) so it works on any
  backend — SQLite for local dev, PostgreSQL in production ... makes no dialect
  assumptions ... seeds a fresh PostgreSQL database correctly."

**Conclusion for PG-fresh-install seeding:** YES it can still seed demo data — the
ORM fallback (`seed_demo_projects`) is the primary seeder on PG. The only loss on PG
is the fast snapshot shortcut (seconds vs the slower programmatic seed). No blocker.

## 6. Desktop (Tauri) build & `services/`

- **No Tauri/Electron/Rust at all**: `**/tauri.conf.json` → none, `**/*.{rs,toml}` at
  repo root → none beyond pyproject, no `src-tauri`/`desktop` dirs. "Desktop / CLI
  mode" is purely the Python CLI flipping `SERVE_FRONTEND=true` (cli.py:197) and the
  SQLite default. No native desktop SQLite coupling.
- **`services/` has no Python and no SQLite**: `services/*.py` → none; the CLAUDE.md
  `services/` tree (cad-converter, cv-pipeline, ai-service) is aspirational/absent in
  this checkout. Nothing there hardcodes SQLite.

## Load-bearing-for-first-run summary

Truly SQLite-assuming, and on the boot/first-run path:

1. **config.py defaults + cli.py `_setup_env`** — default URL is SQLite (override-able).
2. **`main.py` startup**: `sqlite_auto_migrate` (main.py:2143, sqlite-only column
   adder that substitutes for Alembic on SQLite dev), `SQLiteLockRetryMiddleware`
   mount (main.py:1014).
3. **Snapshot seeder** (`seed_showcase_snapshot.py`) — sqlite-only fast path;
   gracefully degrades to the ORM seeder on PG, so not a blocker.
4. **`boq/events.py:286`** — activity-log wildcard event handler is **skipped on
   SQLite** to avoid `MissingGreenlet`. On PG it *registers*. So on PG more event
   wiring goes live than on SQLite — a behavioural divergence to test, not a break.
5. **CWICR cost import** (`costs/router.py`) — raw-sqlite3 fast path, but a working
   Postgres branch already exists.

Everything else tagged "sqlite" is either an inverse PG check, the
`core/sql_json.py` portability shim, dialect-neutral ORM, or a comment documenting a
choice that already keeps the code Postgres-safe.

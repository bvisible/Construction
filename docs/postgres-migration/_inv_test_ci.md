# Inventory: Test suite + CI dependency on SQLite

Scope: how the backend test suite and GitHub Actions CI depend on SQLite, and the concrete
cost of making tests require a real PostgreSQL.

## 1. Current test DB mechanism

Tests run against **per-process / per-module temporary on-disk SQLite files** — never
`:memory:` (deliberately avoided, see below), never the prod DB. The override is set at
conftest *import* time (before any `from app...` import) so it beats every module's import
order.

`backend/tests/conftest.py:25-29`:

```python
_TMP_DIR = Path(tempfile.mkdtemp(prefix="oe-tests-"))
_TMP_DB = _TMP_DIR / "session.db"
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TMP_DB.as_posix()}")
os.environ.setdefault("DATABASE_SYNC_URL", f"sqlite:///{_TMP_DB.as_posix()}")
```

Three module-scoped conftests do the same with their own temp file, plus several individual
test modules *force* SQLite regardless of the ambient `DATABASE_URL`:
- `backend/tests/modules/accommodation/conftest.py:16-19` (prefix `oe-accom-`)
- `backend/tests/modules/geo_hub/conftest.py:18-21` (prefix `oe-geo-overlay-`)
- `backend/tests/modules/property_dev/conftest.py:19-22` (prefix `oe-propdev-r7-`)
- 6 modules hard-pin SQLite ("Force SQLite … regardless of the ambient DATABASE_URL"), e.g.
  `unit/costs/test_repository_keyset.py:17-20`, `unit/test_boq_fk_indexes.py:15-18`.

Why on-disk and not `:memory:` (from `test_repository_keyset.py:5-9`): the async engine opens
multiple connections and `:memory:` would give each connection its own empty DB. This is a
real constraint that any PG migration of the fixtures must respect (it is also why a
naive `:memory:` swap is not an option).

Engine selection is dialect-sniffed in `backend/app/database.py:161-228`:
- `_is_sqlite(url) = "sqlite" in url`
- SQLite path: `connect_args={"check_same_thread": False}` + a `connect` event listener
  (`database.py:198-206`) running `PRAGMA journal_mode=WAL`, `PRAGMA busy_timeout=30000`,
  `PRAGMA foreign_keys=ON` (FK enforcement in tests depends entirely on this listener; on
  Postgres FKs are native and always on).
- Postgres path adds `pool_pre_ping=True` + `pool_recycle` (`database.py:217-226`).
- A custom `GUID` TypeDecorator (`database.py:98-131`) stores UUID natively on PG and as
  `String(36)` on SQLite, and a tolerant JSON deserializer (`database.py:165-180`) tolerates
  the untyped-TEXT JSON columns SQLite produces. Both are dialect-aware shims.

### Isolation model: schema-rebuild per module, NOT transaction rollback

There is essentially **no transactional per-test isolation**: only 4 files use `begin_nested`
(`modules/procurement/test_procurement_security.py`, `unit/test_procurement_finance_r7.py`,
`unit/test_punchlist_polish.py`, `unit/test_punchlist_r7.py`) and that is for testing
SAVEPOINT/nested-transaction behavior in those features, not as a global rollback fixture.
Instead each
module-scoped `app_instance` fixture boots the app and calls `Base.metadata.create_all`
against a fresh temp SQLite (e.g. `accommodation/conftest.py:34-39`). Counts in `backend/tests`:
- `create_all` used in **237 files**
- `scope="module"` fixtures: **346** ; `scope="function"`: **0** ; `scope="session"`: **0**
- `drop_all`: 5 (rare; isolation comes from a fresh temp file per module, not teardown)

So "fast isolation" today = a brand-new on-disk SQLite file per test *module* + a full
`create_all` of all module metadata. It is fast because the DB is local (no network, no
connection handshake) and `create_all` on SQLite is cheap — not because of in-memory tx
rollback.

## 2. Test volume

- Test files (`test_*.py`): **621**
- `def test_` occurrences: **8,517** (includes async)
- `async def test_`: **3,979** (so ~4.5k sync, ~4k async test functions)
- `[tool.pytest.ini_options]` (`pyproject.toml:291-301`): `testpaths=["tests"]`,
  `asyncio_mode="auto"`, markers include `unit: no database` and `integration: requires database`.
- **No `addopts`** at all — pytest runs single-process by default. `pytest-xdist` IS a dev
  dependency (`pyproject.toml:155`) but is **not invoked**: CI runs bare `pytest` (`ci.yml:67`),
  and the root `Makefile` test targets (`Makefile:56-71`: `test-backend` = `pytest -x -v`,
  `test-unit -m unit`, `test-integration -m integration`) also pass no `-n`. So parallelism is
  available but unused today. Note the `-m unit` / `-m integration` split exists but CI does
  not use it (CI runs the whole suite, unmarked tests included).

## 3. What CI does for the DB today

`.github/workflows/ci.yml` `backend` job (`runs-on: ubuntu-latest`, working-dir `backend`):
- `pip install -e ".[dev]"` (ci.yml:58)
- `ruff check .` / `ruff format --check .`
- `pytest` (ci.yml:66-67) with **no `services:` block, no Postgres container, no DB env vars.**

The job relies entirely on the conftest SQLite default. No workflow under
`.github/workflows/` defines a `services: postgres:`. (Other workflows: cla, codeql,
dependency-review, desktop-release, eval-match, pypi-publish, release*, sbom, scorecard —
none stand up a DB.)

## 4. Dependency reality (mostly already in place)

`backend/pyproject.toml`:
- `aiosqlite>=0.20.0` (base dep, line 48) — async SQLite driver.
- `asyncpg>=0.30.0` (line 85, **but in the `[server]` optional-extra**, not base) — async PG
  driver. So `pip install -e ".[dev]"` in CI does NOT pull asyncpg today; a PG test lane would
  need `.[dev,server]` (or add asyncpg to dev).
- `psycopg2-binary>=2.9.10` (line 86, also `[server]`) — sync PG driver for alembic.
- `pytest-xdist>=3.5.0` (line 155) — present but unused.
- `testcontainers` — NOT present. `pytest-postgresql` — NOT present.

So the async PG driver already exists in the tree; the gap is that it is gated behind the
`server` extra and CI installs only `dev`.

## 5. SQLite-specific behavioral assertions (NOT just one — this is material)

A real cluster of tests asserts SQLite-specific behavior or hard-pins the SQLite dialect.
These break or become meaningless under Postgres and must be ported, `skipif`-guarded, or
rewritten:

- `backend/tests/unit/test_boq_fk_indexes.py` — introspects **`sqlite_master`** to assert FK
  indexes materialize; force-pins SQLite (lines 15-18).
- `backend/tests/unit/costs/test_repository_keyset.py` — explicitly exercises the
  **`json_extract`** SQLite JSON path against a file-backed SQLite DB ("the dialect-aware
  `_classification_expr` is the riskiest part", lines 11-14). This is the one test file that
  references `json_extract`; it verifies the SQLite branch of `_classification_expr`. (The
  related costs suites — textsearch/category_tree/autocomplete — share the same on-disk-SQLite
  fixture but don't name `json_extract`.)
- `backend/tests/unit/test_boq_events.py:62-104` — `TestWildcardDialectGuard` /
  `test_is_sqlite_dialect_*` assert `_is_sqlite_dialect()` returns False for a
  `postgresql+asyncpg` URL and True for a sqlite URL, and that the boq activity-log wildcard
  handler is **skipped on SQLite but registered on Postgres** — i.e. behavior genuinely
  differs by dialect.
- `backend/tests/unit/test_db_types.py:1-35` — exercises **both** the SQLite and PostgreSQL
  branches of the MoneyType/SafeDate TypeDecorators via stub dialect objects (`_PGDialect`,
  `_SQLiteDialect`); its docstring states hitting a real PG here "would make the suite require
  Docker", so the PG branch is end-to-end-covered only "when `DATABASE_URL` points at a live
  server." This is PG-aware (not SQLite-locked) and documents the exact Docker tradeoff.
- `backend/tests/unit/test_cleanup_local_db.py` (+ `integration/test_dashboard_rollup_perf.py`,
  `unit/test_translation_cache_lru.py`, `unit/test_dockerignore.py`) — use the raw `sqlite3`
  driver directly (cleanup tooling / perf probes that are inherently SQLite).
- Many suites set `PRAGMA foreign_keys=ON/OFF` or `journal_mode=WAL` directly in fixtures
  (eac, smart_views, bim_hub, requirements, daily_diary, jobs, pipeline_executor — ~20 files).
  `daily_diary` / `requirements` deliberately set `foreign_keys=OFF` to insert orphan rows for
  IDOR/negative tests — on Postgres you cannot turn FKs off per-connection, so those test
  setups need a different approach (deferred constraints or different fixtures).

This is the largest hidden cost: it is not "one pragma test" — it is dozens of fixtures and
several dialect-locked suites that encode SQLite semantics.

## 6. Cost of making tests require Postgres

CI cost (GitHub Actions, per backend run):
- Add `services: postgres:16` to the backend job: container start + healthcheck ≈ **15-40s**
  cold (image typically cached on the ubuntu runner image → usually ~15s). Plus install
  `.[dev,server]` to get asyncpg/psycopg2.
- Or `testcontainers-python`: similar one-time spin-up, adds a dependency + Docker-in-runner;
  more flexible for local dev. (The codebase already comments on testcontainers spin-up cost
  for Redis in `integration/core/test_jobs_celery_redis.py:3-11` — they chose eager mode to
  avoid 3-5s per-test container spin-up. Same instinct applies to PG.)

Suite runtime cost:
- The **346 module fixtures each run a full `Base.metadata.create_all`** (237 files). On local
  SQLite this is near-instant; on Postgres each is a burst of DDL over a socket. With ~346
  rebuilds this becomes the dominant new cost. The serial run (no xdist today) would slow
  materially — order of *minutes added* unless mitigated.
- Mitigations needed to stay tolerable: build the schema **once per session** (one `create_all`
  into a template DB) and switch isolation to per-test SAVEPOINT rollback. That is a non-trivial
  rewrite of ~346 module fixtures (today's isolation depends on a *fresh file per module*, not
  rollback), and several FK-OFF fixtures don't translate to Postgres.
- Enabling `pytest-xdist` (`-n auto`) would help offset PG latency since it is already a dep,
  but xdist + a single Postgres needs per-worker schemas/databases — more fixture work.

Dev-loop friction:
- Today: `git clone` + `pip install -e .[dev]` + `pytest` — zero external services, runs fine
  on this Windows dev box.
- After: every dev (and this Windows box) needs a running Postgres or Docker for *any* test,
  including a single unit test. This removes the zero-dependency `pytest` property the conftest
  docstring / `feedback_test_isolation.md` was built around.

## 7. Implications for the drop-SQLite decision

- Dropping SQLite is **not** a config flip for tests. It requires: (a) un-gate asyncpg/psycopg2
  from `[server]` so `dev` installs them (or add to dev), (b) a CI `services: postgres` or
  testcontainers, (c) an isolation-architecture change from per-module `create_all`-on-fresh-file
  to session-scoped schema + transactional rollback (touching ~346 fixtures / 237 files), and
  (d) porting/`skipif`-ing the SQLite-locked suites in §5 (sqlite_master, json_extract,
  GUID/JSON String(36) branch, dialect guard, `sqlite3`-driver cleanup tests, FK-OFF fixtures).
- Biggest perf risk: 346 per-module `create_all` rebuilds against a networked DB.
- Biggest contributor-experience risk: losing zero-dependency local `pytest`.
- Positives that lower the risk: async PG driver (asyncpg) already in the tree, pytest-xdist
  already available, database.py already dialect-sniffes, and a chunk of the codebase already
  carries PG/SQLite dual-path shims (GUID, tolerant JSON, `_classification_expr`,
  `_is_sqlite_dialect`) — so the *production* code is largely PG-ready; the test/fixture layer
  is where the work concentrates.
- Pragmatic middle path: keep SQLite as the default dev/test DB and add an opt-in Postgres CI
  lane (`services: postgres` + `.[dev,server]` + `DATABASE_URL` override) so production-parity
  is exercised in CI without forcing PG on every local run. The SQLite-locked suites in §5
  would stay SQLite-only and be excluded from the PG lane.

# Inventory: Embedded / bundled PostgreSQL viability

Dimension: can OpenConstructionERP be **Postgres-everywhere** while keeping a
zero-config, no-Docker, single-command first run by bundling a real Postgres
binary that the app starts/stops itself?

Date: 2026-05-30. Author: DataDrivenConstruction. Read-only investigation.
All sizes/versions measured directly from the PyPI JSON API on 2026-05-30.

## TL;DR verdict

**PARTIAL, leaning YES-as-opt-in.** An app-managed embedded Postgres on all
three platforms (Linux + macOS + Windows, x86_64 and arm64) is genuinely
possible today via one well-maintained package: **`pixeltable-pgserver`**
(Apache-2.0, latest **0.5.1 from 2026-01-28**). It ships real per-platform
PostgreSQL binary wheels — including fresh **`win_amd64` and `win_arm64`** — at a
surprisingly small **~10-13 MB per wheel**, supports Python 3.10-3.14, and
exposes a clean `get_server(pgdata) -> get_uri()` lifecycle that drops straight
into our existing CLI `serve` seam and our already-dialect-branched engine.

It is, however, still a third-party niche package (one maintaining team,
Pixeltable) and PG-major-pinned. For a product whose whole promise is "one
command, just works for everyone on first run", betting the *only* path on it is
risky. Recommended: keep SQLite as the lean zero-config default and add
embedded-PG as an **opt-in** (`pip install "openconstructionerp[embedded-pg]"`
+ `serve --embedded-pg`). That delivers "real Postgres, no Docker, one command"
to anyone who wants it without bloating the default or single-sourcing the core.

## The candidates (measured from PyPI, 2026-05-30)

| Package | License | Windows wheel? | PG ver | Latest / date | Per-wheel size (latest) |
|---|---|---|---|---|---|
| **pixeltable-pgserver** | Apache-2.0 | **YES — win_amd64 + win_arm64** | 16.x (PG16 line) | **0.5.1 / 2026-01-28** | linux x86 11.9 MB, linux arm 11.8 MB, mac-x86 10.5 MB, mac-arm 10.1 MB, **win_amd64 13.4 MB**, win_arm64 13.4 MB. Py 3.10-3.14 |
| pgserver (orm011, upstream) | Apache-2.0 | YES (win_amd64) | 16.2 | 0.1.4 / 2024-06-08 | ~10-13 MB; **no arm64 windows, no py3.13/3.14**, last release mid-2024 |
| pgembed (Ladybug-Memory) | Apache-2.0 | YES (win_amd64) | 17 | 0.2.0 / 2026-03-18 | **uneven: manylinux 68 MB, macOS-arm 83 MB, musllinux 12 MB, win 14 MB**; py>=3.12 only; newest/least proven |
| postgresql-wheel (michelp) | Apache-2.0 | **NO (Linux only)** | 14.1 | 14.1.2 / **2021-12-29** | Linux manylinux/musllinux only; stale; py 3.7-3.9 |
| testing.postgresql | BSD (wrapper) | n/a | uses system PG | — | tiny, but needs a **pre-installed** Postgres -> fails zero-config |

Reality check vs my first pass: earlier notes said "only 0.2.0, ~186 MB, 2024".
That was wrong — it came from a flaky page render. The PyPI API shows
`pixeltable-pgserver` is actively maintained (15 releases 0.2.0 -> 0.5.1, latest
Jan 2026), and the wheels are ~10-13 MB, not ~186 MB. Note 0.2.0 and 0.2.1 are
**yanked**; pin a current version (0.5.x).

The only candidates that ship a real Postgres engine binary **for Windows** are
`pixeltable-pgserver` (best maintained), `pgserver` (stale), and `pgembed`
(newest, heavier/uneven, py3.12+). `postgresql-wheel` is Linux-only;
`testing.postgresql` needs a system Postgres so it does not satisfy zero-config.

## License fit (AGPL-3.0 core)

- Wrapper code for all three viable bundlers: **Apache-2.0** -> one-way
  compatible with our AGPL-3.0 core (Apache-2.0 combines into AGPLv3).
- Bundled PostgreSQL itself: **PostgreSQL License** (liberal, BSD/MIT-like) ->
  redistributable inside an AGPL project with attribution.
- No license blocker. Add the bundled-binary license to NOTICE.backend.json per
  our existing legal-audit convention.

## How it fits our codebase (the integration is small)

The mechanical fit is clean — the seams already exist:

1. `pixeltable-pgserver`: `db = pgserver.get_server(pgdata)` runs `initdb` on
   first call, then `db.get_uri()` returns a Postgres URI usable by SQLAlchemy /
   asyncpg (**TCP loopback on Windows**, unix socket on Linux/mac). It
   reference-counts across processes and stops on `cleanup()` / context exit.
2. Our CLI already has the hook: `backend/app/cli.py` `cmd_serve` ->
   `_setup_env()` then `uvicorn.run("app.main:create_app", factory=True)`.
   Today `_setup_env` `setdefault`s the SQLite `DATABASE_URL`/`DATABASE_SYNC_URL`
   (lines 185-188). An `--embedded-pg` branch would, before the SQLite
   defaults: start the managed cluster under `~/.openestimate/pgdata`, derive the
   async (`postgresql+asyncpg://`) and sync (`postgresql://`) URLs from
   `get_uri()`, `os.environ.setdefault` them, run `alembic upgrade head`, then
   serve; on shutdown call `cleanup()`. `init-db` would mirror it.
3. Engine layer needs **zero change**: `backend/app/database.py`
   `create_engine_from_settings()` branches on `_is_sqlite(url)` (line 194) and
   already applies asyncpg `pool_pre_ping`/`pool_recycle` for the non-SQLite
   branch (lines 217-226). A Postgres URI just takes the else branch.
4. Drivers are already declared: `backend/pyproject.toml` already lists
   `asyncpg>=0.30.0` and `psycopg2-binary>=2.9.10` (lines 85-86), and there is a
   `pg_optimizations` JSON->JSONB DDL hook wired in `database.py` (lines 235-244)
   plus a ready `app/scripts/migrate_sqlite_to_postgres.py`. So embedded-PG only
   needs to add the one bundler dependency and the start/stop glue — the Postgres
   side of the app is already substantially built out.

So the glue is genuinely small. The residual risk is the bundled engine's
robustness across platforms, not our integration code.

(Orthogonal to the actual SQL port in `docs/postgres-migration/PLAN.md`: the 254
`json_extract` calls in `bim_hub/repository.py` and the `.like()`->`.ilike()`
audit must still be done. Embedded-PG is the *delivery vehicle* for
"Postgres everywhere"; it only pays off once the code is Postgres-correct.)

## Failure modes / risks (why PARTIAL, not unconditional YES)

1. **Single-source niche dependency.** `pixeltable-pgserver` has one maintaining
   team. A yank (0.2.0/0.2.1 were yanked) or an abandoned release could strand
   whichever platform we depend on. For a "just works for everyone" default that
   is a real bus-factor concern; for an opt-in it is acceptable.
2. **PG-major pinning (16).** pgdata encodes the PG major; a later 16 -> 17/18
   bump needs `pg_upgrade` or dump/restore. If we bundle PG we own that upgrade
   story for every embedded user, forever. (pgembed already tracks PG17, but is
   heavier and py3.12+-only.)
3. **Lifecycle hazards.** PID/lock files in pgdata; an abrupt kill (Windows
   force-close, OOM, power loss) can leave a stale lock that blocks the next
   start. Needs detect-and-recover before `serve`. The library's process cleanup
   helps but we must handle the crash-recovery path ourselves.
4. **Windows = TCP loopback, not unix socket.** The Windows path is the most
   fragile: it binds a loopback TCP port, so a clash with an existing Postgres or
   any port squatter needs auto-port-retry and clear errors. (Our CLI already has
   a `check_port_free` for the HTTP port — a similar guard is needed for the DB
   port.)
5. **Footprint vs the 2 GB-VPS promise.** A real postmaster + workers +
   shared_buffers costs materially more idle RAM than SQLite's in-process file.
   Still fits 2 GB with conservative `shared_buffers`/`max_connections`, but if
   embedded ever became the default we must ship tuned-small defaults.
6. **Disk / data-dir growth.** Each `~/.openestimate/pgdata` is a full PG cluster
   (tens of MB minimum even empty) vs a single SQLite file. Fine locally; on the
   ~95%-full VPS root partition it would need the cleanup PLAN.md already flags.
7. **Running as root / Docker.** pgserver refuses to run PG as root and spawns a
   non-root user; correct on Linux/Docker but extra implicit behaviour to reason
   about and document.

## Recommendation

- **Default stays SQLite** — lean (~30 MB wheel today), true single-command first
  run, the zero-config promise intact.
- **Add embedded-PG as an opt-in**: extra `openconstructionerp[embedded-pg]`
  pulling `pixeltable-pgserver` (pinned to a current 0.5.x, never the yanked
  0.2.x) + a `serve --embedded-pg` flag managing `~/.openestimate/pgdata`. This
  is the clean way to "drop the SQLite *requirement*" for power users — real
  Postgres, no Docker, one command — without forcing it on everyone or
  single-sourcing the only run path.
- **Production** keeps using external Postgres via `DATABASE_URL` (managed or
  self-hosted), exactly as PLAN.md targets. Embedded-PG is for local/dev/single-
  box convenience, not the prod database.
- **Revisit "embedded as default"** once we have run it across all platforms in
  CI for a few releases and have a PG-major-upgrade story, OR once a steadier
  multi-maintainer bundler emerges.

## Sources

- pixeltable-pgserver (best maintained, Windows + arm): https://pypi.org/project/pixeltable-pgserver/ and https://github.com/pixeltable/pixeltable-pgserver
- pgserver (upstream, stale): https://github.com/orm011/pgserver , https://pypi.org/project/pgserver/
- pgembed (newest, PG17, heavier): https://github.com/Ladybug-Memory/pgembed , https://pypi.org/project/pgembed/
- postgresql-wheel (Linux-only): https://github.com/michelp/postgresql-wheel
- PostgreSQL announcement (local non-root PG via pip): https://www.postgresql.org/about/news/install-a-local-non-root-postgresql-server-with-python-pip-2291/
- Repo fit: backend/app/cli.py (`cmd_serve`/`_setup_env`), backend/app/database.py (`create_engine_from_settings`), backend/pyproject.toml (asyncpg + psycopg2-binary already declared), backend/app/scripts/migrate_sqlite_to_postgres.py

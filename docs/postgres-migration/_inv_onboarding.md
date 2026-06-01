# PG-only impact on Onboarding & Distribution

Investigation dimension: what does dropping SQLite (Postgres-only) do to each
distribution channel. Read-only inventory, 2026-05-30.

Sources read:
- `backend/app/cli.py` (the `openestimate` CLI: serve / init-db / doctor / seed)
- `backend/README.md` (the pip quickstart promise)
- `desktop/build-sidecar.sh`, `desktop/pyinstaller.spec`
- `desktop/src-tauri/src/main.rs`, `desktop/src-tauri/tauri.conf.json`
- `.github/workflows/desktop-release.yml`
- `docs/postgres-migration/PLAN.md` (existing migration plan)

## The headline promise (verbatim)

`backend/README.md` lines 12-22:

> ```bash
> pip install openconstructionerp
> openestimate init-db      # one-time: creates ~/.openestimate/ + SQLite DB
> openestimate serve        # http://127.0.0.1:8080
> ```
> That is the entire happy path. **No Docker, no Postgres, no Redis, no Node** -
> the wheel bundles the compiled React UI and falls back to SQLite, in-memory
> caching, and a local filesystem object store.

So "no Postgres" is an explicit, written, top-of-README selling point. PG-only
directly contradicts the headline.

## How each channel gets its DB today

### pip / CLI self-host
- `cli.py:_setup_env()` (lines 175-203) hard-defaults via `setdefault`:
  - `DATABASE_URL = sqlite+aiosqlite:///<data_dir>/openestimate.db`
  - `DATABASE_SYNC_URL = sqlite:///<data_dir>/openestimate.db`
  - data_dir defaults to `~/.openestimate` (line 51).
- `init-db` (`cmd_init_db`, lines 625-776) creates the SQLite file, imports 43
  module models, runs `sqlite_auto_migrate` + `Base.metadata.create_all`. There
  is literally a SQLite-specific migrator (`app.core.sqlite_migrator`).
- `serve` preflight (`check_env_overrides`, lines 325-337) treats SQLite as the
  default "OK" state and only notes "PostgreSQL mode" if a URL override is set.
  Nothing checks that a Postgres server is reachable before boot.
- First-run UX (`main()`, lines 1112-1145): bare `openestimate` detects first
  run by `~/.openestimate/openestimate.db` existence, prints welcome, offers to
  open the browser, then serves. The whole first-run heuristic is built around a
  local DB file.

### Tauri desktop
- `tauri.conf.json` declares a `sidecar` bundle. `main.rs` (lines 76-102) spawns
  the sidecar `openestimate-server --host 127.0.0.1 --port <picked>`, waits for
  `/api/health`, then points the webview at it.
- The sidecar IS the CLI: `pyinstaller.spec` entry point is
  `backend/app/cli.py` (line 84), bundles `aiosqlite` as a hidden import
  (line 26), and `desktop-release.yml` release notes say
  "All data is stored locally in `~/.openestimate/`" (line 149).
- So the desktop app inherits the exact SQLite defaults from `_setup_env`. There
  is no DB server in the bundle, no Docker, no service. The .exe/.dmg/.AppImage
  is self-contained.
- Note `excludes` in pyinstaller.spec (lines 92-100) drop numpy/pandas/scipy/
  torch to keep the binary small — the desktop build is deliberately lean.

### demo / eval
- The live VPS demo runs SQLite too (per PLAN.md line 26: systemd sets 4-slash
  absolute SQLite URLs). `docker compose up` brings up the *full* prod stack
  (Postgres+Redis+MinIO+Qdrant) per backend/README "Docker" section — that is
  the heavy path, not the eval path.

## Embedded-Postgres feasibility (option c)

- No embedded-postgres machinery exists in the tree today (no `pg_ctl`,
  `initdb`, or postgresql-binaries references under `backend/app`).
- Embedding would mean shipping platform-specific Postgres server binaries
  (~30-50 MB per OS/arch) inside the wheel and inside the PyInstaller sidecar,
  plus first-run `initdb` + a managed `pg_ctl start/stop` lifecycle, port
  management, data-dir cluster init, and clean shutdown on Ctrl+C / app quit.
  Libraries like `postgresql-binaries` / `pg8000`-adjacent embedded wrappers
  exist but are not pure-Python and complicate the cross-platform wheel.
- For pip this breaks the "pure-Python wheel, works on a 2GB VPS" property and
  bloats the download. For Tauri it is more plausible (the app is already a
  platform-specific native binary) but adds real lifecycle complexity and binary
  size, and the desktop build currently goes out of its way to stay lean.

## Verdict per channel

| Channel | PG-only verdict | Why |
|---|---|---|
| pip / CLI self-host | PAINFUL → near-dealbreaker | Kills the 3-command happy path and the written "no Postgres" promise. Requires user-provided PG before first launch. |
| pip / desktop-CLI sidecar | (same as pip) | The sidecar is the CLI; same SQLite defaults, same breakage. |
| Tauri desktop | DEALBREAKER (unless embedded PG) | An end-user .exe/.dmg cannot ask a non-technical user to install/run Postgres. SQLite is the only realistic option; embedded-PG is the only PG-shaped alternative and is heavy/complex. |
| demo / eval | PAINFUL | Today SQLite-on-VPS or `docker compose up`. PG-only means every evaluator needs Docker or a managed PG — Docker is explicitly NOT a default requirement. |

## Bottom line

Keep SQLite as the zero-config default for pip + desktop + eval; make Postgres
an opt-in production backend selected by `DATABASE_URL`. This is exactly what
PLAN.md already recommends. Making PG mandatory everywhere would break the
single strongest distribution advantage the product has (one command, no
infra), and is a hard blocker for the Tauri desktop channel specifically.

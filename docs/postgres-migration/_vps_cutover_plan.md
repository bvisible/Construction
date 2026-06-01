# VPS PostgreSQL Cutover — Execution Steps

OpenConstructionERP — migrate the **hosted VPS demo** from SQLite to a **dedicated,
self-hosted PostgreSQL 16 docker container** (`oe-postgres`, named volume `oe_pgdata`,
host port **5433**, bound to **127.0.0.1 only**).

> **PostgreSQL is OPT-IN.** The pip-install / `docker compose up` default stays
> **SQLite** (`sqlite+aiosqlite:///./openestimate.db`). This runbook applies ONLY to
> the hosted demo at `root@31.97.123.81`. Do not change the documented default for
> self-hosters.

Target facts (treated as authoritative):

| Thing | Value |
|---|---|
| Host | `root@31.97.123.81` |
| Repo | `/root/OpenConstructionERP` |
| venv | `/root/OpenConstructionERP/venv/` (NOT `.venv`) |
| systemd unit | `openconstructionerp` (serves port **9090**) |
| Current DB | `/root/OpenConstructionERP/data/openestimate.db` (SQLite) |
| Frontend served from | `backend/app/_frontend_dist` |
| Health endpoint | `http://localhost:9090/api/health` (NOT `/api/v1/health`) |
| New PG container | `oe-postgres`, image `postgres:16`, volume `oe_pgdata`, `127.0.0.1:5433:5432` |

**Do NOT touch / reuse / prune** the other docker stacks on this box: the **n8n** stack,
the **conference-chat** stack (caddy / nocodb / qdrant / 2× postgres), and **dokufluss**.
OCERP gets its OWN postgres on its OWN port (5433). Never prune named volumes of other
stacks. Only `docker builder prune` (build cache) and `docker volume prune` of *dangling*
volumes are safe — and only run those if disk is tight AND you have verified they are not
in use.

> Run interactively, one block at a time. Each block has a checkpoint — STOP and
> investigate if a checkpoint is wrong. The SQLite file is never deleted, so rollback
> (section 8) is one env change away.

---

## ⚠️ VERIFY ON VPS (could not be determined from local repo files)

These are unknowns I could not resolve from the local repo. Resolve each on the box
*before* running the matching step. They are the only places this runbook makes an
assumption.

1. **systemd env mechanism (Step 0 / Step 5).** I cannot see the VPS unit file locally.
   Run `systemctl cat openconstructionerp` and check whether it uses
   `EnvironmentFile=/path/...`, inline `Environment=...` lines, or neither. Step 5 gives
   both an `EnvironmentFile` recipe and a `systemctl edit` drop-in recipe — pick the one
   that matches what you find. If an `EnvironmentFile` already exists, edit that file (do
   not also add a drop-in; an inline `Environment=` in a drop-in would shadow it and cause
   confusion).
2. **Whether the venv already has the PG drivers (Step 0 / Step 2).** `asyncpg` and
   `psycopg2-binary` are declared in `backend/pyproject.toml` but only under the
   `[server]` optional-extra — a plain `pip install openconstructionerp` (or
   `pip install -e .`) does NOT pull them. Run the `pip show` check in Step 0; install in
   Step 2 only if missing.
3. **Whether host port 5433 (and 5432) is actually free (Step 0 / Step 1).** Other stacks
   run their own postgres. 5433 is the *recommendation* to dodge a likely-occupied 5432.
   Confirm with the `ss -ltnp` check in Step 0; if 5433 is also taken, bump to 5434+ and
   substitute that port consistently in every command below.
4. **Disk headroom.** PG container image (~150 MB) + a full copy of the data (~the size of
   `openestimate.db`, held once on the PG side) must fit. Confirm `df -h` in Step 0.
5. **Exact JWT/env already set.** The app refuses to boot in non-development with a weak
   `JWT_SECRET`. Whatever env currently makes the SQLite service boot must be preserved —
   only ADD/CHANGE the two `DATABASE_*` vars, never drop existing ones. Capture the
   current env in Step 0 so you can diff.
6. **Row/table counts.** Expected magnitudes (table count, row count) are not knowable
   from local files. Run a `--dry-run` first (Step 4a) and treat ITS numbers as the
   baseline the real run must reproduce.

---

## 0. Pre-flight (read-only — safe to run anytime)

```bash
ssh root@31.97.123.81

# --- which ports in the 5430-5439 range are already bound, and by what? ---
ss -ltnp | grep -E '543[0-9]' || echo "no listener on 5430-5439"

# --- existing docker stacks (DO NOT TOUCH n8n / conference-chat / dokufluss) ---
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}'
docker volume ls          # note the existing named volumes — none of these get pruned

# --- disk headroom (need image + one full copy of the DB) ---
df -h /
ls -lh /root/OpenConstructionERP/data/openestimate.db

# --- are the PG drivers already in the venv? ---
source /root/OpenConstructionERP/venv/bin/activate
pip show asyncpg psycopg2-binary || echo "one or both drivers MISSING — do Step 2"
python -c "import sys; print(sys.executable)"   # confirm it's the venv python
deactivate

# --- dump the current systemd environment so we can diff after the change ---
systemctl show openconstructionerp -p Environment
systemctl cat openconstructionerp | grep -iE "EnvironmentFile|Environment="
#   ^ if you see `EnvironmentFile=/some/path`, record that path — Step 5 edits it.
#     if you only see inline `Environment=` lines, use the `systemctl edit` drop-in.

# --- live health BEFORE we touch anything (baseline version + module count) ---
curl -s http://localhost:9090/api/health | python3 -m json.tool
```

**Checkpoint:**
- Note which 543x ports are free. If **5433** is taken, choose the next free port and
  substitute it everywhere below.
- Confirm `oe-postgres` is NOT already a container name (`docker ps -a | grep oe-postgres`).
- Record whether the drivers are present (decides Step 2).
- Record the env mechanism (`EnvironmentFile` path, or inline) — decides Step 5.
- Record baseline `/api/health` (version, `database`, `alembic_head_matches`, module count).

---

## 1. Provision the dedicated PostgreSQL container

```bash
docker run -d \
  --name oe-postgres \
  --restart unless-stopped \
  -e POSTGRES_USER=oe \
  -e POSTGRES_PASSWORD='<PG_PASSWORD>' \
  -e POSTGRES_DB=openestimate \
  -p 127.0.0.1:5433:5432 \
  -v oe_pgdata:/var/lib/postgresql/data \
  postgres:16
```

Why these choices:
- **`-p 127.0.0.1:5433:5432`** — publishes the container's 5432 only on the host
  loopback. The app talks to it over `localhost`, and it is NEVER reachable from the
  public internet (no firewall rule needed, no exposure even if ufw is loose). The host
  port is **5433** so it cannot collide with any other stack's postgres already on 5432.
- **`--name oe-postgres` + `-v oe_pgdata:...`** — a clearly-owned container and a clearly
  named volume, so it is obvious this belongs to OCERP and must not be confused with the
  conference-chat / n8n / dokufluss postgres data.
- **`--restart unless-stopped`** — comes back after a reboot, but a deliberate
  `docker stop` stays stopped.

Wait for it to accept connections, then verify:

```bash
# wait until ready (Postgres runs initdb on first boot — a few seconds)
until docker exec oe-postgres pg_isready -U oe -d openestimate; do sleep 1; done

# confirm the role + db exist and we can authenticate over the published port
docker exec -e PGPASSWORD='<PG_PASSWORD>' oe-postgres \
  psql -U oe -d openestimate -c '\conninfo'

# confirm the host port is bound on loopback only
ss -ltnp | grep ':5433'
```

**Checkpoint:** `pg_isready` reports `accepting connections`; `\conninfo` shows connected
as `oe` to `openestimate`; `ss` shows `127.0.0.1:5433` (NOT `0.0.0.0:5433`).

> Collation note: the container defaults to the image locale (typically `en_US.utf8` /
> `C.UTF-8`). The app does all case-insensitive search via `ILIKE` /
> `func.lower(...).like(...)`, so the default collation is fine — no special initdb args
> needed.

---

## 2. Install the PG drivers into the venv (only if Step 0 said MISSING)

The app's async engine needs **asyncpg** (for `DATABASE_URL=postgresql+asyncpg://...`),
and the migration script + `alembic stamp` need **psycopg2** (for the
`postgresql+psycopg2://...` sync URL). Both are declared in `backend/pyproject.toml` under
the `[server]` extra but are not in the base install.

```bash
source /root/OpenConstructionERP/venv/bin/activate

# Option A — exact pins matching pyproject [server]:
pip install "asyncpg>=0.30.0" "psycopg2-binary>=2.9.10"

# Option B (equivalent) — install the declared extra from the repo:
#   pip install -e "/root/OpenConstructionERP/backend[server]"

pip show asyncpg psycopg2-binary | grep -E '^(Name|Version):'
deactivate
```

**Checkpoint:** both `asyncpg` and `psycopg2-binary` print a Name+Version.

---

## 3. Stop the app for a consistent snapshot + back up SQLite

Stopping the service guarantees the SQLite file is quiescent (no in-flight writes) while
we copy it. The backup is the rollback source of truth.

```bash
systemctl stop openconstructionerp
systemctl is-active openconstructionerp || echo "stopped (expected)"

# timestamped backup of the live DB (and the WAL/SHM sidecars if present)
cp -av /root/OpenConstructionERP/data/openestimate.db \
       /root/OpenConstructionERP/data/openestimate.db.bak-$(date +%Y%m%d-%H%M%S)
# (WAL mode sidecars — harmless if they don't exist)
cp -av /root/OpenConstructionERP/data/openestimate.db-wal \
       /root/OpenConstructionERP/data/openestimate.db-wal.bak-$(date +%Y%m%d-%H%M%S) 2>/dev/null || true
cp -av /root/OpenConstructionERP/data/openestimate.db-shm \
       /root/OpenConstructionERP/data/openestimate.db-shm.bak-$(date +%Y%m%d-%H%M%S) 2>/dev/null || true

ls -lh /root/OpenConstructionERP/data/openestimate.db*
```

**Checkpoint:** a `openestimate.db.bak-<timestamp>` exists with the same size as the live
DB, and the service is stopped.

---

## 4. Migrate the data SQLite → PostgreSQL

The script (`backend/app/scripts/migrate_sqlite_to_postgres.py`) imports every module's
models, builds the target schema with `Base.metadata.create_all` (so the JSON→JSONB
`@compiles` hook AND the FK/composite/GIN performance indexes fire exactly like a fresh
install), then copies every table in FK order, batched, with per-row fault isolation and
retry passes for self-referential FKs.

**Exact CLI** (confirmed from source): `--source`, `--target`, `--truncate`, `--dry-run`,
`--batch-size` (default 1000). There is **no `--only` and no `--skip-create`** flag — the
schema is always created. The script auto-coerces async URLs to sync
(`postgresql+asyncpg`→`postgresql+psycopg2`, `sqlite+aiosqlite`→`sqlite`), so either form
works for `--target`; the `postgresql+psycopg2://` form below is explicit.

Run from `backend/` with the venv active.

```bash
cd /root/OpenConstructionERP/backend
source ../venv/bin/activate
```

### 4a. DRY RUN first — counts only, never writes

```bash
python -m app.scripts.migrate_sqlite_to_postgres \
  --source "sqlite:////root/OpenConstructionERP/data/openestimate.db" \
  --target "postgresql+psycopg2://oe:<PG_PASSWORD>@localhost:5433/openestimate" \
  --dry-run
```

**Checkpoint:** prints `model discovery: imported N module model packages; T tables
registered`, then `tables in metadata: T; total source rows: R`. Record **T** and **R** —
these are your baseline. (Note the FOUR slashes in the sqlite source URL — absolute path.)

### 4b. REAL migration into the fresh (empty) PG database

`--truncate` is a no-op on the empty target but keep it so a re-run is idempotent (it
empties the target in reverse-FK order before copying).

```bash
python -m app.scripts.migrate_sqlite_to_postgres \
  --source "sqlite:////root/OpenConstructionERP/data/openestimate.db" \
  --target "postgresql+psycopg2://oe:<PG_PASSWORD>@localhost:5433/openestimate" \
  --truncate
```

**Checkpoint:** ends with `total rows copied: <N>; rows skipped: 0` and
`migration finished cleanly.` (exit 0). A handful of skipped rows is tolerable but READ
the per-table skip warnings on stderr first — `<N>` copied should be close to the
dry-run's `R`.

### 4c. Spot-check counts + JSONB round-trip

```bash
# PG side (through the published port)
docker exec -e PGPASSWORD='<PG_PASSWORD>' oe-postgres \
  psql -U oe -d openestimate -c \
  "SELECT (SELECT count(*) FROM oe_users_user) AS users,
          (SELECT count(*) FROM oe_projects_project) AS projects;"

# SQLite side (must match) — sqlite3 may need apt install sqlite3 if absent
sqlite3 /root/OpenConstructionERP/data/openestimate.db \
  "SELECT (SELECT count(*) FROM oe_users_user),(SELECT count(*) FROM oe_projects_project);"

# confirm a JSON column actually landed as JSONB (proves the @compiles hook fired)
docker exec -e PGPASSWORD='<PG_PASSWORD>' oe-postgres \
  psql -U oe -d openestimate -c \
  "SELECT data_type FROM information_schema.columns
    WHERE column_name='classification' LIMIT 1;"   # expect: jsonb
```

**Checkpoint:** user/project counts match between PG and SQLite; the JSON column reports
`jsonb`.

```bash
deactivate
```

---

## 5. Point the app at PostgreSQL (systemd env)

Set BOTH URLs (async for the app runtime, sync for alembic/stamp). The setting names are
`DATABASE_URL` and `DATABASE_SYNC_URL` (case-insensitive; the `OE_` prefix also works —
e.g. `OE_DATABASE_URL`). Use whichever mechanism Step 0 revealed.

```
DATABASE_URL=postgresql+asyncpg://oe:<PG_PASSWORD>@localhost:5433/openestimate
DATABASE_SYNC_URL=postgresql+psycopg2://oe:<PG_PASSWORD>@localhost:5433/openestimate
```

> If `<PG_PASSWORD>` contains any of `@ : / ? # & %`, URL-encode those characters in BOTH
> URLs (e.g. `@` → `%40`). Easiest path: pick a password from `[A-Za-z0-9_]` so no
> encoding is needed.

### Option A — EnvironmentFile (use if Step 0 showed `EnvironmentFile=/path`)

Edit that exact file (do not invent a new path):

```bash
# back it up first
cp -av <ENV_FILE_PATH> <ENV_FILE_PATH>.bak-$(date +%Y%m%d-%H%M%S)

# then edit it (nano/vi) and set/replace the two lines:
#   DATABASE_URL=postgresql+asyncpg://oe:<PG_PASSWORD>@localhost:5433/openestimate
#   DATABASE_SYNC_URL=postgresql+psycopg2://oe:<PG_PASSWORD>@localhost:5433/openestimate
# Leave every OTHER line (JWT_SECRET, APP_ENV, etc.) untouched.

systemctl daemon-reload
```

### Option B — `systemctl edit` drop-in (use if there is NO EnvironmentFile)

```bash
systemctl edit openconstructionerp
# In the editor that opens, add EXACTLY this block (between the marker comments):

# [Service]
# Environment="DATABASE_URL=postgresql+asyncpg://oe:<PG_PASSWORD>@localhost:5433/openestimate"
# Environment="DATABASE_SYNC_URL=postgresql+psycopg2://oe:<PG_PASSWORD>@localhost:5433/openestimate"

# (uncomment the three lines above; quotes are required because URLs contain special chars)
systemctl daemon-reload
```

> Do NOT mix A and B. A drop-in `Environment=` overrides an `EnvironmentFile` value for
> the same key, which is confusing. If an EnvironmentFile exists, edit it (Option A).

**Checkpoint (before restart):** `systemctl show openconstructionerp -p Environment`
either now lists the PG URLs (Option B) or the EnvironmentFile content is correct (Option
A — it won't show in `show -p Environment` until the next start).

---

## 6. Stamp alembic head against PostgreSQL

The schema was built by `create_all` (NOT the migration chain), so we **stamp** head
rather than running the full upgrade chain — that keeps
`/api/health.alembic_head_matches` true without replaying 3000+ migrations against PG.

```bash
cd /root/OpenConstructionERP/backend
source ../venv/bin/activate

DATABASE_SYNC_URL="postgresql+psycopg2://oe:<PG_PASSWORD>@localhost:5433/openestimate" \
  alembic stamp head

# verify the alembic_version row now points at the head revision
docker exec -e PGPASSWORD='<PG_PASSWORD>' oe-postgres \
  psql -U oe -d openestimate -c "SELECT version_num FROM alembic_version;"
deactivate
```

**Checkpoint:** `alembic stamp head` succeeds and `alembic_version` holds exactly one row
with the head revision. (If `alembic stamp` complains the table is missing, the app's
fresh-DB boot also stamps it — but stamping explicitly here is the deterministic path.)

---

## 7. Start the app + verify

```bash
systemctl start openconstructionerp
systemctl status openconstructionerp --no-pager | head -20

# health — expect database=ok, alembic_head_matches=true, module count ~117
curl -s http://localhost:9090/api/health | python3 -m json.tool
```

**Checkpoint `/api/health`:**
- `database` = `ok`
- `alembic_head_matches` = `true`
- `version` = `5.9.2` (or whatever the deployed source reports)
- module count ≈ 117 (matches the Step 0 baseline)

Then a **sequential** smoke (NEVER parallel against the shared demo box — concurrent
Playwright/probe runs stall the event loop):

```bash
# 1) health again (idempotent)
curl -s http://localhost:9090/api/health | python3 -m json.tool | grep -E 'database|alembic'

# 2) a real login → token (demo creds: note the 'r' in openestimator.io)
TOKEN=$(curl -s -X POST http://localhost:9090/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"demo@openestimator.io","password":"<DEMO_PASSWORD>"}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin).get("access_token",""))')
echo "token len: ${#TOKEN}"

# 3) one read endpoint with the token (projects list)
curl -s http://localhost:9090/api/v1/projects/ -H "Authorization: Bearer $TOKEN" \
  | python3 -c 'import sys,json;d=json.load(sys.stdin);print("projects:",len(d.get("items",d) if isinstance(d,dict) else d))'

# 4) a second read endpoint (costs or boqs) — run AFTER 3 returns, not in parallel
curl -s http://localhost:9090/api/v1/costs/ -H "Authorization: Bearer $TOKEN" -o /dev/null -w "costs HTTP %{http_code}\n"
```

**Checkpoint:** login returns a non-empty token; both read endpoints return 200 with data
(not 500). Then do a quick browser pass (login + open Dashboard, Projects, one BOQ) —
sequentially, one tab.

> If frontend chunks 404 after a deploy, re-sync `_frontend_dist` from the built
> `frontend/dist` (the wheel-shadow gotcha) — unrelated to the DB cutover but worth
> knowing.

---

## 8. ROLLBACK (if anything in Steps 6–7 fails)

The SQLite DB is untouched and backed up. Reverting is just an env change + restart. Leave
`oe-postgres` running but unused — no need to delete it; you can retry the cutover later.

### Option A — you used an EnvironmentFile

```bash
systemctl stop openconstructionerp
# restore the pre-cutover env file from the backup you made in Step 5:
cp -av <ENV_FILE_PATH>.bak-<timestamp> <ENV_FILE_PATH>
systemctl daemon-reload
systemctl start openconstructionerp
```

### Option B — you used a `systemctl edit` drop-in

```bash
systemctl revert openconstructionerp     # removes the drop-in, restores stock unit
systemctl daemon-reload
systemctl restart openconstructionerp
```

If the stock unit does not itself set the SQLite URLs (i.e. the app's built-in defaults
must apply), the defaults are already SQLite:
`DATABASE_URL=sqlite+aiosqlite:///./openestimate.db`,
`DATABASE_SYNC_URL=sqlite:///./openestimate.db`. If you need them explicit (e.g. the unit
runs with a different CWD), set the 4-slash absolute forms instead:

```
DATABASE_URL=sqlite+aiosqlite:////root/OpenConstructionERP/data/openestimate.db
DATABASE_SYNC_URL=sqlite:////root/OpenConstructionERP/data/openestimate.db
```

Verify the rollback:

```bash
curl -s http://localhost:9090/api/health | python3 -m json.tool   # database=ok, back on SQLite
```

**Checkpoint:** `/api/health` is `database=ok` again and the app behaves as before. The
SQLite `.bak-<timestamp>` file remains the canonical pre-cutover snapshot — keep it for at
least a week after a successful cutover before considering it disposable.

---

## Appendix — optional PG tuning + backups (after a clean cutover)

These run against the container; adjust to the VPS RAM. Not required for correctness.

```bash
# modest tuning for a small shared VPS (example — tune to actual RAM)
docker exec oe-postgres psql -U oe -d postgres -c "ALTER SYSTEM SET shared_buffers='512MB';"
docker exec oe-postgres psql -U oe -d postgres -c "ALTER SYSTEM SET effective_cache_size='1536MB';"
docker exec oe-postgres psql -U oe -d postgres -c "ALTER SYSTEM SET work_mem='16MB';"
docker exec oe-postgres psql -U oe -d postgres -c "ALTER SYSTEM SET maintenance_work_mem='128MB';"
docker restart oe-postgres && systemctl restart openconstructionerp

# nightly logical backup of the OCERP db ONLY (never dumps other stacks' DBs)
mkdir -p /root/backups/oe
cat >/etc/cron.d/oe-pgdump <<'CRON'
0 3 * * * root docker exec -e PGPASSWORD='<PG_PASSWORD>' oe-postgres pg_dump -U oe openestimate | gzip > /root/backups/oe/oe_$(date +\%F).sql.gz
CRON
```

Note: the app's `database_pool_recycle` defaults to 1800s and `pool_pre_ping` is enabled
automatically for non-SQLite URLs (see `app/database.py`), so the pool self-heals if
`oe-postgres` restarts — no app config needed.

# VPS PostgreSQL Cutover Runbook

OpenConstructionERP — migrate the live VPS from SQLite to self-hosted PostgreSQL 16.
Target host: `root@31.97.123.81`. Systemd unit: `openconstructionerp` (port 9090).
Repo: `/root/OpenConstructionERP`. venv: `/root/OpenConstructionERP/venv/` (NOT `.venv`).
Current SQLite DB: `/root/OpenConstructionERP/data/openestimate.db`.

> Run interactively, one block at a time. Each block prints a checkpoint. STOP and
> investigate if any checkpoint is wrong. There is a full rollback at the end — the
> SQLite DB is never deleted, only left in place, so reverting is one env change away.

---

## 0. Pre-flight (read-only — safe to run anytime)

```bash
ssh root@31.97.123.81
# disk headroom (PG + a full data copy needs a few GB)
df -h /
# is postgres already present?
which psql && psql --version || echo "psql NOT installed"
# current DB size (the copy target must hold roughly this much, twice during migration)
ls -lh /root/OpenConstructionERP/data/openestimate.db
# live version + health BEFORE we touch anything
curl -s http://localhost:9090/api/health | python3 -m json.tool | head -30
# memory
free -h
```

Checkpoint: note free disk GB and DB size. If `/` has < ~3× the DB size free, do step 1a first.

### 1a. (only if disk tight) reclaim space — CPU-only torch

Memory note: ~6 GB of unused CUDA torch wheels live in the venv (the box is CPU-only).
Swapping to CPU torch recovers headroom. Do this carefully and test after.

```bash
source /root/OpenConstructionERP/venv/bin/activate
du -sh "$(python -c 'import torch,os;print(os.path.dirname(torch.__file__))')" 2>/dev/null || echo "no torch"
# Only if torch is present AND large AND confirmed unused by a running feature:
pip uninstall -y torch && pip install --index-url https://download.pytorch.org/whl/cpu torch
df -h /
```

---

## 1. Install PostgreSQL 16

```bash
apt-get update
apt-get install -y postgresql-16 postgresql-client-16
systemctl enable --now postgresql
pg_lsclusters                # expect a 16 main cluster, online, port 5432
```

Checkpoint: `pg_lsclusters` shows `16 main ... online`.

---

## 2. Create database + role

Choose a strong password and keep it; it goes into the app env in step 5.

```bash
PGPASS='REPLACE_WITH_A_STRONG_PASSWORD'
sudo -u postgres psql <<SQL
CREATE ROLE oe LOGIN PASSWORD '${PGPASS}';
CREATE DATABASE openestimate OWNER oe ENCODING 'UTF8' LC_COLLATE 'C' LC_CTYPE 'C' TEMPLATE template0;
GRANT ALL PRIVILEGES ON DATABASE openestimate TO oe;
SQL
# sanity: connect as the app role
PGPASSWORD="${PGPASS}" psql -h localhost -U oe -d openestimate -c '\conninfo'
```

Checkpoint: `\conninfo` reports connected as `oe` to `openestimate`.

> Note on collation: `LC_COLLATE 'C'` makes plain `LIKE` byte-ordered and fast. All
> case-insensitive search in the app already uses `ILIKE` / `func.lower(...).like(...)`,
> so `C` collation is safe and gives deterministic ordering.

---

## 3. Pull the new release + install deps (PG drivers)

```bash
cd /root/OpenConstructionERP
git fetch origin && git checkout main && git pull --ff-only
source venv/bin/activate
# async + sync PG drivers (asyncpg for the app, psycopg2 for alembic + migration script)
pip install "asyncpg>=0.29" "psycopg2-binary>=2.9"
# make sure the wheel/source frontend dist is in sync (see VPS gotcha memory)
python -c "import app.main" && echo "IMPORT_OK"
```

Checkpoint: `IMPORT_OK`. (If frontend chunks 404 later, re-sync `_frontend_dist` — see
`feedback_vps_wheel_shadowed`.)

---

## 4. Migrate the data SQLite → PostgreSQL

The script builds the target schema via `Base.metadata.create_all` (so JSONB columns +
FK/GIN/composite indexes from `performance_indexes.py` are emitted), then copies every
table in FK order, batched, idempotent, with per-row skip-safety.

```bash
cd /root/OpenConstructionERP/backend
source ../venv/bin/activate

# 4a. DRY RUN first — must report 432 tables and a positive total, NO writes
python -m app.scripts.migrate_sqlite_to_postgres \
  --source "sqlite:////root/OpenConstructionERP/data/openestimate.db" \
  --target "postgresql+psycopg2://oe:${PGPASS}@localhost/openestimate" \
  --dry-run

# 4b. REAL migration into the empty PG db (--truncate is a no-op on an empty target,
#     but keep it so a re-run is safe/idempotent)
python -m app.scripts.migrate_sqlite_to_postgres \
  --source "sqlite:////root/OpenConstructionERP/data/openestimate.db" \
  --target "postgresql+psycopg2://oe:${PGPASS}@localhost/openestimate" \
  --truncate
```

Note the FOUR slashes in the sqlite source URL (absolute path) — see
`feedback_alembic_wrong_db`.

Checkpoint: final summary prints `tables ok` ≈ 432, `rows copied` ≈ 387k (matches the
dev baseline order of magnitude), `tables failed = 0`, `rows skipped = 0` (a handful of
skips is acceptable — read them). Spot-check a couple of counts:

```bash
PGPASSWORD="${PGPASS}" psql -h localhost -U oe -d openestimate -c \
  "SELECT count(*) FROM oe_users_user; SELECT count(*) FROM oe_projects_project;"
# compare to SQLite
sqlite3 /root/OpenConstructionERP/data/openestimate.db \
  "SELECT count(*) FROM oe_users_user; SELECT count(*) FROM oe_projects_project;"
```

Counts must match. Also verify a JSONB column round-trips:

```bash
PGPASSWORD="${PGPASS}" psql -h localhost -U oe -d openestimate -c \
  "SELECT pg_typeof(asset_info) FROM oe_bim_element LIMIT 1;"   # expect jsonb
```

---

## 5. Point the app at PostgreSQL

Edit the systemd unit's environment (or the env file it references — check
`systemctl cat openconstructionerp` for `EnvironmentFile=`).

```bash
systemctl cat openconstructionerp | grep -iE "Environment|EnvironmentFile"
```

Set BOTH URLs (async for the app, sync for alembic/stamp):

```
DATABASE_URL=postgresql+asyncpg://oe:PGPASS@localhost/openestimate
DATABASE_SYNC_URL=postgresql+psycopg2://oe:PGPASS@localhost/openestimate
```

(Replace `PGPASS`. URL-encode the password if it contains `@ : / ?`.)

---

## 6. Stamp alembic + restart

The schema was created via `create_all` (not the migration chain), so stamp head to keep
`/api/health.alembic_head_matches` true. env.py's fresh-blank-DB shortcut handles this on
boot, but stamping explicitly is deterministic:

```bash
cd /root/OpenConstructionERP/backend
source ../venv/bin/activate
DATABASE_SYNC_URL="postgresql+psycopg2://oe:${PGPASS}@localhost/openestimate" \
  alembic stamp head
systemctl restart openconstructionerp
sleep 4
curl -s http://localhost:9090/api/health | python3 -m json.tool
```

Checkpoint `/api/health`:
- `version` = 5.9.2
- `database` = ok
- `alembic_head_matches` = true
- module count ≈ 117

Then a real login + a couple of list endpoints through the browser (sequential, per
`feedback_prod_probe_sequential`).

---

## 7. Post-cutover

```bash
# basic PG tuning for a small VPS (adjust to RAM; example for ~4–8 GB)
sudo -u postgres psql -c "ALTER SYSTEM SET shared_buffers='1GB';"
sudo -u postgres psql -c "ALTER SYSTEM SET effective_cache_size='3GB';"
sudo -u postgres psql -c "ALTER SYSTEM SET work_mem='32MB';"
sudo -u postgres psql -c "ALTER SYSTEM SET maintenance_work_mem='256MB';"
sudo -u postgres psql -c "ALTER SYSTEM SET max_connections='100';"
systemctl restart postgresql && systemctl restart openconstructionerp
# nightly logical backup
echo '0 3 * * * postgres pg_dump openestimate | gzip > /root/backups/oe_$(date +\%F).sql.gz' \
  >> /etc/crontab
```

Keep `data/openestimate.db` in place for at least a week as the rollback anchor.

---

## ROLLBACK (if anything in step 6 fails)

The SQLite DB is untouched. Revert the two env vars and restart:

```
DATABASE_URL=sqlite+aiosqlite:////root/OpenConstructionERP/data/openestimate.db
# remove DATABASE_SYNC_URL override (or set the sqlite 4-slash form)
```
```bash
systemctl restart openconstructionerp
curl -s http://localhost:9090/api/health | python3 -m json.tool   # back to SQLite, version 5.9.2
```

The app is back on SQLite in seconds. Diagnose PG offline, then retry the cutover.

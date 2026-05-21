# OpenConstructionERP Production Runbook

Operational playbook for the `openconstructionerp` service running on the
shared demo VPS. Optimised for fast incident response — every command in
this file is copy-pasteable.

## Service basics

- **Host**: `root@31.97.123.81`
- **systemd unit**: `openconstructionerp`
- **Python venv**: `/root/OpenConstructionERP/venv`
- **venv pip**: `/root/OpenConstructionERP/venv/bin/pip` (never use system pip)
- **Port**: `9090` (bound by uvicorn inside the service)
- **Working dir**: `/root/OpenConstructionERP`
- **Boot time**: ~3-4 minutes (71+ modules + Qdrant ping + BOQ backfill
  before port binds — be patient, do not assume it failed before 4 min).

## Common operations

```bash
# Restart the service
systemctl restart openconstructionerp

# Tail live logs
journalctl -u openconstructionerp -f

# Last 200 lines (post-mortem)
journalctl -u openconstructionerp -n 200 --no-pager

# Health probe (also reports alembic head match + frontend dist presence)
curl -fsS http://localhost:9090/api/health | jq

# Correlate logs to a specific user-reported request
curl -fsS -H "X-Request-ID: my-trace-42" http://localhost:9090/api/health
journalctl -u openconstructionerp --since "5 min ago" | grep my-trace-42

# Slow-query offenders (logger name: slow_queries)
journalctl -u openconstructionerp --since today | grep slow_queries
```

## Deploy procedure

```bash
# 1. Upload the new wheel + source tar from local
scp dist/openconstructionerp-X.Y.Z-py3-none-any.whl root@31.97.123.81:/tmp/
scp dist/source-X.Y.Z.tar.gz root@31.97.123.81:/tmp/

# 2. On the VPS — install wheel
/root/OpenConstructionERP/venv/bin/pip install --force-reinstall \
    /tmp/openconstructionerp-X.Y.Z-py3-none-any.whl

# 3. Untar source over the install (backend source shadows wheel — see
#    "VPS wheel shadowed by source" in MEMORY.md)
cd /root/OpenConstructionERP
tar xzf /tmp/source-X.Y.Z.tar.gz

# 4. Sync the frontend dist directory (chunk filenames change every build)
rsync -a --delete backend/app/_frontend_dist/ \
    /root/OpenConstructionERP/venv/lib/python3.12/site-packages/app/_frontend_dist/

# 5. Run migrations (see Alembic gotcha below) and restart
DATABASE_SYNC_URL=sqlite:////root/OpenConstructionERP/data/openestimate.db \
    /root/OpenConstructionERP/venv/bin/alembic upgrade head
systemctl restart openconstructionerp

# 6. Verify
curl -fsS http://localhost:9090/api/health | jq '.version, .status, .alembic_head_matches'
```

## DB backup / restore

The production DB is a single SQLite file:
`/root/OpenConstructionERP/data/openestimate.db`

```bash
# Backup (online, safe — SQLite locks the file briefly)
sqlite3 /root/OpenConstructionERP/data/openestimate.db \
    ".backup '/root/backups/oe-$(date +%F-%H%M).db'"

# Compress + ship offsite
gzip /root/backups/oe-*.db
# rsync /root/backups/ <offsite>:/...

# Restore — STOP THE SERVICE FIRST or you'll corrupt the WAL
systemctl stop openconstructionerp
cp /root/backups/oe-2026-05-21-0900.db \
    /root/OpenConstructionERP/data/openestimate.db
systemctl start openconstructionerp
```

## Alembic gotcha (read before running migrations)

The systemd unit injects `DATABASE_URL` (async) but `alembic` invoked from
a shell does NOT inherit it and falls back to the project default — a
RELATIVE `./openestimate.db` in the current working directory. Running
`alembic upgrade head` from `/root/OpenConstructionERP` will migrate
`/root/OpenConstructionERP/openestimate.db`, NOT the real prod DB at
`/root/OpenConstructionERP/data/openestimate.db`.

**Always** export the sync URL explicitly:

```bash
export DATABASE_SYNC_URL=sqlite:////root/OpenConstructionERP/data/openestimate.db
/root/OpenConstructionERP/venv/bin/alembic upgrade head
```

`alembic.ini` lives in `backend/alembic.ini`, not at the repo root.

## Rollback

```bash
# 1. Install the previous wheel (PyPI keeps every release)
/root/OpenConstructionERP/venv/bin/pip install --force-reinstall \
    openconstructionerp==<previous-version>

# 2. If the rollback crosses an alembic revision, downgrade explicitly:
DATABASE_SYNC_URL=sqlite:////root/OpenConstructionERP/data/openestimate.db \
    /root/OpenConstructionERP/venv/bin/alembic downgrade <revision>

# 3. Re-sync frontend dist from the previous source tar (chunks differ
#    per release — a v4.2.2 dist served by v4.2.1 backend = white screen)
tar xzf /tmp/source-<previous>.tar.gz -C /root/OpenConstructionERP/

# 4. Restart and verify
systemctl restart openconstructionerp
curl -fsS http://localhost:9090/api/health | jq '.version, .status'
```

## Common 500 causes

| Symptom | Likely cause | Fix |
|---|---|---|
| `/api/health` returns `alembic_head_matches: false` | Migrations not applied after deploy | See Alembic gotcha above |
| `/api/health` returns `frontend_dist_present: false` | `_frontend_dist` rsync skipped or wheel-only install | Re-run step 4 of the deploy procedure |
| Random 500s with `OperationalError: no such column` | Same root cause as `alembic_head_matches: false` | `alembic upgrade head` |
| `/match-elements` returns empty / 500 | Qdrant unreachable | Check `curl http://localhost:6333`; restart Qdrant; semantic search degrades to lexical |
| Boot stalls > 5 min | Embedding model first-time download | Watch `journalctl -f`; let it finish; cap with `OE_EMBEDDING_DOWNLOAD_TIMEOUT_SECONDS` |
| 500 with `decimal.InvalidOperation` in body | Client sent NaN/Infinity in JSON | Already rejected as 422 by `_RejectNonFiniteJSONMiddleware` |
| All requests hang | DB locked (SQLite) | Restart service; check for orphaned `*.db-wal` files |
| `journalctl` shows `slow_queries` storm | Genuinely slow query, N+1, or missing index | Capture the `statement` field; add index; raise `OE_SLOW_QUERY_MS` temporarily |

## Useful one-liners

```bash
# Which version is actually serving?
curl -fsS http://localhost:9090/api/health | jq -r '.version'

# Is the wheel still being shadowed by /root/OpenConstructionERP/backend/app?
python -c "import app; print(app.__file__)"

# Disk usage on /
df -h /

# Top 10 largest files under /root (catch runaway logs / pycache)
du -ah /root | sort -rh | head -10
```

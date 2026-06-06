# VPS and marketing-site deploy

# Dossier: Production VPS and Marketing-Site Deploy

Scope: the live production box at `root@31.97.123.81`, the PostgreSQL cutover that is still pending there, and how to safely ship marketing-site changes. Read this before touching anything on the box. All facts below were taken from files in the repo; where a fact could only come from the live host it is called out as "verify on box".

---

## 1. Live deploy facts (authoritative)

These are confirmed from `docs/postgres-migration/MASTER_PLAN_pg_embedded.md` (lines 56-70), `docs/postgres-migration/VPS_CUTOVER_RUNBOOK.md` (lines 3-6), `docs/postgres-migration/V6_HANDOVER.md`, and the live `marketing-site/Caddyfile`.

- Host: `root@31.97.123.81` (SSH confirmed working in the v6.0.0 handover).
- App repo on the box: `/root/OpenConstructionERP`.
- App virtualenv: `/root/OpenConstructionERP/venv/` (NOT `.venv` - this trips people up).
- App systemd unit: `openconstructionerp`, serving port `9090` on the host.
- App health endpoint: `http://localhost:9090/api/health` (NOT `/api/v1/health`, that returns 404). Expect `database=ok` and `alembic_head_matches=true`.
- App still runs on SQLite at `/root/OpenConstructionERP/data/openestimate.db`. The PG cutover is deferred (see section 3).
- Frontend is served by the backend from `backend/app/_frontend_dist` (must be re-synced after a `pip install`, otherwise built JS chunks 404).
- Demo login: `demo@openconstructionerp.com` (the old `demo@openestimator.io` was removed; commit `3e7a8c876` removed the dead `openestimator.io` domain). Password per V6_HANDOVER.md is `DemoPass1234!`. Login endpoint is `POST /api/v1/auth/login` (V6_HANDOVER.md also references `/api/v1/users/auth/login/` - confirm the exact path against the running build before scripting it).
- The contact email anywhere on the box must only ever be `info@datadrivenconstruction.io`.

### Reverse proxy / web server: Caddy

Caddy fronts everything on this box. The config that ships is `marketing-site/Caddyfile`. The same Caddy instance also serves `chat.datadrivenconstruction.io`, `prozesswerk.31.97.123.81.nip.io`, and the NocoDB host. Do not break those vhosts.

The `openconstructionerp.com` vhost (Caddyfile lines 25-148) does, in order:
- Sets HSTS / nosniff / frame / referrer / permissions security headers.
- Forces HTML revalidation: `Cache-Control "no-cache, must-revalidate"` for `*.html` and `/` (lines 38-39), so marketing HTML edits reach users without a hard refresh, but ETags still allow 304s.
- Proxies the marketing form endpoints to the in-house SMTP sidecar at `172.19.0.1:8891` (Caddyfile lines 42-85): `/api/demo-register` -> `/register`, `/api/license-request` -> `/license-request`, `/api/inquiry` -> `/inquiry`, `/api/subscribe` -> `/subscribe`, `/api/partners-apply` -> `/partners-apply`, `/api/forms-health` -> `/health`.
- Proxies the catch-all `/api/*` to the ERP backend at `172.19.0.1:9090` (lines 88-90).
- Serves the marketing static site from the Caddy root `/srv-oce` (the `handle` block at lines 137-147, plus the explicit static asset handlers at lines 100-119).

### The marketing forms sidecar

`marketing-site/demo-register-api.py` is the only dynamic piece of the marketing surface. It listens on port `8891` (file line 54) and appends JSON lines under `/root/clawd/` (file lines 268-282): demo registrations, license requests (`/root/clawd/license-requests.jsonl`), contact inquiries, newsletter subscribers, partner applications, and an email-failure log. It also handles SMTP send. If a marketing form stops working, check this process is running and that `/api/forms-health` returns ok before suspecting Caddy.

### CRUCIAL gotcha: `/assets/` is reverse-proxied to the app, NOT static

This is the single most important thing to know about deploying marketing static files.

The Vite-built ERP SPA emits `index.html` with `/assets/*` resource paths, so the Caddyfile forwards `/assets/*` to the backend SPA (lines 123-125):

```
handle /assets/* {
  reverse_proxy 172.19.0.1:9090
}
```

The backend's SPA fallback returns `index.html` (HTML) for unknown paths. So if you place a marketing static file under `/assets/` (for example `/assets/i18n.js`), a request for it gets proxied to the app and comes back as the SPA HTML document with a 200, NOT your file. The file "exists on disk" under `/srv-oce/assets/` but is never served, because the proxy rule wins before file_server is reached. This silently breaks anything that depends on it (it loads, but as HTML, so the JS throws a syntax error).

Only specific subpaths under `/assets/` are carved out as static before that proxy rule (Caddyfile lines 100-119): `/assets/loops/*`, `/assets/stills/*`, `/assets/screenshots/*`, `/assets/svg/*`, `/assets/icons/*`. Everything else under `/assets/` goes to the app.

Because of this, the shared i18n runtime was moved out of `/assets/` to `/i18n/i18n.js`. Top-level paths like `/i18n/` and `/locales/` and root-level `*.html` are NOT under `/assets/`, so they fall through to the static `handle` block (lines 137-147) and are served as real files via `try_files {path} {path}.html {path}/index.html` + `file_server`. That block also forwards genuine non-file paths (React Router routes like `/login`, `/dashboard`, `/projects`) to the backend so SPA refresh survives.

Rule of thumb for any new marketing static asset: do NOT put it under `/assets/` unless it is one of the five carved-out subfolders. Put runtime JS under `/i18n/` (or another top-level folder you add a static handler for), images under `/assets/svg|icons|stills|...`, and locale JSON under `/locales/`.

---

## 2. Uncommitted, undeployed marketing-site state (act on this first)

The marketing-site working tree is significantly ahead of what is committed, and none of it is on the live box yet. This is the most pressing marketing item.

What is committed (HEAD has the homepage i18n done): commit `0162056cc` "i18n(site): translate the homepage into all 19 languages" (792 strings, locale version bumped). `index.html` uses an INLINE i18n copy and fetches `locales/${lang}.json` with a relative path (no leading slash), with `LOCALE_VERSION = '20260605a'` (index.html line 20468). That relative fetch resolves correctly at the site root.

What is NOT committed (working-tree only, from `git status`):
- `marketing-site/i18n/` is a brand new UNTRACKED directory containing `i18n/i18n.js`, the shared runtime for all non-homepage pages. There is no `i18n.js` tracked anywhere in git history (neither under `assets/` nor `i18n/`). It lives only in the working tree.
- All 11 sub-pages now reference `<script src="/i18n/i18n.js" defer>` (confirmed in contact, demo-register, docs, download, imprint, industries, license-request, partners, news, services, standards). These edits are uncommitted (`M` in status).
- All 20 locale JSON files under `marketing-site/locales/` are modified (regenerated Jun 5), uncommitted.
- A new `download.html` and edits to `index.html`, `partners.html`, etc. are uncommitted.
- The on-disk `marketing-site/assets/` directory is now empty.

Stale documentation to be aware of: the comment header inside `marketing-site/i18n/i18n.js` (lines 5 and 34 of CLAUDE.md) still says `<script src="/assets/i18n.js" defer>`. That is the OLD path and is wrong given the `/assets/` gotcha; the live pages correctly use `/i18n/i18n.js`. The marketing-site `CLAUDE.md` also still documents the old deploy path `/srv/openconstructionerp.com && git pull` (lines 116-126), which does NOT match the live Caddy mount `/srv-oce` and may not match how the box actually pulls. Treat CLAUDE.md's deploy section as outdated and follow section 4 below instead.

Acceptance criteria for finishing this work item:
- `marketing-site/i18n/i18n.js` is committed (git add the new dir), the 11 sub-page edits are committed, the regenerated locales are committed, with conventional-commit messages and no AI attribution, DataDrivenConstruction voice, no em-dashes.
- After deploy, `https://openconstructionerp.com/i18n/i18n.js` returns the actual JavaScript with `Content-Type: text/javascript` (NOT an HTML document). If it returns HTML, the `/assets/` gotcha has reappeared or the file is not under `/srv-oce/i18n/`.
- `https://openconstructionerp.com/locales/de.json?v=20260605a` returns JSON.
- Each sub-page loads with a working language toggle and no console errors; switching language updates `data-i18n` nodes.

Gotcha: keep `LOCALE_VERSION` in `i18n/i18n.js` (line 19) in sync with the inline copy in `index.html` (line 20468); both are `20260605a` right now. Bump both together on every locale content change so browsers refetch.

---

## 3. PostgreSQL cutover on the VPS (still pending)

### Why it matters
Production still runs on SQLite while the product default since v6.0.0 is embedded PostgreSQL (pixeltable-pgserver, no Docker). The live demo therefore runs a configuration the project no longer ships by default, and a single-file SQLite DB on a 24/7 multi-tenant-ish demo is a scaling and durability liability. The founder decision (MASTER_PLAN_pg_embedded.md lines 74-88) is locked: Postgres everywhere via EMBEDDED Postgres, including the VPS, no Docker on the happy path.

### Why it is deferred (the real blockers)
From V6_HANDOVER.md lines 297-307 and MASTER_PLAN lines 65-67:
1. Disk is tight: root partition around 95 percent. The migration needs headroom for a full second copy of the data plus the new pgdata. There are roughly 6 GB of unused CUDA torch wheels in the venv (the box is CPU-only) that can be reclaimed by swapping to CPU torch, which is the documented way to free space.
2. Migrating live data is the most dangerous, least reversible step. The handover notes that in the session where it was attempted the tool output was being garbled, so each step (backup ok, migrate ok, health ok) could not be reliably verified, and migrating blind risked breaking working prod. This is a "do it in a clean session, verify every checkpoint" item.
3. The box also runs unrelated docker stacks (n8n; conference-chat = caddy/nocodb/qdrant/2x postgres; dokufluss) on their own ports including 5432. Never touch, prune, or reuse them. The embedded pgdata is self-contained under the app repo and does not collide.

### Which runbook to follow (there are three, only one is current)
The repo has three cutover documents that disagree because the strategy evolved:
- `docs/postgres-migration/_vps_cutover_plan.md` - a dedicated Docker `postgres:16` container on port 5433. SUPERSEDED. Do not use (MASTER_PLAN line 318 marks it superseded by embedded).
- `docs/postgres-migration/VPS_CUTOVER_RUNBOOK.md` - apt-installed `postgresql-16` cluster on 5432. Also pre-embedded; its checkpoints still say version 5.9.2. Useful for the data-migration command and rollback shape but the engine choice is outdated.
- The EMBEDDED-PG approach in `MASTER_PLAN_pg_embedded.md` (Phase 4, lines 234-256) and the step-by-step in `V6_HANDOVER.md` lines 302-307. THIS is the current, correct one: the app boots its own embedded PG under `/root/OpenConstructionERP/data/pgdata`, no separate DB process to manage.

### Current correct cutover outline (embedded PG, from V6_HANDOVER.md 302-307 + MASTER_PLAN Phase 4)
Run interactively, one block at a time, verifying each checkpoint. The SQLite file is never deleted, so rollback is one env change away.
1. Backup the live SQLite DB (timestamped `.bak`), and snapshot the current systemd env so you can diff.
2. `git fetch` and checkout the release tag to deploy (currently the box is on 5.9.1; bring it forward; pixeltable-pgserver is now a BASE dependency so the venv install pulls it). If disk is tight, reclaim the 6 GB unused CUDA torch first (swap to CPU torch).
3. Re-sync `_frontend_dist` after the pip install (otherwise JS chunks 404).
4. Phase 1 (SAFE): deploy still on SQLite via `OE_USE_SQLITE=1`, run `alembic upgrade head` using a 4-slash absolute `DATABASE_SYNC_URL` (`sqlite:////root/OpenConstructionERP/data/openestimate.db`), restart, verify `/api/health` shows the new version and `database=ok`. This proves the new code runs on prod data before any DB change.
5. Phase 2 (the risky flip): let the app migrate SQLite -> embedded PG (the transparent auto-migration: it migrates, verifies counts, archives a `.bak`, and aborts back to SQLite on failure), flip the env to embedded (drop `OE_USE_SQLITE`), restart, verify `/api/health` `database=ok` and spot-check row counts (users, projects). Keep the SQLite backup for at least a week as the rollback anchor.
6. Smoke test SEQUENTIALLY only. Never run parallel Playwright/probe runs against the shared demo box; concurrent probes stall the event loop. Login, then open Dashboard, Projects, one BOQ, one tab at a time.

Migration mechanics worth knowing: the data-copy script is `backend/app/scripts/migrate_sqlite_to_postgres.py`. It builds the target schema with `Base.metadata.create_all` (so the JSON->JSONB `@compiles` hook and the FK/composite/GIN performance indexes fire exactly like a fresh install), then copies every table in FK order, batched, idempotent, with per-row fault isolation and a retry pass for self-referential FKs. CLI flags are `--source`, `--target`, `--truncate`, `--dry-run`, `--batch-size` (default 1000). It auto-coerces async URLs to sync. There is no `--only` and no `--skip-create`. Always `--dry-run` first and treat its table/row counts as the baseline the real run must reproduce.

Embedded-PG runtime gotchas (from MASTER_PLAN 114-116 and memory): pixeltable-pgserver refuses to run PG as root and spawns a non-root postmaster, which matters because the systemd unit runs as root. A force-killed embedded PG can exceed the pg_ctl start timeout during crash recovery and cause a silent fallback to SQLite (the `database=ok` health check would hide it), so after the cutover verify the actual backend in use, not just that health is green. The postmaster survives a task stop because it is in a new process group, and its logs are UTF-16-LE. Pin a current 0.5.x of pgserver (0.2.0/0.2.1 are yanked).

Acceptance criteria for the cutover: fresh `/api/health` on the box reports `database=ok`, `alembic_head_matches=true`, the intended version, and module count around 117; row counts for users and projects match the SQLite source; a JSONB column reports type `jsonb`; sequential browser smoke passes; the n8n / conference-chat / dokufluss stacks are untouched; the SQLite `.bak` is retained.

Rollback: revert the two `DATABASE_*` env vars (or `systemctl revert` the drop-in) so the app uses SQLite again, restart, confirm `/api/health` `database=ok`. The app is back on SQLite in seconds.

---

## 4. Marketing-site deploy procedure (safe steps)

The marketing site is plain static HTML/CSS/JS with zero build step. Caddy serves it from the host directory mounted at `/srv-oce` inside the Caddy container. (The marketing-site CLAUDE.md still documents an older `/srv/openconstructionerp.com` git-pull flow, which does not match the live `/srv-oce` mount; do not trust it. Verify the real host path backing `/srv-oce` on the box before copying, see open questions.)

Safe deploy for HTML / CSS / locales / JS (no Caddyfile change):
1. Commit and push the marketing-site changes to `main` first (so the repo is the source of truth and the change is recoverable). Conventional commit, DataDrivenConstruction voice, no em-dashes, no AI attribution.
2. SSH to `root@31.97.123.81`.
3. Back up the current live files first: copy the current contents of the `/srv-oce`-backing directory to a timestamped backup before overwriting anything. This is the rollback anchor.
4. Copy only the changed files into the Caddy mount (scp the specific changed files, or `git pull` into the backing directory if it is a clone; confirm which it is on the box). Crucially, when you add the new `i18n/` directory and the regenerated `locales/`, make sure they land at `<mount>/i18n/i18n.js` and `<mount>/locales/*.json`, NOT under `<mount>/assets/`.
5. No Caddy restart is needed for static file changes; `file_server` serves from disk directly, and HTML is set to revalidate.
6. Verify from outside: `curl -I https://openconstructionerp.com/` (expect the security headers and `Cache-Control: no-cache, must-revalidate`), `curl -sI https://openconstructionerp.com/i18n/i18n.js` (expect a JS content-type, NOT `text/html`), and `curl -s https://openconstructionerp.com/locales/de.json?v=20260605a | head` (expect JSON). Then open a sub-page in a browser and switch language.

Deploy when the `Caddyfile` itself changes:
1. Commit and push.
2. SSH, update the Caddyfile on the box, then reload Caddy (prefer `caddy reload` / `docker compose restart caddy` depending on how Caddy runs there; check the live orchestration first since this box runs several stacks).
3. Verify `curl -I https://openconstructionerp.com/` shows the new headers and that the form endpoints and `/assets/*` proxy still behave.

Do not touch backend/frontend/services/packages/data/deploy from a marketing task (CLAUDE.md boundary contract). Marketing changes that depend on a release should ship as a separate commit after the platform release.

---

## 5. Quick reference

- VPS: `root@31.97.123.81`, app repo `/root/OpenConstructionERP`, venv `venv/`, unit `openconstructionerp` on `:9090`, health `/api/health`, app DB still SQLite at `data/openestimate.db`.
- Caddy marketing mount: `/srv-oce`. Forms sidecar: `172.19.0.1:8891`, writes `/root/clawd/*.jsonl`.
- App backend proxied at `172.19.0.1:9090`; `/assets/*` (except loops/stills/screenshots/svg/icons) goes to the APP, so keep marketing assets out of `/assets/`.
- Shared marketing i18n runtime lives at `/i18n/i18n.js` (NOT `/assets/i18n.js`); locales at `/locales/*.json`; `LOCALE_VERSION` currently `20260605a` in both `i18n/i18n.js` and `index.html`.
- PG cutover: follow the EMBEDDED-PG path (MASTER_PLAN Phase 4 + V6_HANDOVER 302-307), not the docker (`_vps_cutover_plan.md`) or apt (`VPS_CUTOVER_RUNBOOK.md`) plans. Blockers: disk ~95 percent (reclaim CPU torch), verify every checkpoint, never touch other stacks, keep SQLite as rollback.



## OPEN QUESTIONS
- The exact host directory that backs the Caddy /srv-oce mount could not be determined from repo files. The marketing-site CLAUDE.md says /srv/openconstructionerp.com (with git pull), the task brief says /root/clawd/openconstructionerp/, and the Caddyfile only names the in-container path /srv-oce. Confirm on the box (docker inspect the Caddy container volume binds, or readlink the mount) before scp/pull, and whether the backing dir is a git clone or a plain file drop.
- How the box actually updates marketing files (git pull cron vs manual scp) is unverified. The committed CLAUDE.md claims a cron pull but also gives a manual git pull; the working tree shows uncommitted changes that clearly were never pushed, so whatever mechanism exists is not keeping prod current. Determine the real mechanism on the host.
- How Caddy runs on the box (docker compose service name vs systemd vs raw binary) is not in the repo, so the exact reload command for a Caddyfile change is unconfirmed. Inspect docker ps / systemctl on the host.
- The current published version is stated as v6.9.0 in the task and v6.8.2 in memory, but on-disk pyproject.toml is 6.8.0 and the top CHANGELOG entry is 6.8.0. The VPS is reportedly still on 5.9.1. Confirm the actual published version and the exact tag/commit to deploy to the VPS during cutover.
- The systemd env mechanism on the VPS (EnvironmentFile path vs inline Environment= vs systemctl drop-in) cannot be seen from the repo. Run systemctl cat openconstructionerp on the box to decide whether to edit a file or add a drop-in, and capture existing env (JWT_SECRET etc) so the cutover only adds/changes DATABASE_* vars.
- Exact current free disk on the VPS is unknown (docs say ~95 percent as of the v6.0.0 era). Re-check df -h before the cutover; if still tight, reclaim the ~6 GB unused CUDA torch by swapping to CPU torch and re-test.
- The login endpoint path is inconsistent in docs (/api/v1/auth/login vs /api/v1/users/auth/login/). Confirm against the running build before scripting the smoke test.
- Whether the embedded-PG transparent auto-migration has ever been exercised against the real ~1.2GB prod SQLite is unverified; the prior attempt was abandoned due to garbled tool output. Do a --dry-run of migrate_sqlite_to_postgres.py and verify counts before the live flip.

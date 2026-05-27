# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**OpenConstructionERP** (PyPI: `openconstructionerp`, CLI: `openestimate`) — open-source AGPL-3.0 ERP for construction cost estimation: BOQ, 4D/5D planning, AI-powered estimation, CAD/BIM takeoff. Python 3.12+ FastAPI backend + React 18 + TypeScript Vite frontend. SQLite default (zero-config), PostgreSQL in production.

The longer vision/philosophy lives in [`.claude/CLAUDE.md`](.claude/CLAUDE.md) (calls itself "OpenEstimate" — same project, predecessor name). Sub-area guides: [`.claude/backend.md`](.claude/backend.md), [`.claude/frontend.md`](.claude/frontend.md). Per-release context in [CHANGELOG.md](CHANGELOG.md), v2.0.0+ release notes in [README.md](README.md).

Current branch context: `frappe-integration` adds an embedded mode where the SPA boots inside a Frappe Desk page (`/neoconstruction/*`) — see [Frappe integration](#frappe-integration-current-branch).

## Common commands

Top-level driver is the Makefile. First-time install (Python 3.12+, Node 20+):

```bash
make setup                     # pip install -e ./backend[server] + npm install in frontend
```

Daily dev (two terminals — `make dev` just prints instructions, only `dev-unix` backgrounds):

```bash
make dev-backend               # uvicorn :8000 with --reload (also `make infra` for PG/Redis/MinIO via docker)
make dev-frontend              # vite :5173
make dev-unix                  # POSIX-only shortcut: backend backgrounded + frontend
```

Tests:

```bash
make test                      # backend + frontend
make test-backend              # cd backend && pytest -x -v
make test-frontend             # cd frontend && vitest
make test-unit                 # pytest -m unit (no DB)
make test-integration          # pytest -m integration (needs DB)
make test-backend-cov          # pytest --cov=app --cov-report=term --cov-report=html
cd backend && pytest tests/path/to/test_x.py::test_y    # single test
cd backend && pytest -k "boq and not slow"              # by name pattern
cd frontend && npx playwright test                       # e2e (also `npm run test:e2e:ui`/`headed`)
```

Quality:

```bash
make lint                      # ruff check + npm run lint (eslint)
make format                    # ruff format + prettier
make typecheck                 # mypy app/ + tsc --noEmit
```

Database (Alembic):

```bash
make migrate                   # alembic upgrade head
make migrate-new MSG="…"       # alembic revision --autogenerate
make migrate-down              # downgrade -1
make seed                      # python -m app.scripts.seed_catalog (CWICR cost catalog; demo projects auto-seed on first boot)
make db-reset                  # DESTRUCTIVE: drop+create+migrate+seed (PG only)
```

Module scaffolding & build:

```bash
make module-new NAME=oe_foo    # backend/app/scripts/scaffold_module.py
make module-test NAME=oe_boq   # pytest -k "oe_boq"
make build-wheel               # frontend build → bundled into Python wheel via hatchling
make quickstart                # docker compose up (PG + unified app on :8080)
```

Frontend-only specifics:

```bash
cd frontend
npm run api:generate           # regenerates src/shared/lib/api-types.ts from http://localhost:8000/api/openapi.json (backend must be running)
npm run typecheck              # tsc --noEmit (strict mode)
```

## Architecture

### Backend — module-based FastAPI

Layout: `backend/app/main.py` is a factory (`create_app()` invoked via `uvicorn ... --factory`). It builds the app, mounts a few core routers manually (`i18n`, `module_mgmt`, `audit`, `search`, `activity`, `sidebar_badges`), then `module_loader.load_all(app)` discovers and mounts everything in `backend/app/modules/`.

```
Request → Middleware (auth/CORS/rate/tenant)
        → Router  (HTTP only, in modules/{name}/router.py)
        → Service (business logic, in modules/{name}/service.py — stateless)
        → Repository (SQLAlchemy queries, modules/{name}/repository.py)
        → Models (SQLAlchemy ORM, modules/{name}/models.py)
```

**Module conventions** (loader in `backend/app/core/module_loader.py`):
- Manifest: `app/modules/{name}/manifest.py` declares `manifest = ModuleManifest(name="oe_{name}", ...)`. The `oe_` prefix is the registered name; the directory drops it (`oe_boq` → `app/modules/boq/`).
- Loader auto-mounts `{name}/router.py` at `/api/v1/{dir_name}` with tag = `display_name`. If a module's `router.py` is missing, the loader logs and continues.
- Loader also auto-imports `models.py`, `hooks.py`, `events.py`, `validators.py` if present, and calls `package.on_startup()` if defined.
- Categories: `core` (51 modules, always loaded), `regional` (9: dach_pack, swiss_pack, uk_pack, us_pack, asia_pac_pack, latam_pack, india_pack, middle_east_pack, russia_pack), `extension`, `enterprise`, `intelligence`, `developer_tools`. Non-core modules can be disabled at runtime — state persists via `core/module_state.py`.
- Dependency resolution is topological (`depends=[...]` in manifest) and cycle-detecting.

**Validation is first-class**: `backend/app/core/validation/engine.py` exposes a rule engine; rules live in `backend/app/core/validation/rules/__init__.py` (colocated by design — DIN276, GAEB, NRM, MasterFormat, ÖNORM, DPGF, GB/T 50500, etc., plus `boq_quality` universal). Modules register custom rules via the registry. Every import must produce a `ValidationReport` (severity ∈ ERROR/WARNING/INFO) before persistence — see workflow in `.claude/CLAUDE.md`.

**Vector / AI**: vector DB is optional (LanceDB embedded by default, Qdrant for production via `QDRANT_URL`). LLM providers (Anthropic, OpenAI, Gemini, Mistral, Groq, DeepSeek, Ollama) are called directly via `httpx` in `app/modules/ai/ai_client.py` — vendor SDKs are intentionally NOT bundled (would add ~800 MB). API keys persist in DB + `~/.openestimate/config.json`.

**Database conventions**: `oe_{module}_{entity}` table names; UUID PKs; `created_at`, `updated_at`, `created_by` on every table; JSONB for metadata. Async SQLAlchemy 2.0 with `aiosqlite` (default) or `asyncpg` (prod). Multiple Alembic migrations per module are normal.

**No IfcOpenShell**: all CAD/BIM (RVT, IFC, DWG, DGN) goes through DDC cad2data → canonical JSON → modules. BCF is allowed as I/O (XML, no runtime dep).

### Frontend — features mirror backend modules

`frontend/src/features/{module}/` mirrors `backend/app/modules/{module}/` 1:1 most of the time. Routing in `frontend/src/app/App.tsx` lazy-loads heavy pages (BOQ editor, Schedule, Takeoff, CAD explorer…). Shared UI primitives in `frontend/src/shared/ui/`, hooks in `shared/hooks/`, API helpers in `shared/lib/api.ts` (uses generated types from `api-types.ts`).

**State**: Zustand for global state (`stores/`), TanStack Query v5 for server state (configured with `networkMode: 'offlineFirst'` and 30s `staleTime`; mutations are queued in `offlineStore` IndexedDB and replayed on reconnect — do NOT add `retry` at the react-query layer for offline). MutationCache auto-invalidates queries by mutation key prefix on success.

**i18n is mandatory** — all user-facing strings go through `react-i18next`'s `t()`. 21 languages, fallbacks bundled in `frontend/src/app/i18n-fallbacks.ts` (one big file, becomes its own chunk via Vite). Backend exposes `/api/v1/i18n/{locale}`. RTL supported (Arabic).

**Heavy UI libs**: AG Grid Community (BOQ tables), PDF.js (takeoff viewer), Three.js (3D BIM viewer), Yjs + y-websocket (collab editing), Recharts (dashboards), Leaflet/MapLibre (project maps).

### Frappe integration (current branch)

`frontend/src/main.tsx` detects embedded mode via any of: `window.__FRAPPE_INTEGRATION__`, `window.frappe.boot`, `window.oce_jwt`, or path `/neoconstruction`. When detected:

- `BrowserRouter basename` switches `/` → `/neoconstruction`.
- `App.tsx` swaps `AppLayout` → `FrappeLayout` (`frontend/src/app/layout/FrappeLayout.tsx`) — uses Frappe Desk's native sidebar + navbar.
- `useAuthStore` is force-set: `isAuthenticated: true`, `accessToken: window.oce_jwt`, email from `window.frappe.boot.user`. Frappe controller has already enforced access; OCE trusts that.
- A 401 from a `/api/v1/*` call should trigger `get_oce_jwt` to refresh (provisioning flow).

Stand-alone Vite dev server (no Frappe globals) keeps the `AppLayout` path.

### Companion repos (cross-repo context)

This OCE fork is the backend/SPA half of a 3-repo product. When a feature crosses repo boundaries (auth, scans, mobile capture), check the relevant peer first:

- **`~/GitHub/neoconstruction`** — Frappe v15 custom app that embeds this SPA at `/neoconstruction/*` on a Frappe site. SSO + thin UI wrapper only — no business logic of its own. Issues the OCE JWT via `neoconstruction.api.sso.get_oce_jwt` (HS256, secret `oce_jwt_secret` in `site_config.json` = `settings.jwt_secret` here). Provisions OCE users via `POST /api/v1/users/auth/register/`. **Has no DocType for 3D/BIM/scan files** — anything binary should hit OCE FastAPI directly with the JWT, never round-trip through Frappe.
- **`~/GitHub/neoffice-mobile`** — Expo / React Native monorepo (Expo SDK 55, RN 0.83, React 19) for the field/artisan app. Includes a **Room Scan** tool (`apps/mobile/app/[site_id]/tools/room-scan/`) using Apple **RoomPlan** via the `bvisible/expo-roomplan` fork. Capture produces three artifacts in `Documents/room-scans/{scanId}/`:
  - `scan.usdz` — Apple-native 3D model (AR Quick Look, archival)
  - `scan.json` — RoomPlan `CapturedRoom` parametric data (walls/doors/windows/openings/objects with transforms + dimensions + confidence) — **this is the source of truth for BOQ-grade quantities**, not the mesh
  - `photos/` — annotation photos
  Today the mobile app stores everything locally with no upload pipeline. Locked design (2026-05-01, [[Neoffice/Room-Scan/07-Pipeline-3D-OCE-Integration]] in Obsidian): mobile converts USDZ → glTF/GLB **on device** via iOS 17+ `MDLAsset.export(to:)`, fetches `oce_jwt` from Frappe, then `POST /api/v1/bim/scan/upload` (multipart: glb + json + usdz + photos) directly to **this** OCE backend. **Module `oe_bim` does not yet exist in `backend/app/modules/` — it must be created** (manifest, `BimScan`/`BimElement` models, parser RoomPlan JSON → canonical, router, Alembic migration, validation rules `room_scan`). Frontend `RoomScanViewerPage.tsx` will load the GLB via Three.js `GLTFLoader` and overlay measurements from the parametric JSON.

  **Format rule**: USDZ archived as-is, GLB for visualization, RoomPlan JSON drives quantities. **Never try to re-measure on the tessellated mesh** when the parametric JSON has the exact value. **No IfcOpenShell, no IFC** — RoomPlan data goes straight to canonical via the new parser, same as DDC cad2data outputs.

## Conventions to respect

These rules are enforced/expected — silent violations are a frequent source of churn:

- **Comments in English** (project + global rule). Identifiers always English.
- **All user-facing strings translatable**: backend `_("...")` (Frappe-style), frontend `t("...")`. No hardcoded labels, error messages, or button text.
- **`frappe.log_error(title, message)`** — title ≤ 140 chars, message unlimited. Never `frappe.log_error(f"long string")` — that goes into the title field and truncates.
- **Commits**: do NOT add `Co-Authored-By: Claude` or "Generated with Claude Code" footers (user instruction). Conventional Commits (`feat:`, `fix:`, `refactor:`, …).
- **Backend layering**: routers stay HTTP-only; business logic in services; SQLAlchemy queries only in repositories; never call repositories from routers.
- **ruff line-length = 120** (`backend/pyproject.toml`), TypeScript `strict: true`, Prettier `printWidth=100 singleQuote=true`. The `[tool.ruff.lint]` block ignores ~30 rules with comments explaining why — read it before adding rules back.
- **Validation on every import**: any new import path must produce a `ValidationReport`. Bypassing the validation engine is a review blocker.
- **Module manifest naming**: `name="oe_{x}"` in manifest, directory `{x}` without `oe_` prefix. The loader strips `oe_` to find the directory.
- **Don't add LLM vendor SDKs**: use `httpx` against the provider's REST API like the rest of `ai_client.py`. The `[semantic]` extra pulls Qdrant + sentence-transformers, the `[ai]` extra is a deprecated alias for it.
- **DDC cad2data only** for CAD/BIM — no IfcOpenShell. BCF (XML) is fine.

## Frequent gotchas

- `make dev` only prints instructions; you need `make dev-backend` + `make dev-frontend` in two terminals (or `make dev-unix` on POSIX). Windows users must run them separately.
- The frontend wheel-bundle path: `cd frontend && npm run build` THEN `make build-wheel` — hatchling force-includes `frontend/dist` into the wheel (see `[tool.hatch.build.targets.wheel.force-include]`).
- `make db-reset` only works against PostgreSQL via Docker Compose (`docker-compose.yml`). For SQLite dev DB, just delete the `.db` file and re-run.
- Vector DB and AI are entirely optional — features degrade gracefully. Don't add hard imports of `lancedb`, `qdrant_client`, `paddleocr`, etc. at module load time; they live behind try/except in the modules that need them.
- `npm run api:generate` requires the backend running on `:8000`. Regenerate `src/shared/lib/api-types.ts` after backend schema changes.
- Audit reports in `audit/` are snapshots of completed cross-cutting reviews (backend/frontend/db inventory, security, i18n, etc.) — useful context, not active work.
- BOQ unit normalization: CWICR multi-prefix forms like `'100 EA'`, `'1000 m'` are accepted (see `normalise_unit()`); bare units behave as before. Don't reject them in new code.

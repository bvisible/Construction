# OpenConstructionERP v4.6.0 — Floating chat + Accommodation + Geo raster overlay + dashboard widgets

## Overview

A 10-commit feature wave on top of v4.5.0. v4.6.0 puts an ERP-aware chat on every page, introduces the new **Accommodation** module (unified worker camps / rentals / hotels), ships **10 new dashboard widgets** with a server-synced layout customizer, adds **DWG/PDF raster overlay** to the Geo Hub globe, and rolls out **6 per-module guided tours** (BOQ, BIM, Geo, PropDev, Dashboard, Accommodation) with 192 hand-translated EN/DE/RU strings. Module count: 110 → 111.

## Highlights

- **Floating chat with full ERP database access** — bottom-right FAB on every page, 17 typed tools, streamed tool-call cards (`628ba697`).
- **Accommodation module (new)** — three lodging kinds in one model, booking state machine, PropDev bootstrap, HR autobook (`7816f3ff`, `66abdc2f`, `14f52eae`).
- **10 dashboard widgets + server-side layout persistence** — BOQ Summary, Critical Path, Top Risks, HSE Scorecard, Procurement Pipeline, Budget Variance, Change Orders, Clash Health, Validation Score, Weather Site (`313614c4`); widget endpoint 4xx count: **12 → 0** (`c3bf7831`).
- **Geo Hub DWG/PDF raster overlay** — drag-corners onto the globe, polygon crop with vertex drag, degenerate-bbox guard with actionable "Needs corners" CTA (`39b241b3`, `4cb0a93d`).
- **6 per-module guided tours** wired through `ModuleHelpButton tourId="…"` — BOQ · BIM · Geo · PropDev · Dashboard · Accommodation, 192 i18n strings (`690f09ba`).
- **Marketing-site SMTP fix** — port 465 now correctly uses `SMTP_SSL`; port 587 stays on STARTTLS (`aa5150c4`).
- **Latest alembic head**: `v3121` (Accommodation + Geo raster overlay), single-head invariant maintained.

## New modules

### Accommodation (`oe_accommodation`)

First entry in the new "lodging" surface — unifies what used to be three separate spreadsheets at most contractors:

- **Three kinds**: `worker_camp` (site crews), `rental` (staff apartments), `hotel` (visiting consultants).
- **Rooms** with status (`available` · `occupied` · `maintenance` · `blocked`), `bim_element_id`, base rate + currency (inherited from project when blank).
- **Bookings** with state machine `reserved → checked_in → checked_out` (or `cancelled` from any non-final state), 409 on bookings into maintenance/blocked rooms, idempotent same-state updates, final-state lock.
- **Charges** (base rent, extras, deposits, refunds) — Decimal precision, room currency inheritance.
- **PropDev bootstrap** — iterate a development block's plots and create rooms 1:1; idempotent on label.
- **HR autobook (suggest-confirm)** — lowest-labelled available `worker_camp` room for an employee Contact; UI confirms with a real booking POST. No auto-actions.
- **IDOR posture**: every helper returns 404 (never 403) on cross-tenant access — Wave-5 pattern.
- **Manifest**: `oe_accommodation` v0.1.0, depends on `oe_projects`, `oe_contacts`, `auto_install=True`.
- **Bookings list endpoint** with status[] + date-overlap filters (half-open interval semantics, NULL `check_out` treated as open-ended).
- **Frontend MVP**: `AccommodationListPage` (cards grouped by kind with tabs), `AccommodationDetailPage`, `BulkRoomAddModal`, `HrAutobookModal`.

## Feature additions

### Floating chat with the ERP DB
- Mounted in `AppLayout` → present on every route (Dashboard, BOQ, BIM, Geo, PropDev, Accommodation, all 111 modules).
- 17 tools: `get_all_projects`, `get_project_summary`, `get_boq_items`, `get_schedule`, `get_validation_results`, `get_risk_register`, `search_cwicr_database`, `get_cost_model`, `compare_projects`, `run_validation`, `create_boq_item`, `search_boq_positions`, `search_documents`, `search_tasks`, `search_risks`, `search_bim_elements`, `search_anything`.
- Streamed SSE responses with per-tool renderers (risk register table, BOQ summary table, etc.).
- Provider-agnostic — works behind any LLM backend already wired into the `ai_agents` module.

### 10 dashboard widgets + customizer
- New widget registry IDs: `boq_summary`, `validation_score`, `clash_health`, `schedule_critical`, `risk_top`, `hse_scorecard`, `procurement_pipeline`, `budget_variance`, `change_orders`, `weather_site`.
- Server-side layout persistence via `UserPreference` — your dashboard composition follows you between devices.
- `DashboardLayoutManager` lets users add / remove / reorder widgets without touching code.

### 6 per-module guided tours
- BOQ · BIM · Geo · PropDev · Dashboard · Accommodation each ship a hand-written tour invoked from `ModuleHelpButton tourId="…"` in their page header.
- 192 new i18n strings translated to DE/RU at native quality.

### Geo Hub raster overlay
- Upload PDF or image → tap four corner pins onto the globe → overlay drapes over terrain.
- **Polygon crop** with vertex drag for cookie-cutter trimming of irrelevant edges.
- Renders inside the existing Cesium 3D Tiles 1.1 viewer with proper z-ordering against project pins.

## Bug fixes

- **`aa5150c4`** — Marketing site SMTP port 465 was using STARTTLS-style `smtplib.SMTP` and silently failing handshake; now branches to `SMTP_SSL` for 465 / `SMTP` + `starttls()` for 587.
- **`c3bf7831`** — Dashboard widget URLs drifted from router prefixes during the previous wave (12 `/api/v1/...` paths returned 4xx). All endpoints reconciled; widget panel now boots clean.
- **`4cb0a93d`** — Geo overlay component had an infinite re-render loop on first open caused by an unstable `useMemo` dep; also added a degenerate-bbox guard so pixel→geo math that under-determines placement now shows a "Needs corners" CTA instead of a blank globe.

## Breaking changes

None. The `/api/v1/*` surface remains backwards-compatible.

## Migration

`alembic upgrade head` brings two new revisions:

- **v3120** — `accommodation_init` — creates `accommodations`, `accommodation_rooms`, `accommodation_bookings`, `accommodation_charges` with FKs to `projects` and (optional) `property_dev_blocks`.
- **v3121** — `geo_raster_overlay` — adds raster overlay tables for Geo Hub (image storage ref + four corner lat/lon + crop polygon).

Operator notes:
- VPS DB path stays `sqlite:////root/OpenConstructionERP/data/openestimate.db` (4 slashes).
- `rm -rf backend/app/_frontend_dist dist/` before building the wheel (PWA precache hashes go stale otherwise).
- Single-head invariant intact: `v3121_geo_raster_overlay`.

## Internal changes

- **Per-module ProductTour pattern** — `ModuleHelpButton tourId="<short_name>"` in the page header is the canonical way to add a tour. Tours are co-located with their feature folder.
- **Server-side dashboard layout** — `UserPreference`-backed payload replaces the old localStorage-only `DashboardLayoutManager` store. Existing localStorage layouts are migrated on first load.
- **Accommodation IDOR pattern** — Wave-5 404-not-403 idiom adopted module-wide; `_verify_project_access`, `_accessible_project_ids` helpers in `service.py` are the template for any future lodging-adjacent modules.
- **Chat tool registration** — `backend/app/modules/erp_chat/tools.py` is the single source of truth for tool specs; renderers are in `frontend/src/features/erp-chat/renderers/`.

## Contributors

— Artem & contributors. Reach us at `info@datadrivenconstruction.io`.

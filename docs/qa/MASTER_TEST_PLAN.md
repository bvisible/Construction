# OpenConstructionERP — MASTER TEST PLAN

**Version**: 1.0 (drafted 2026-05-24 against main HEAD)
**Target build**: v4.6.1 (commit `4e9d4b5b`, alembic head `v3123_boq_fk_indexes`)
**Scope**: 112 backend modules + 100+ frontend feature pages
**Contact**: `info@datadrivenconstruction.io`

## Table of contents

- [Phase 0 — Environment setup](#phase-0--environment-setup)
- [Phase 1 — Smoke tests](#phase-1--smoke-tests-gate-to-phase-2)
- [Phase 2 — Module-by-module test inventory](#phase-2--module-by-module-test-inventory)
- [Phase 3 — End-to-end persona journeys](#phase-3--end-to-end-persona-journeys)
- [Phase 4 — Regression matrix](#phase-4--regression-matrix)
- [Phase 5 — Bug-fix loop](#phase-5--bug-fix-loop)
- [Phase 6 — Reporting](#phase-6--reporting)
- [Appendix A — Module ↔ batch mapping](#appendix-a--module--batch-mapping)
- [Appendix B — Test-id namespace](#appendix-b--test-id-namespace)

## Overview

OpenConstructionERP v4.6.1 ships 112 backend modules and 100+ frontend
feature folders. This plan defines six phases of testing — from a fresh
Docker compose bring-up through smoke, per-module exhaustion, persona
journeys, cross-cutting regression, the bug-fix loop, and the final
reporting pack — at a level of detail that any browser-automation
agent (Playwright + Chromium/Firefox/WebKit) can execute end-to-end
without ambiguity.

The plan is **agent-executable**: every numbered test specifies its
pre-condition, click-by-click steps, expected outcome, screenshot
filename, and machine-checkable pass criterion. Sister artefact
`test_plan_manifest.json` is the machine-readable manifest the test
runner consumes.

**Why six phases?**
1. Phase 0 verifies the SUT itself (no point testing a broken stack).
2. Phase 1 protects every other test from wasted runtime when login is
   broken.
3. Phase 2 is the bulk of the work — every module, every button.
4. Phase 3 is journeys: real users do not touch one module at a time.
5. Phase 4 is invariants every module must satisfy; running them
   inline in Phase 2 would explode runtime, so they are factored out.
6. Phase 5 closes the loop — bugs are useless until they are fixed.
7. Phase 6 emits artefacts a human can read in 30 minutes to decide
   `ship` or `hold`.

## Phase 0 — Environment setup

This phase must complete green before any test from Phase 1 onwards is allowed to
run. The runner treats Phase 0 as a hard gate: a failure here aborts the wave.

### 0.1 Fresh Docker compose runbook

The runner provisions a clean, hermetic environment per wave to guarantee that
no stale data, no cached migrations, and no residual JWT survives between
runs.

1. Bring down any previous stack:

   ```bash
   docker compose down -v --remove-orphans
   docker volume prune -f
   ```

2. Wipe the local SQLite dev DB (if running outside docker):

   ```bash
   rm -f data/openestimate.db
   rm -rf backend/app/_frontend_dist
   ```

3. Start the dependencies (postgres + redis + minio + qdrant):

   ```bash
   docker compose up -d postgres redis minio qdrant
   ```

4. Wait for each service to be healthy:

   ```bash
   docker compose ps --format json | jq -r '.[] | "\(.Service) \(.Health)"'
   # expect: postgres healthy, redis healthy, minio healthy, qdrant healthy
   ```

5. Apply migrations and verify the head matches the expected revision:

   ```bash
   alembic upgrade head
   alembic current
   # expect: v3123_boq_fk_indexes (head)
   ```

   The single-head invariant must hold — `alembic heads` should print exactly
   one revision. If two are printed, abort the wave and file a `blocker`.

6. Load seed data + demo users:

   ```bash
   python -m scripts.seed_demo
   python -m scripts.seed_cwicr --rows 5000  # smaller subset for fast tests
   ```

   The seed script provisions:

   - `demo@openconstructionerp.com` / `demo123`  (TENANT_A, role=OWNER)
   - `editor@openconstructionerp.com` / `demo123`  (TENANT_A, role=EDITOR)
   - `viewer@openconstructionerp.com` / `demo123`  (TENANT_A, role=VIEWER)
   - `tenantb@openconstructionerp.com` / `demo123`  (TENANT_B, role=OWNER)  — IDOR check baseline
   - 3 sample projects with BOQs, BIM, schedule, finance pre-populated

   IMPORTANT: the email is `openconstructionerp.com` (with the "r") — NOT
   `openestimate.io` (which 401s and is a recurring test-author pitfall).

### 0.2 Backend bring-up

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Wait for `Application startup complete`, then verify:

| Check | URL | Expected |
|-------|-----|----------|
| Health | `GET http://localhost:8000/api/health` | `{"status":"ok"}` 200 |
| Modules | `GET http://localhost:8000/api/system/modules` | array length **≥ 112** |
| Alembic | response body includes `alembic_head_matches: true` | true |
| OpenAPI | `GET http://localhost:8000/openapi.json` | 200 + non-empty `paths` |

NOTE: `/api/v1/health` returns **404** — only `/api/health` (no `/v1`) is
correct. This bites every new test author.

### 0.3 Frontend bring-up

```bash
cd frontend && npm ci && npm run dev -- --host 127.0.0.1 --port 5173
```

Wait for `Local: http://127.0.0.1:5173/`. The dev server proxies
`/api/*` → `http://127.0.0.1:8000` via `vite.config.ts`.

Verify in the browser by visiting `http://localhost:5173/` and:

- Login form renders.
- Top-right locale switcher offers EN/DE/RU/AR.
- No red console errors except the well-known suppressed PWA precache warning
  in dev mode.

### 0.4 Browser launch (Playwright)

```bash
cd frontend
npx playwright install --with-deps chromium firefox webkit
npx playwright test e2e/critical_paths.spec.ts --reporter=line
```

Critical-path smoke must pass on Chromium AND Firefox AND WebKit before any
Phase 2 batch is scheduled. If WebKit fails for known engine-specific bugs
(rare), the wave can proceed but the WebKit fails are filed as `minor`.

### 0.5 Required artefacts directory

```
qa-runs/
└── 2026-05-24T18-15-00Z/
    ├── screenshots/
    │   └── batch-XX-<module>/<test-id>/<step>.png
    ├── traces/
    ├── videos/
    ├── axe-reports/
    ├── lighthouse/
    ├── coverage/
    └── report.html
```

The runner creates this tree before Phase 1 starts and refuses to begin if it
cannot write to `qa-runs/`.

### 0.6 Phase 0 exit criteria

All five checkboxes must be true:

- [ ] All four docker dependencies report healthy.
- [ ] `alembic current` shows `v3123_boq_fk_indexes (head)` and exactly one head.
- [ ] `/api/system/modules` returns ≥ 112 module entries.
- [ ] Playwright critical_paths.spec.ts passes on all three engines.
- [ ] Demo accounts can log in via the UI.


## Phase 1 — Smoke tests (gate to Phase 2)

The smoke suite is a 12-test critical-path bundle. Every test must pass before
the per-module batches in Phase 2 begin executing. Failures here are auto-
classified `blocker` and short-circuit the wave.

### Test S-01 — Login with valid demo credentials

- **Pre-condition**: stack from Phase 0 is up; database freshly seeded.
- **Steps**:
  1. Navigate to `http://localhost:5173/login`.
  2. Wait for the e-mail input to be visible (selector
     `input[type="email"][name="email"]`).
  3. Type `demo@openconstructionerp.com`.
  4. Type `demo123` into `input[type="password"]`.
  5. Click `button[type="submit"]` labelled `Sign in`.
- **Expected**: redirect to `/dashboard` within 3 s; no `Unauthorized` toast;
  cookie `oe_session` exists with `HttpOnly; Secure; SameSite=Lax`.
- **Screenshot point**: `S-01-after-login.png`
- **Pass criteria**:
  - `page.url() === "http://localhost:5173/dashboard"`
  - `await page.locator('[data-testid="user-menu"]').isVisible()`
  - Network response from `/api/v1/users/login` was 200.

### Test S-02 — Logout

- **Pre-condition**: S-01 passed.
- **Steps**:
  1. Click `[data-testid="user-menu"]`.
  2. Click menu item `Logout`.
- **Expected**: redirect to `/login`; cookie `oe_session` cleared; visiting
  `/dashboard` directly redirects back to `/login`.
- **Screenshot point**: `S-02-after-logout.png`
- **Pass criteria**: `await page.locator('input[name="email"]').isVisible()`.

### Test S-03 — Magic-link buyer portal

- **Pre-condition**: a buyer with email `buyer.smoke@example.com` exists
  (seeded). Backend `EMAIL_BACKEND=console` so the magic link prints to stdout.
- **Steps**:
  1. POST `/api/v1/portal/magic-link` with `{"email": "buyer.smoke@example.com"}`.
  2. Tail container logs, extract URL matching
     `https?://[^\s]+/portal/magic\?token=([A-Za-z0-9._-]+)`.
  3. Navigate the browser to that URL.
- **Expected**: lands on `/portal/dashboard`; buyer can see their reservation.
- **Screenshot point**: `S-03-portal-dashboard.png`
- **Pass criteria**: `[data-testid="portal-buyer-name"]` shows the buyer's
  display name.

### Test S-04 — Dashboard loads (after login)

- Re-log as `demo@openconstructionerp.com`.
- Verify dashboard widgets render: BOQ Summary, Critical Path, Top Risks, HSE
  Scorecard, Procurement Pipeline, Budget Variance, Change Orders, Clash
  Health, Validation Score, Weather Site (10 widgets total — v4.6.0).
- **Pass criteria**: zero 4xx responses on the dashboard widget panel
  (regression from v4.6.0 `c3bf7831`).

### Test S-05 — Sidebar renders all 112+ entries

- After login, count the items in `[data-testid="sidebar-nav-item"]`.
- **Pass criteria**: count ≥ 112; no duplicate labels; no `__MISSING__` strings.

### Test S-06 — /settings opens without error

- Click sidebar `Settings`.
- **Pass criteria**: `/settings` route renders, no console error, axe-core
  reports zero blocking violations.

### Test S-07 — Health endpoint

- HTTP GET `http://localhost:8000/api/health` → 200 + JSON body with `status:
  "ok"`, `version: "4.6.1"`, `alembic_head_matches: true`,
  `module_count: >=112`.

### Test S-08 — Critical-path: create project

- New project from sidebar → name `SmokeTestProject-{timestamp}` → submit.
- **Pass criteria**: redirects to `/projects/:id`; project appears in
  `/projects` list; appears in `/api/v1/projects`.

### Test S-09 — Critical-path: add BOQ position

- Inside `SmokeTestProject` → BOQ tab → click `+ Add position` → fill
  description, qty=10, unit=m³, unit_rate=125.50 → save.
- **Pass criteria**: position appears in the grid; total = 1255.00; persists
  after reload.

### Test S-10 — Critical-path: upload document

- Inside project → Documents → drag a small PDF.
- **Pass criteria**: appears in list with magic-byte verified `application/pdf`
  badge; download round-trips bytes identically.

### Test S-11 — Locale switcher EN→DE→RU→AR

- Cycle locales via header switcher.
- **Pass criteria**: at least the dashboard title text changes; no untranslated
  `t('…')` keys leak to DOM; AR triggers `dir="rtl"` on `<html>`.

### Test S-12 — Floating chat opens

- Click the bottom-right FAB.
- **Pass criteria**: chat panel mounts; typing "list my projects" + Enter
  returns at least one project tool-call card.

### Phase 1 exit gate

All 12 tests green on Chromium. If any one fails the wave is paused and the
failure is opened as a `blocker` in `docs/qa/bugs_<timestamp>.md`.


## Phase 2 — Module-by-module test inventory

The 112 modules are grouped into 15 logical batches for parallel
execution. Each batch runs as its own runner job with its own clean
test database snapshot.

Batch dependencies form a DAG so the scheduler can fan out as many
batches as there are runner slots. Per-module sections below are
auto-generated from `backend/app/modules/<mod>/router.py` and the
matching `frontend/src/features/<feat>/` folder.

### Section 2.shared — shared per-module test templates

Every per-module test of the same `T0NN` number follows the same template
below. The runner agent fills in `<module>`, `<endpoint>`, and the actual DOM
selectors discovered at runtime.

#### Template T001 — "GET list endpoint returns 200 + array"

- **Pre**: logged in as `demo@openconstructionerp.com` (OWNER, TENANT_A).
- **Steps**:
  1. HTTP GET the module's first GET endpoint (discovered from `router.py`).
  2. Inspect the response.
- **Expected**: HTTP 200; body is a JSON array OR an envelope shaped like
  `{items: [...], total: N, page: 1, page_size: 50}`.
- **Pass criteria**:
  ```js
  response.status === 200 &&
  (Array.isArray(body) || ('items' in body && Array.isArray(body.items)))
  ```

#### Template T002 — "Open from sidebar and capture first paint"

- **Pre**: logged in; at least one project exists.
- **Steps**:
  1. Locate the sidebar nav item that maps to the module (label varies by
     locale — use `[data-module-id="<module>"]` if present, else fall back to
     accessible name from `aria-label`).
  2. Click it.
  3. Wait for `<h1>` to be visible AND any `[data-testid="loader"]` to detach.
- **Expected**: page renders without console errors; main heading visible
  within 3000 ms.
- **Pass criteria**: `h1` visible, no red console error, no XHR with status
  ≥ 400.

#### Template T003 — "Empty state renders when no data exists"

- **Pre**: filter / fresh project ensures zero rows match.
- **Steps**:
  1. Apply a filter that matches nothing, OR open a fresh project with no
     module data.
  2. Observe the list area.
- **Expected**: an illustrative empty-state component with copy + CTA. NOT a
  blank grid.
- **Pass criteria**: page contains text matching `/no\s+(results|data|items)/i`
  OR `[data-testid="empty-state"]` is visible.

#### Template T004 — "Click every safe button + capture screenshot per state"

- **Pre**: page loaded with seeded data.
- **Steps**:
  1. Enumerate every `<button>` whose accessible name does NOT match
     `/delete|remove|destroy|drop|reset|wipe/i`.
  2. For each: click → wait 500 ms → screenshot → if a modal opened,
     screenshot it then press Escape → assert
     `window.__errors__.length === 0`.
- **Expected**: every non-destructive button either opens a panel/modal,
  navigates, or shows a toast. Never throws.
- **Pass criteria**: `window.__errors__.length === 0` after all clicks.

#### Template T005 — "Fill every form with valid data + submit"

- **Pre**: forms enumerated; fixture registry available for valid values.
- **Steps**:
  1. For each `<form>`: fill required inputs with valid values from
     `tests/fixtures/qa/values_<module>.json`.
  2. Submit.
  3. Observe success indicator (toast / redirect / row inserted).
- **Expected**: success path completes; no 5xx; created entity visible.
- **Pass criteria**: POST response 2xx; success indicator detected within
  3000 ms.

#### Template T006 — "Locale toggle EN → DE → RU → AR (RTL)"

- **Pre**: page loaded.
- **Steps**:
  1. For each locale in `['en', 'de', 'ru', 'ar']`:
     a. Click the locale switcher; select the locale.
     b. Wait for the lazy-locale chunk to load (`useI18nReady()` flips true).
     c. Assert main heading text changed vs the EN baseline.
     d. For `ar`, additionally assert `document.documentElement.dir === 'rtl'`.
- **Expected**: all four locales render without untranslated keys; AR is RTL.
- **Pass criteria**: no DOM text matching `/__MISSING__|t\(['"]/`; for AR
  `documentElement.dir === 'rtl'`.

#### Template T007 — "axe-core a11y audit (WCAG AA)"

- **Pre**: page loaded with data.
- **Steps**:
  1. Inject axe-core script.
  2. Run `axe.run({ runOnly: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] })`.
- **Expected**: zero violations of severity `critical` or `serious`.
- **Pass criteria**:
  ```js
  violations.filter(v => ['critical', 'serious'].includes(v.impact)).length === 0
  ```

#### Template T008 — "Mobile viewport 375×667 — no horizontal scroll"

- **Pre**: page loaded.
- **Steps**:
  1. `page.setViewportSize({ width: 375, height: 667 })`.
  2. Reload.
  3. Evaluate `document.documentElement.scrollWidth - window.innerWidth`.
- **Expected**: difference ≤ 1 px.
- **Pass criteria**: `diff <= 1`.

#### Template T009 — "Large dataset (1000+ rows) — render and scroll"

- **Pre**: seed 1000 rows via
  `python scripts/qa/seed_bulk.py --module <mod> --count 1000`.
- **Steps**:
  1. Load page.
  2. Scroll to bottom.
  3. Measure scroll FPS via `Performance.mark`.
- **Expected**: page does not freeze; FPS during scroll ≥ 30; no OOM warnings.
- **Pass criteria**: average scroll FPS ≥ 30; DOM node count stays ≤ 5000.

#### Template T010 — "IDOR — cross-tenant access returns 404 (NOT 403, NOT 200)"

- **Pre**: resource X created by TENANT_A; logged in as TENANT_B.
- **Steps**:
  1. As TENANT_A: POST a resource; capture `{id}`.
  2. Log out; log in as `tenantb@openconstructionerp.com`.
  3. GET / PATCH / DELETE the same `{id}`.
- **Expected**: all three return HTTP 404.
- **Pass criteria**: all three responses `.status === 404`.

#### Shared edge-cases checklist (applies to every list/CRUD page)

- Empty state (no rows) — illustrative.
- Single row — pagination disabled or hidden.
- Exactly one page worth of rows — last-page button disabled.
- 1000+ rows — virtual scroll smooth, DOM ≤ 5000 nodes.
- Network failure — disconnect, retry, observe banner + reconnect.
- Slow network (Chrome DevTools `Slow 3G`) — skeleton loaders, no white flash.
- 403 from API — user-friendly message, not raw JSON.
- 404 from API — page-level 404 component, not blank screen.
- 500 from API — error boundary fallback + retry button.
- Concurrent edit (two tabs) — last-write-wins OR conflict UI surfaced.
- Locale toggle mid-flow — form values preserved, labels translated.
- Mobile viewport (375×667) — no horizontal scroll, all CTAs reachable.
- Keyboard-only navigation — Tab reaches every interactive element; Enter activates.
- Screen reader (axe-core) — zero critical/serious violations.
- Print stylesheet — page is readable in print preview.

The per-module sections below cite this section by ID rather than
duplicating the 200+ lines of step detail 112 times.


### Batch overview

| Batch | Name | Modules | Est. minutes | Depends on |
|-------|------|---------|--------------|------------|
| `batch-01-auth-identity` | Auth, Users, Settings, Account, Admin | 4 | 110 | — |
| `batch-02-projects-companies-contacts` | Projects, Companies, Contacts | 3 | 120 | batch-01-auth-identity |
| `batch-03-boq-suite` | BOQ — editor, exports, GAEB, validation | 3 | 240 | batch-02-projects-companies-contacts |
| `batch-04-costs-catalog-match-resources` | Costs, Catalog, Match Elements, Resources | 7 | 200 | batch-03-boq-suite |
| `batch-05-bim-cad-validation` | BIM Hub, BIM Models, CAD Import, Validation, Clash | 9 | 280 | batch-02-projects-companies-contacts |
| `batch-06-takeoff` | Takeoff (manual + DWG + PDF + CV) | 3 | 180 | batch-03-boq-suite |
| `batch-07-propdev` | Property Development — Lead → Warranty + Accommodation | 4 | 360 | batch-02-projects-companies-contacts |
| `batch-08-crm-sales-pipeline` | CRM, Sales Pipeline, Activities | 2 | 150 | batch-02-projects-companies-contacts |
| `batch-09-procurement-subs-bids` | Procurement, Subcontractors, Bid Management, RFQ | 5 | 220 | batch-03-boq-suite |
| `batch-10-schedule-workorders-risk` | Schedule, Schedule Advanced (Last Planner), Tasks, Risk | 5 | 220 | batch-02-projects-companies-contacts |
| `batch-11-qms-hse-field` | QMS, HSE, HSE Advanced, Daily Diary, Snag List, Punchlist, Field Reports, Inspections, NCR, Safety, Service, Equipment | 10 | 320 | batch-02-projects-companies-contacts |
| `batch-12-finance-eac-contracts-changeorders-variations` | Finance, Cost Model, EAC, Contracts, Variations, Change Orders | 7 | 280 | batch-03-boq-suite, batch-09-procurement-subs-bids |
| `batch-13-carbon-submittals-rfi-meetings-reports` | Carbon, Submittals, RFI, Meetings, Reports, Reporting, BI | 11 | 280 | batch-03-boq-suite |
| `batch-14-geo-hub` | Geo Hub (Cesium 3D Tiles, raster overlay, auto-anchor) | 1 | 140 | batch-02-projects-companies-contacts |
| `batch-15-ai-chat-vector-marketplace-integrations` | AI, AI Agents, ERP Chat, Search, Integrations, Webhooks, Marketplace | 39 | 420 | batch-03-boq-suite |

**Total estimated runner-minutes (serial)**: 3520  
**Total estimated wall-clock with 5 parallel runners**: ~704 minutes  
**Total estimated agent-hours (incl. triage + fix loop)**: ~93.9 hours

### Batch `batch-01-auth-identity` — Auth, Users, Settings, Account, Admin

**Summary**: Login, RBAC, JWT, magic links, MFA, password reset, user CRUD, role assignment, audit log, tenant-scope toggles.

**Modules in this batch**: users, admin, teams, notifications

**Estimated runner-minutes**: 110  
**Depends on**: —

### Module: `users`

- Backend: `backend/app/modules/users/`
- Frontend: `frontend/src/features/users/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 38

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `POST` | `/auth/register/` |
| `POST` | `/auth/register` |
| `POST` | `/auth/demo-login/` |
| `POST` | `/auth/demo-login` |
| `POST` | `/auth/login/` |
| `POST` | `/auth/login` |
| `POST` | `/auth/refresh/` |
| `POST` | `/auth/refresh` |
| `POST` | `/auth/forgot-password/` |
| `POST` | `/auth/reset-password/` |
| `GET` | `/me/` |
| `GET` | `/me` |
| `PATCH` | `/me/` |
| `POST` | `/me/change-password/` |
| `GET` | `/me/preferences/` |
| `PATCH` | `/me/preferences/` |
| `GET` | `/me/api-keys/` |
| `POST` | `/me/api-keys/` |
| `DELETE` | `/me/api-keys/{key_id}` |
| `GET` | `/me/module-preferences/` |
| … | (+18 more — see `router.py`) |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/users/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `users-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `users-T002` | Open `users` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `users-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `users-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `users-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `users-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `users-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `users-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `users-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `users-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- Login timing-attack safe (test_auth_timing).
- Demo email is `demo@openconstructionerp.com` (with 'r').
- Magic-link + JWT round-trip.

### Module: `admin`

- Backend: `backend/app/modules/admin/`
- Frontend: `frontend/src/features/admin/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 3

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `POST` | `/qa-reset` |
| `POST` | `/cost-vector-reindex` |
| `GET` | `/cost-vector-reindex/status/{task_id}` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/admin/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `admin-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `admin-T002` | Open `admin` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `admin-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `admin-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `admin-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `admin-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `admin-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `admin-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `admin-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `admin-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `teams`

- Backend: `backend/app/modules/teams/`
- Frontend: `(API-only — no UI)`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 8

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/` |
| `GET` | `/project/{project_id}` |
| `POST` | `/` |
| `PATCH` | `/{team_id}` |
| `DELETE` | `/{team_id}` |
| `GET` | `/{team_id}/members/` |
| `POST` | `/{team_id}/members/` |
| `DELETE` | `/{team_id}/members/{user_id}` |

**UI surface area**

- API-only module — no UI surface to test. Run API-only test path:
  - exercise every endpoint from above via `httpx` directly;
  - validate JSON schemas against `openapi.json`;
  - run regression matrix items reg-01, reg-02, reg-04, reg-05.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `teams-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `teams-T002` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `notifications`

- Backend: `backend/app/modules/notifications/`
- Frontend: `frontend/src/features/notifications/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 9

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/` |
| `GET` | `/unread-count/` |
| `POST` | `/{notification_id}/read/` |
| `POST` | `/read-all/` |
| `DELETE` | `/{notification_id}` |
| `GET` | `/preferences/` |
| `POST` | `/preferences/` |
| `GET` | `/event-types/` |
| `POST` | `/digest/flush/` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/notifications/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `notifications-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `notifications-T002` | Open `notifications` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `notifications-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `notifications-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `notifications-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `notifications-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `notifications-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `notifications-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `notifications-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `notifications-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Batch `batch-02-projects-companies-contacts` — Projects, Companies, Contacts

**Summary**: Project CRUD, archive/restore, settings, members; contacts module-bridge (v3117), correspondence threading.

**Modules in this batch**: projects, contacts, correspondence

**Estimated runner-minutes**: 120  
**Depends on**: batch-01-auth-identity

### Module: `projects`

- Backend: `backend/app/modules/projects/`
- Frontend: `frontend/src/features/projects/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 48

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `POST` | `/` |
| `GET` | `/` |
| `GET` | `/{project_id}` |
| `PATCH` | `/{project_id}` |
| `DELETE` | `/{project_id}/` |
| `DELETE` | `/{project_id}` |
| `POST` | `/{project_id}/restore/` |
| `POST` | `/{project_id}/duplicate/` |
| `GET` | `/{project_id}/members/` |
| `GET` | `/{project_id}/members` |
| `POST` | `/{project_id}/members/` |
| `POST` | `/{project_id}/members` |
| `DELETE` | `/{project_id}/members/{member_user_id}/` |
| `DELETE` | `/{project_id}/members/{member_user_id}` |
| `GET` | `/{project_id}/folder-permissions/` |
| `POST` | `/{project_id}/folder-permissions/` |
| `DELETE` | `/{project_id}/folder-permissions/{permission_id}/` |
| `GET` | `/{project_id}/dashboard/` |
| `GET` | `/dashboard/cards/` |
| `GET` | `/analytics/overview/` |
| … | (+28 more — see `router.py`) |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/projects/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `projects-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `projects-T002` | Open `projects` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `projects-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `projects-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `projects-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `projects-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `projects-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `projects-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `projects-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `projects-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `contacts`

- Backend: `backend/app/modules/contacts/`
- Frontend: `frontend/src/features/contacts/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 15

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/` |
| `GET` | `/search/` |
| `GET` | `/stats/` |
| `GET` | `/tags/` |
| `GET` | `/by-company/` |
| `POST` | `/import/file/` |
| `GET` | `/export/` |
| `GET` | `/template/` |
| `POST` | `/` |
| `GET` | `/{contact_id}` |
| `PATCH` | `/{contact_id}` |
| `DELETE` | `/{contact_id}` |
| `POST` | `/{contact_id}/convert-to-lead` |
| `POST` | `/{contact_id}/convert-to-buyer` |
| `GET` | `/{contact_id}/module-rows` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/contacts/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `contacts-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `contacts-T002` | Open `contacts` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `contacts-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `contacts-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `contacts-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `contacts-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `contacts-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `contacts-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `contacts-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `contacts-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `correspondence`

- Backend: `backend/app/modules/correspondence/`
- Frontend: `frontend/src/features/correspondence/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 6

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/` |
| `POST` | `/` |
| `GET` | `/{correspondence_id}` |
| `PATCH` | `/{correspondence_id}` |
| `DELETE` | `/{correspondence_id}` |
| `POST` | `/{correspondence_id}/attachments/` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/correspondence/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `correspondence-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `correspondence-T002` | Open `correspondence` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `correspondence-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `correspondence-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `correspondence-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `correspondence-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `correspondence-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `correspondence-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `correspondence-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `correspondence-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Batch `batch-03-boq-suite` — BOQ — editor, exports, GAEB, validation

**Summary**: BOQ editor (AG Grid + hierarchy MAX_NESTING_DEPTH=8), section-scoped add, reusable positions, FX-correct exports, GAEB X83/X84, validation rule packs.

**Modules in this batch**: boq, assemblies, validation

**Estimated runner-minutes**: 240  
**Depends on**: batch-02-projects-companies-contacts

### Module: `boq`

- Backend: `backend/app/modules/boq/`
- Frontend: `frontend/src/features/boq/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 90

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `POST` | `/boqs/` |
| `GET` | `/boqs/` |
| `GET` | `/boqs/templates/` |
| `POST` | `/boqs/from-template/` |
| `POST` | `/boqs/classify/` |
| `POST` | `/boqs/classify-elements/` |
| `POST` | `/boqs/search-cost-items/` |
| `POST` | `/boqs/suggest-rate/` |
| `POST` | `/boqs/{boq_id}/check-anomalies/` |
| `POST` | `/boqs/enhance-description/` |
| `POST` | `/boqs/suggest-prerequisites/` |
| `POST` | `/boqs/{boq_id}/check-scope/` |
| `POST` | `/boqs/escalate-rate/` |
| `GET` | `/boqs/{boq_id}` |
| `GET` | `/boqs/{boq_id}/structured/` |
| `GET` | `/boqs/{boq_id}/activity/` |
| `GET` | `/projects/{project_id}/activity/` |
| `GET` | `/projects/{project_id}/resource-by-code/` |
| `PATCH` | `/boqs/{boq_id}` |
| `DELETE` | `/boqs/{boq_id}` |
| … | (+70 more — see `router.py`) |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/boq/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `boq-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `boq-T002` | Open `boq` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `boq-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `boq-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `boq-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `boq-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `boq-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `boq-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `boq-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `boq-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- MAX_NESTING_DEPTH=8 — attempting depth 9 must surface a user-visible error.
- Reusable / linked positions (v3036) — editing parent updates linked children.
- FX-correct CSV/Excel exports (#111) — verify decimal locale and currency column.
- Cycle detection — a parent_id cycle attempt must return 409.
- Section-scoped '+ Add position' (#149) — new row appears under the right section.

### Module: `assemblies`

- Backend: `backend/app/modules/assemblies/`
- Frontend: `frontend/src/features/assemblies/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 19

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `POST` | `/` |
| `GET` | `/` |
| `POST` | `/ai-generate/` |
| `GET` | `/stats/` |
| `GET` | `/{assembly_id}` |
| `PATCH` | `/{assembly_id}` |
| `DELETE` | `/{assembly_id}` |
| `POST` | `/{assembly_id}/components/` |
| `PATCH` | `/{assembly_id}/components/{component_id}` |
| `DELETE` | `/{assembly_id}/components/{component_id}` |
| `POST` | `/{assembly_id}/apply-to-boq/` |
| `POST` | `/{assembly_id}/clone/` |
| `POST` | `/{assembly_id}/reorder-components/` |
| `GET` | `/{assembly_id}/export/` |
| `POST` | `/import/` |
| `PATCH` | `/{assembly_id}/tags/` |
| `GET` | `/templates/` |
| `GET` | `/templates/{template_id}` |
| `POST` | `/templates/{template_id}/apply` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/assemblies/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `assemblies-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `assemblies-T002` | Open `assemblies` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `assemblies-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `assemblies-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `assemblies-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `assemblies-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `assemblies-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `assemblies-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `assemblies-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `assemblies-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `validation`

- Backend: `backend/app/modules/validation/`
- Frontend: `frontend/src/features/validation/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 9

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `POST` | `/run/` |
| `POST` | `/check-bim-model` |
| `GET` | `/reports/` |
| `GET` | `/reports/{report_id}` |
| `DELETE` | `/reports/{report_id}` |
| `POST` | `/import-ids` |
| `GET` | `/reports/{report_id}/sarif` |
| `GET` | `/rule-sets/` |
| `GET` | `/{report_id}/similar/` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/validation/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `validation-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `validation-T002` | Open `validation` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `validation-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `validation-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `validation-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `validation-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `validation-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `validation-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `validation-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `validation-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Batch `batch-04-costs-catalog-match-resources` — Costs, Catalog, Match Elements, Resources

**Summary**: CWICR cost DB browsing, catalog tooltip z-index regression, /match-elements 7-stage wizard, resource planning, supplier vendor management.

**Modules in this batch**: costs, catalog, cost_match, match, match_elements, resources, supplier_catalogs

**Estimated runner-minutes**: 200  
**Depends on**: batch-03-boq-suite

### Module: `costs`

- Backend: `backend/app/modules/costs/`
- Frontend: `frontend/src/features/costs/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 37

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/autocomplete/` |
| `POST` | `/` |
| `GET` | `/` |
| `GET` | `/regions/` |
| `GET` | `/regions/stats/` |
| `DELETE` | `/actions/clear-region/{region}` |
| `GET` | `/vector/status/` |
| `GET` | `/vector/download-status/` |
| `GET` | `/vector/regions/` |
| `GET` | `/vector/v3-status/` |
| `GET` | `/embedder/status/` |
| `GET` | `/qdrant-search/` |
| `POST` | `/vector/index/` |
| `POST` | `/vector/load-github/{db_id}` |
| `POST` | `/vector/restore-snapshot/{db_id}` |
| `GET` | `/catalogues-v3/` |
| `POST` | `/catalogues-v3/{region}/install` |
| `GET` | `/vector/search/` |
| `GET` | `/categories/` |
| `GET` | `/category-tree/` |
| … | (+17 more — see `router.py`) |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/costs/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `costs-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `costs-T002` | Open `costs` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `costs-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `costs-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `costs-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `costs-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `costs-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `costs-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `costs-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `costs-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `catalog`

- Backend: `backend/app/modules/catalog/`
- Frontend: `frontend/src/features/catalog/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 10

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `POST` | `/import/{region}` |
| `GET` | `/regions/` |
| `DELETE` | `/region/{region}` |
| `PATCH` | `/adjust-prices/` |
| `GET` | `/` |
| `GET` | `/stats/` |
| `GET` | `/{resource_id}/used-by/` |
| `GET` | `/{resource_id}` |
| `POST` | `/` |
| `POST` | `/extract/` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/catalog/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `catalog-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `catalog-T002` | Open `catalog` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `catalog-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `catalog-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `catalog-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `catalog-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `catalog-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `catalog-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `catalog-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `catalog-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `cost_match`

- Backend: `backend/app/modules/cost_match/`
- Frontend: `(API-only — no UI)`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 1

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/_health` |

**UI surface area**

- API-only module — no UI surface to test. Run API-only test path:
  - exercise every endpoint from above via `httpx` directly;
  - validate JSON schemas against `openapi.json`;
  - run regression matrix items reg-01, reg-02, reg-04, reg-05.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `cost-match-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `cost-match-T002` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `match`

- Backend: `backend/app/modules/match/`
- Frontend: `frontend/src/features/match/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 4

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `POST` | `/element` |
| `POST` | `/feedback` |
| `POST` | `/accept` |
| `GET` | `/_health` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/match/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `match-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `match-T002` | Open `match` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `match-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `match-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `match-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `match-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `match-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `match-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `match-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `match-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `match_elements`

- Backend: `backend/app/modules/match_elements/`
- Frontend: `frontend/src/features/match-elements/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 33

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `POST` | `/sessions` |
| `POST` | `/sessions/from-excel` |
| `GET` | `/sessions` |
| `GET` | `/sessions/{session_id}` |
| `PATCH` | `/sessions/{session_id}` |
| `POST` | `/sessions/{session_id}/touch` |
| `GET` | `/sessions/{session_id}/progress` |
| `POST` | `/sessions/{session_id}/__debug_set_progress` |
| `GET` | `/sessions/{session_id}/groups` |
| `GET` | `/sessions/{session_id}/group` |
| `POST` | `/sessions/{session_id}/groups/split` |
| `POST` | `/sessions/{session_id}/groups/merge` |
| `GET` | `/sessions/{session_id}/attributes` |
| `GET` | `/sessions/{session_id}/categories` |
| `GET` | `/projects/{project_id}/bim-models` |
| `POST` | `/sessions/{session_id}/match` |
| `POST` | `/sessions/{session_id}/confirm` |
| `POST` | `/sessions/{session_id}/bulk-confirm` |
| `POST` | `/sessions/{session_id}/apply` |
| `POST` | `/sessions/{session_id}/no-match` |
| … | (+13 more — see `router.py`) |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/match-elements/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `match-elements-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `match-elements-T002` | Open `match_elements` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `match-elements-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `match-elements-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `match-elements-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `match-elements-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `match-elements-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `match-elements-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `match-elements-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `match-elements-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `resources`

- Backend: `backend/app/modules/resources/`
- Frontend: `frontend/src/features/resources/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 50

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/resources/` |
| `POST` | `/resources/` |
| `GET` | `/resources/{resource_id}` |
| `PATCH` | `/resources/{resource_id}` |
| `DELETE` | `/resources/{resource_id}` |
| `GET` | `/resources/{resource_id}/dashboard` |
| `GET` | `/skills/` |
| `POST` | `/skills/` |
| `GET` | `/skills/{skill_id}` |
| `PATCH` | `/skills/{skill_id}` |
| `DELETE` | `/skills/{skill_id}` |
| `POST` | `/resources/{resource_id}/skills` |
| `GET` | `/resources/{resource_id}/skills` |
| `DELETE` | `/resources/{resource_id}/skills/{skill_id}` |
| `GET` | `/certifications/` |
| `GET` | `/certifications/expiring` |
| `POST` | `/certifications/` |
| `GET` | `/certifications/{cert_id}` |
| `PATCH` | `/certifications/{cert_id}` |
| `DELETE` | `/certifications/{cert_id}` |
| … | (+30 more — see `router.py`) |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/resources/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `resources-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `resources-T002` | Open `resources` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `resources-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `resources-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `resources-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `resources-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `resources-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `resources-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `resources-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `resources-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `supplier_catalogs`

- Backend: `backend/app/modules/supplier_catalogs/`
- Frontend: `frontend/src/features/supplier-catalogs/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 42

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `POST` | `/vendors` |
| `GET` | `/vendors` |
| `GET` | `/vendors/{vendor_id}` |
| `PATCH` | `/vendors/{vendor_id}` |
| `PATCH` | `/vendors/{vendor_id}/suspend` |
| `PATCH` | `/vendors/{vendor_id}/blacklist` |
| `POST` | `/vendors/{vendor_id}/rating` |
| `POST` | `/categories` |
| `POST` | `/catalog-items` |
| `GET` | `/catalog-items` |
| `GET` | `/catalog-items/{item_id}/price-comparison` |
| `POST` | `/price-lists/{vendor_id}` |
| `POST` | `/price-lists/{vendor_id}/import` |
| `POST` | `/prs` |
| `POST` | `/prs/{pr_id}/submit` |
| `POST` | `/prs/{pr_id}/approve` |
| `POST` | `/prs/{pr_id}/reject` |
| `POST` | `/prs/{pr_id}/convert-to-po` |
| `POST` | `/pos` |
| `POST` | `/pos/{po_id}/send` |
| … | (+22 more — see `router.py`) |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/supplier-catalogs/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `supplier-catalogs-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `supplier-catalogs-T002` | Open `supplier_catalogs` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `supplier-catalogs-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `supplier-catalogs-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `supplier-catalogs-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `supplier-catalogs-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `supplier-catalogs-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `supplier-catalogs-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `supplier-catalogs-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `supplier-catalogs-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Batch `batch-05-bim-cad-validation` — BIM Hub, BIM Models, CAD Import, Validation, Clash

**Summary**: BIM upload via DDC cad2data (NO IfcOpenShell), federations, properties panel, BCF round-trip, clash heatmaps, coordination thresholds.

**Modules in this batch**: bim_hub, bim_requirements, cad, validation, clash, clash_ai_triage, clash_cost_impact, coordination_hub, bcf

**Estimated runner-minutes**: 280  
**Depends on**: batch-02-projects-companies-contacts

### Module: `bim_hub`

- Backend: `backend/app/modules/bim_hub/`
- Frontend: `(API-only — no UI)`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 52

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `POST` | `/upload/` |
| `POST` | `/upload-cad/` |
| `POST` | `/{model_id}/generate-pdf-sheets/` |
| `POST` | `/{model_id}/retry/` |
| `GET` | `/models/{model_id}/geometry/` |
| `GET` | `/` |
| `POST` | `/` |
| `GET` | `/assets` |
| `PATCH` | `/assets/{element_id}/asset-info` |
| `GET` | `/{model_id}` |
| `PATCH` | `/{model_id}` |
| `GET` | `/models/{model_id}/schema/` |
| `DELETE` | `/{model_id}` |
| `POST` | `/cleanup-stale/` |
| `POST` | `/cleanup-orphans/` |
| `GET` | `/models/{model_id}/elements/` |
| `POST` | `/models/{model_id}/elements/` |
| `POST` | `/models/{model_id}/elements/by-ids/` |
| `POST` | `/models/{model_id}/ensure-element/` |
| `GET` | `/elements/{element_id}` |
| … | (+32 more — see `router.py`) |

**UI surface area**

- API-only module — no UI surface to test. Run API-only test path:
  - exercise every endpoint from above via `httpx` directly;
  - validate JSON schemas against `openapi.json`;
  - run regression matrix items reg-01, reg-02, reg-04, reg-05.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `bim-hub-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `bim-hub-T002` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- Magic-byte upload validation rejects non-IFC/RVT/DWG; serve-time validation too (v3.12.1).
- Converter cli tolerance — gracefully handle DDC cad2data returning empty geometry.
- Properties panel renders with no NaN values; orjson trap (feedback_no_orjson_default.md).

### Module: `bim_requirements`

- Backend: `backend/app/modules/bim_requirements/`
- Frontend: `frontend/src/features/bim_requirements/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 10

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `POST` | `/import/upload/` |
| `GET` | `/sets/` |
| `GET` | `/sets/{set_id}/` |
| `DELETE` | `/sets/{set_id}/` |
| `GET` | `/template/` |
| `POST` | `/export/{set_id}/excel/` |
| `POST` | `/export/{set_id}/ids/` |
| `POST` | `/validate/{set_id}/` |
| `POST` | `/preview-yaml/` |
| `POST` | `/install-from-yaml/` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/bim_requirements/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `bim-requirements-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `bim-requirements-T002` | Open `bim_requirements` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `bim-requirements-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `bim-requirements-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `bim-requirements-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `bim-requirements-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `bim-requirements-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `bim-requirements-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `bim-requirements-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `bim-requirements-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `cad`

- Backend: `backend/app/modules/cad/`
- Frontend: `(API-only — no UI)`
- Has router: NO
- Has manifest: YES
- Discovered endpoints: 0

**Public surface area (API endpoints discovered in `router.py`)**

_No `@router.<method>` decorators detected — module may use a different
registration style (sub-router include) or be API-only via service layer._

**UI surface area**

- API-only module — no UI surface to test. Run API-only test path:
  - exercise every endpoint from above via `httpx` directly;
  - validate JSON schemas against `openapi.json`;
  - run regression matrix items reg-01, reg-02, reg-04, reg-05.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `cad-T001` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `clash`

- Backend: `backend/app/modules/clash/`
- Frontend: `frontend/src/features/clash/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 24

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/projects/{project_id}/models` |
| `GET` | `/projects/{project_id}/categories` |
| `GET` | `/projects/{project_id}/runs/` |
| `POST` | `/projects/{project_id}/runs/` |
| `GET` | `/projects/{project_id}/runs/{run_id}` |
| `DELETE` | `/projects/{project_id}/runs/{run_id}` |
| `GET` | `/projects/{project_id}/runs/{run_id}/results` |
| `PATCH` | `/projects/{project_id}/runs/{run_id}/results/{result_id}` |
| `GET` | `/projects/{project_id}/runs/{run_id}/compare` |
| `GET` | `/projects/{project_id}/runs/{run_id}/export-csv` |
| `POST` | `/projects/{project_id}/runs/{run_id}/export-bcf` |
| `POST` | `/projects/{project_id}/runs/{run_id}/import-bcf` |
| `POST` | `/projects/{project_id}/runs/{run_id}/results/{result_id}/watch` |
| `DELETE` | `/projects/{project_id}/runs/{run_id}/results/{result_id}/watch` |
| `GET` | `/projects/{project_id}/runs/{run_id}/clusters` |
| `GET` | `/projects/{project_id}/runs/{run_id}/rule-suggestions` |
| `POST` | `/projects/{project_id}/runs/{run_id}/apply-rule-suggestion` |
| `GET` | `/projects/{project_id}/runs/{run_id}/rules` |
| `PATCH` | `/projects/{project_id}/runs/{run_id}/rules` |
| `GET` | `/issues` |
| … | (+4 more — see `router.py`) |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/clash/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `clash-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `clash-T002` | Open `clash` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `clash-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `clash-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `clash-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `clash-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `clash-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `clash-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `clash-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `clash-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `clash_ai_triage`

- Backend: `backend/app/modules/clash_ai_triage/`
- Frontend: `(API-only — no UI)`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 5

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `POST` | `/clashes/{clash_id}` |
| `POST` | `/batch` |
| `GET` | `/clashes/{clash_id}/history` |
| `GET` | `/prompts/current` |
| `POST` | `/replay/{triage_result_id}` |

**UI surface area**

- API-only module — no UI surface to test. Run API-only test path:
  - exercise every endpoint from above via `httpx` directly;
  - validate JSON schemas against `openapi.json`;
  - run regression matrix items reg-01, reg-02, reg-04, reg-05.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `clash-ai-triage-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `clash-ai-triage-T002` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `clash_cost_impact`

- Backend: `backend/app/modules/clash_cost_impact/`
- Frontend: `(API-only — no UI)`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 2

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/clash/{clash_id}/impact` |
| `GET` | `/project/{project_id}/rollup` |

**UI surface area**

- API-only module — no UI surface to test. Run API-only test path:
  - exercise every endpoint from above via `httpx` directly;
  - validate JSON schemas against `openapi.json`;
  - run regression matrix items reg-01, reg-02, reg-04, reg-05.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `clash-cost-impact-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `clash-cost-impact-T002` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `coordination_hub`

- Backend: `backend/app/modules/coordination_hub/`
- Frontend: `(API-only — no UI)`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 5

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/projects/{project_id}/dashboard` |
| `GET` | `/projects/{project_id}/trade-matrix` |
| `GET` | `/projects/{project_id}/timeline` |
| `GET` | `/projects/{project_id}/thresholds` |
| `PUT` | `/projects/{project_id}/thresholds/{metric}` |

**UI surface area**

- API-only module — no UI surface to test. Run API-only test path:
  - exercise every endpoint from above via `httpx` directly;
  - validate JSON schemas against `openapi.json`;
  - run regression matrix items reg-01, reg-02, reg-04, reg-05.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `coordination-hub-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `coordination-hub-T002` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `bcf`

- Backend: `backend/app/modules/bcf/`
- Frontend: `(API-only — no UI)`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 14

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/projects/{project_id}/topics/` |
| `POST` | `/projects/{project_id}/topics/` |
| `GET` | `/projects/{project_id}/topics/{topic_id}` |
| `PUT` | `/projects/{project_id}/topics/{topic_id}` |
| `DELETE` | `/projects/{project_id}/topics/{topic_id}` |
| `POST` | `/projects/{project_id}/topics/{topic_id}/comments/` |
| `PUT` | `/projects/{project_id}/topics/{topic_id}/comments/{comment_id}` |
| `DELETE` | `/projects/{project_id}/topics/{topic_id}/comments/{comment_id}` |
| `POST` | `/projects/{project_id}/topics/{topic_id}/viewpoints/` |
| `GET` | `/projects/{project_id}/topics/{topic_id}/viewpoints/{vp_guid}/snapshot` |
| `GET` | `/projects/{project_id}/export` |
| `POST` | `/projects/{project_id}/import` |
| `GET` | `/export/clashes` |
| `POST` | `/import/clashes` |

**UI surface area**

- API-only module — no UI surface to test. Run API-only test path:
  - exercise every endpoint from above via `httpx` directly;
  - validate JSON schemas against `openapi.json`;
  - run regression matrix items reg-01, reg-02, reg-04, reg-05.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `bcf-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `bcf-T002` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Batch `batch-06-takeoff` — Takeoff (manual + DWG + PDF + CV)

**Summary**: PDF.js + Canvas overlay, click-to-measure, AI suggestion overlay, numeric measurement persistence (v3111), markups module.

**Modules in this batch**: takeoff, dwg_takeoff, markups

**Estimated runner-minutes**: 180  
**Depends on**: batch-03-boq-suite

### Module: `takeoff`

- Backend: `backend/app/modules/takeoff/`
- Frontend: `frontend/src/features/takeoff/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 38

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/converters/` |
| `POST` | `/converters/{converter_id}/verify/` |
| `GET` | `/converters/{converter_id}/install-progress/` |
| `POST` | `/converters/{converter_id}/install/` |
| `POST` | `/converters/manifest/install/{component_name}` |
| `POST` | `/converters/{converter_id}/uninstall/` |
| `POST` | `/cad-extract/` |
| `POST` | `/cad-columns/` |
| `POST` | `/cad-group/` |
| `POST` | `/cad-group/elements/` |
| `POST` | `/cad-group/create-boq/` |
| `GET` | `/cad-group/export/` |
| `POST` | `/cad-data/describe/` |
| `GET` | `/cad-data/missingness/` |
| `POST` | `/cad-data/value-counts/` |
| `GET` | `/cad-data/elements/` |
| `POST` | `/cad-data/aggregate/` |
| `POST` | `/cad-data/save/` |
| `POST` | `/cad-data/from-bim-model/` |
| `GET` | `/cad-data/sessions/` |
| … | (+18 more — see `router.py`) |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/takeoff/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `takeoff-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `takeoff-T002` | Open `takeoff` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `takeoff-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `takeoff-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `takeoff-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `takeoff-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `takeoff-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `takeoff-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `takeoff-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `takeoff-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `dwg_takeoff`

- Backend: `backend/app/modules/dwg_takeoff/`
- Frontend: `frontend/src/features/dwg-takeoff/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 18

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `POST` | `/drawings/upload/` |
| `GET` | `/drawings/` |
| `GET` | `/drawings/{drawing_id}` |
| `DELETE` | `/drawings/{drawing_id}` |
| `GET` | `/drawings/{drawing_id}/entities/` |
| `GET` | `/drawings/{drawing_id}/thumbnail/` |
| `PATCH` | `/drawings/{drawing_id}/scale/` |
| `PATCH` | `/drawings/{drawing_id}/layers` |
| `POST` | `/annotations/` |
| `GET` | `/annotations/` |
| `PATCH` | `/annotations/{annotation_id}` |
| `DELETE` | `/annotations/{annotation_id}` |
| `POST` | `/annotations/{annotation_id}/link-boq/` |
| `GET` | `/pins/` |
| `POST` | `/groups/` |
| `GET` | `/groups/` |
| `DELETE` | `/groups/{group_id}` |
| `GET` | `/offline-readiness/` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/dwg-takeoff/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `dwg-takeoff-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `dwg-takeoff-T002` | Open `dwg_takeoff` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `dwg-takeoff-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `dwg-takeoff-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `dwg-takeoff-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `dwg-takeoff-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `dwg-takeoff-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `dwg-takeoff-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `dwg-takeoff-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `dwg-takeoff-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `markups`

- Backend: `backend/app/modules/markups/`
- Frontend: `frontend/src/features/markups/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 19

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/summary/` |
| `GET` | `/export/` |
| `POST` | `/bulk/` |
| `POST` | `/` |
| `GET` | `/` |
| `GET` | `/{markup_id}` |
| `PATCH` | `/{markup_id}` |
| `DELETE` | `/{markup_id}` |
| `POST` | `/{markup_id}/link-to-boq/` |
| `POST` | `/scales/` |
| `GET` | `/scales/` |
| `DELETE` | `/scales/{config_id}` |
| `POST` | `/stamps/templates/` |
| `GET` | `/stamps/templates/` |
| `PATCH` | `/stamps/templates/{template_id}` |
| `DELETE` | `/stamps/templates/{template_id}` |
| `GET` | `/{markup_id}/comments/` |
| `POST` | `/{markup_id}/comments/` |
| `DELETE` | `/{markup_id}/comments/{comment_id}/` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/markups/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `markups-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `markups-T002` | Open `markups` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `markups-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `markups-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `markups-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `markups-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `markups-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `markups-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `markups-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `markups-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Batch `batch-07-propdev` — Property Development — Lead → Warranty + Accommodation

**Summary**: Complete PropDev clickflow (Lead/Qualified/Reservation/SPA/Handover/Warranty), House Types, custom templates, dashboards (Funnel/Velocity/Heatmap), Accommodation calendar view, buyer portal magic-link, webhook leads ingest.

**Modules in this batch**: property_dev, accommodation, portal, webhook_leads

**Estimated runner-minutes**: 360  
**Depends on**: batch-02-projects-companies-contacts

### Module: `property_dev`

- Backend: `backend/app/modules/property_dev/`
- Frontend: `frontend/src/features/property-dev/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 199

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/developments/` |
| `POST` | `/developments/` |
| `GET` | `/developments/{dev_id}` |
| `PATCH` | `/developments/{dev_id}` |
| `DELETE` | `/developments/{dev_id}` |
| `GET` | `/developments/{dev_id}/dashboard` |
| `GET` | `/developments/{dev_id}/sales-dashboard` |
| `GET` | `/plots/` |
| `POST` | `/plots/` |
| `GET` | `/plots/{plot_id}` |
| `PATCH` | `/plots/{plot_id}` |
| `DELETE` | `/plots/{plot_id}` |
| `POST` | `/plots/{plot_id}/reserve` |
| `GET` | `/plots/{plot_id}/configurator` |
| `GET` | `/house-types/` |
| `POST` | `/house-types/` |
| `GET` | `/house-types/{ht_id}` |
| `PATCH` | `/house-types/{ht_id}` |
| `DELETE` | `/house-types/{ht_id}` |
| `GET` | `/house-type-catalogue/` |
| … | (+179 more — see `router.py`) |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/property-dev/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `property-dev-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `property-dev-T002` | Open `property_dev` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `property-dev-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `property-dev-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `property-dev-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `property-dev-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `property-dev-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `property-dev-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `property-dev-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `property-dev-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- Complete Lead → Qualified → Reservation → SPA → Handover → Warranty clickflow.
- House Types — CountryCombobox + parking_spots field (v3119).
- Custom doc-template upload (v3116) — round-trip render.
- Snag photo magic-byte validation (v3110).

### Module: `accommodation`

- Backend: `backend/app/modules/accommodation/`
- Frontend: `frontend/src/features/accommodation/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 17

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/` |
| `POST` | `/` |
| `GET` | `/{accommodation_id}` |
| `PATCH` | `/{accommodation_id}` |
| `DELETE` | `/{accommodation_id}` |
| `GET` | `/{accommodation_id}/bookings` |
| `POST` | `/{accommodation_id}/rooms` |
| `GET` | `/{accommodation_id}/rooms` |
| `PATCH` | `/rooms/{room_id}` |
| `GET` | `/rooms/{room_id}/bookings` |
| `POST` | `/rooms/{room_id}/bookings` |
| `GET` | `/bookings/{booking_id}` |
| `PATCH` | `/bookings/{booking_id}` |
| `POST` | `/bookings/{booking_id}/charges` |
| `GET` | `/bookings/{booking_id}/charges` |
| `POST` | `/{accommodation_id}/bootstrap-from-propdev/{block_id}` |
| `POST` | `/bookings/suggest-from-hr` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/accommodation/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `accommodation-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `accommodation-T002` | Open `accommodation` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `accommodation-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `accommodation-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `accommodation-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `accommodation-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `accommodation-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `accommodation-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `accommodation-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `accommodation-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- Booking state machine: reserved → checked_in → checked_out (or cancelled from non-final).
- Booking into maintenance/blocked room → 409.
- Half-open date overlap semantics with NULL check_out.
- PropDev bootstrap is idempotent on label.
- HR autobook is suggest-confirm (no auto-action).

### Module: `portal`

- Backend: `backend/app/modules/portal/`
- Frontend: `frontend/src/features/portal/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 21

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `POST` | `/admin/users/invite` |
| `GET` | `/admin/users` |
| `GET` | `/admin/users/{portal_user_id}` |
| `PATCH` | `/admin/users/{portal_user_id}` |
| `POST` | `/admin/users/{portal_user_id}/resend-invite` |
| `POST` | `/admin/access-rules` |
| `GET` | `/admin/access-rules` |
| `DELETE` | `/admin/access-rules/{rule_id}` |
| `GET` | `/admin/document-access-log` |
| `POST` | `/auth/magic-link` |
| `POST` | `/auth/consume` |
| `POST` | `/auth/logout` |
| `GET` | `/me` |
| `GET` | `/me/accessible/{resource_type}` |
| `GET` | `/me/notifications` |
| `POST` | `/me/notifications/{notification_id}/read` |
| `POST` | `/me/document-access` |
| `PATCH` | `/me` |
| `POST` | `/me/tickets` |
| `GET` | `/me/tickets` |
| … | (+1 more — see `router.py`) |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/portal/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `portal-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `portal-T002` | Open `portal` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `portal-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `portal-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `portal-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `portal-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `portal-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `portal-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `portal-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `portal-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `webhook_leads`

- Backend: `backend/app/modules/webhook_leads/`
- Frontend: `(API-only — no UI)`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 12

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `POST` | `/incoming/{source_slug}/` |
| `GET` | `/sources/` |
| `POST` | `/sources/` |
| `GET` | `/sources/{source_id}` |
| `PATCH` | `/sources/{source_id}` |
| `POST` | `/sources/{source_id}/rotate-secret` |
| `DELETE` | `/sources/{source_id}` |
| `GET` | `/sources/{source_id}/mappings/` |
| `POST` | `/sources/{source_id}/mappings/` |
| `PATCH` | `/mappings/{mapping_id}` |
| `DELETE` | `/mappings/{mapping_id}` |
| `GET` | `/logs/` |

**UI surface area**

- API-only module — no UI surface to test. Run API-only test path:
  - exercise every endpoint from above via `httpx` directly;
  - validate JSON schemas against `openapi.json`;
  - run regression matrix items reg-01, reg-02, reg-04, reg-05.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `webhook-leads-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `webhook-leads-T002` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Batch `batch-08-crm-sales-pipeline` — CRM, Sales Pipeline, Activities

**Summary**: CRM lead dedup (v3122 active_email_unique), money decimal-as-string, PII redaction, GDPR forget, WIN role gate, sales pipeline drag.

**Modules in this batch**: crm, pipelines

**Estimated runner-minutes**: 150  
**Depends on**: batch-02-projects-companies-contacts

### Module: `crm`

- Backend: `backend/app/modules/crm/`
- Frontend: `frontend/src/features/crm/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 47

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/accounts/` |
| `POST` | `/accounts/` |
| `GET` | `/accounts/tree` |
| `GET` | `/accounts/{account_id}` |
| `PATCH` | `/accounts/{account_id}` |
| `DELETE` | `/accounts/{account_id}` |
| `GET` | `/leads/` |
| `POST` | `/leads/` |
| `GET` | `/leads/{lead_id}` |
| `PATCH` | `/leads/{lead_id}` |
| `DELETE` | `/leads/{lead_id}` |
| `POST` | `/leads/{lead_id}/forget` |
| `POST` | `/leads/{lead_id}/qualify` |
| `POST` | `/leads/{lead_id}/disqualify` |
| `POST` | `/leads/{lead_id}/convert` |
| `GET` | `/opportunities/` |
| `POST` | `/opportunities/` |
| `GET` | `/opportunities/{opportunity_id}` |
| `PATCH` | `/opportunities/{opportunity_id}` |
| `DELETE` | `/opportunities/{opportunity_id}` |
| … | (+27 more — see `router.py`) |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/crm/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `crm-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `crm-T002` | Open `crm` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `crm-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `crm-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `crm-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `crm-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `crm-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `crm-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `crm-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `crm-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- Lead dedup — same email twice on active leads must 409 (v3122 unique constraint).
- Money fields Decimal-as-string (test_crm_money_decimal).
- PII redaction in logs.
- GDPR forget — verify hard-delete + audit-marker.
- WIN role gate — only MANAGER can move to WIN.

### Module: `pipelines`

- Backend: `backend/app/modules/pipelines/`
- Frontend: `frontend/src/features/pipelines/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 9

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/node-types/` |
| `GET` | `/runs/{run_id}` |
| `GET` | `/` |
| `POST` | `/` |
| `GET` | `/{pipeline_id}` |
| `PUT` | `/{pipeline_id}` |
| `DELETE` | `/{pipeline_id}` |
| `POST` | `/{pipeline_id}/run` |
| `GET` | `/{pipeline_id}/runs/` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/pipelines/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `pipelines-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `pipelines-T002` | Open `pipelines` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `pipelines-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `pipelines-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `pipelines-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `pipelines-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `pipelines-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `pipelines-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `pipelines-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `pipelines-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Batch `batch-09-procurement-subs-bids` — Procurement, Subcontractors, Bid Management, RFQ

**Summary**: Procurement workflow, subcontractor onboarding, bid invitations + quote upload + award, RFQ/RFP packages, tender export (GAEB).

**Modules in this batch**: procurement, subcontractors, bid_management, rfq_bidding, tendering

**Estimated runner-minutes**: 220  
**Depends on**: batch-03-boq-suite

### Module: `procurement`

- Backend: `backend/app/modules/procurement/`
- Frontend: `frontend/src/features/procurement/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 12

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/` |
| `POST` | `/` |
| `GET` | `/stats/` |
| `GET` | `/goods-receipts/` |
| `POST` | `/goods-receipts/` |
| `POST` | `/goods-receipts/{gr_id}/confirm/` |
| `GET` | `/suppliers/{contact_id}/scorecard/` |
| `GET` | `/{po_id}` |
| `PATCH` | `/{po_id}` |
| `POST` | `/{po_id}/create-invoice/` |
| `GET` | `/{po_id}/match-status/` |
| `POST` | `/{po_id}/issue/` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/procurement/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `procurement-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `procurement-T002` | Open `procurement` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `procurement-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `procurement-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `procurement-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `procurement-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `procurement-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `procurement-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `procurement-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `procurement-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `subcontractors`

- Backend: `backend/app/modules/subcontractors/`
- Frontend: `frontend/src/features/subcontractors/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 46

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/subcontractors/` |
| `POST` | `/subcontractors/` |
| `GET` | `/subcontractors/{sub_id}` |
| `PATCH` | `/subcontractors/{sub_id}` |
| `DELETE` | `/subcontractors/{sub_id}` |
| `GET` | `/subcontractors/{sub_id}/dashboard` |
| `GET` | `/subcontractors/{sub_id}/contacts` |
| `POST` | `/contacts/` |
| `PATCH` | `/contacts/{contact_id}` |
| `DELETE` | `/contacts/{contact_id}` |
| `GET` | `/prequalifications/` |
| `POST` | `/prequalifications/` |
| `PATCH` | `/prequalifications/{prequal_id}` |
| `POST` | `/prequalifications/{prequal_id}/submit` |
| `POST` | `/prequalifications/{prequal_id}/approve` |
| `POST` | `/prequalifications/{prequal_id}/reject` |
| `GET` | `/certificates/` |
| `GET` | `/certificates/expiring` |
| `POST` | `/certificates/` |
| `PATCH` | `/certificates/{certificate_id}` |
| … | (+26 more — see `router.py`) |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/subcontractors/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `subcontractors-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `subcontractors-T002` | Open `subcontractors` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `subcontractors-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `subcontractors-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `subcontractors-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `subcontractors-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `subcontractors-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `subcontractors-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `subcontractors-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `subcontractors-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `bid_management`

- Backend: `backend/app/modules/bid_management/`
- Frontend: `frontend/src/features/bid-management/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 59

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/bid-packages/` |
| `POST` | `/bid-packages/` |
| `GET` | `/bid-packages/{package_id}` |
| `PATCH` | `/bid-packages/{package_id}` |
| `DELETE` | `/bid-packages/{package_id}` |
| `POST` | `/bid-packages/{package_id}/publish` |
| `POST` | `/bid-packages/{package_id}/open-bids` |
| `POST` | `/bid-packages/{package_id}/close` |
| `POST` | `/bid-packages/{package_id}/cancel` |
| `POST` | `/bid-packages/{package_id}/award` |
| `GET` | `/bid-packages/{package_id}/dashboard` |
| `GET` | `/bid-packages/{package_id}/analytics` |
| `GET` | `/bid-packages/{package_id}/leveling-matrix` |
| `GET` | `/bid-packages/{package_id}/qa-board` |
| `POST` | `/bid-packages/{package_id}/send-invitations` |
| `POST` | `/bid-packages/{package_id}/scorecards` |
| `GET` | `/bid-package-line-items/` |
| `POST` | `/bid-package-line-items/` |
| `POST` | `/bid-packages/{package_id}/lines/bulk` |
| `PATCH` | `/bid-package-line-items/{line_id}` |
| … | (+39 more — see `router.py`) |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/bid-management/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `bid-management-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `bid-management-T002` | Open `bid_management` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `bid-management-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `bid-management-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `bid-management-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `bid-management-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `bid-management-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `bid-management-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `bid-management-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `bid-management-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `rfq_bidding`

- Backend: `backend/app/modules/rfq_bidding/`
- Frontend: `(API-only — no UI)`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 11

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/` |
| `POST` | `/` |
| `GET` | `/{rfq_id}` |
| `PATCH` | `/{rfq_id}` |
| `DELETE` | `/{rfq_id}` |
| `POST` | `/{rfq_id}/issue/` |
| `GET` | `/bids/` |
| `POST` | `/bids/` |
| `GET` | `/bids/{bid_id}` |
| `POST` | `/bids/{bid_id}/evaluate/` |
| `POST` | `/bids/{bid_id}/award/` |

**UI surface area**

- API-only module — no UI surface to test. Run API-only test path:
  - exercise every endpoint from above via `httpx` directly;
  - validate JSON schemas against `openapi.json`;
  - run regression matrix items reg-01, reg-02, reg-04, reg-05.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `rfq-bidding-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `rfq-bidding-T002` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `tendering`

- Backend: `backend/app/modules/tendering/`
- Frontend: `frontend/src/features/tendering/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 12

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/` |
| `POST` | `/packages/` |
| `GET` | `/packages/` |
| `GET` | `/packages/{package_id}` |
| `PATCH` | `/packages/{package_id}` |
| `POST` | `/packages/{package_id}/bids/` |
| `GET` | `/packages/{package_id}/bids/` |
| `PATCH` | `/bids/{bid_id}` |
| `GET` | `/packages/{package_id}/comparison/` |
| `POST` | `/packages/{package_id}/apply-winner/` |
| `GET` | `/packages/{package_id}/export/pdf/` |
| `GET` | `/bid-analysis/` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/tendering/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `tendering-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `tendering-T002` | Open `tendering` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `tendering-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `tendering-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `tendering-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `tendering-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `tendering-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `tendering-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `tendering-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `tendering-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Batch `batch-10-schedule-workorders-risk` — Schedule, Schedule Advanced (Last Planner), Tasks, Risk

**Summary**: 4D Schedule with CPM weekly, Last Planner lookahead, task Kanban/Gantt, risk register heatmap, background jobs panel.

**Modules in this batch**: schedule, schedule_advanced, tasks, risk, jobs

**Estimated runner-minutes**: 220  
**Depends on**: batch-02-projects-companies-contacts

### Module: `schedule`

- Backend: `backend/app/modules/schedule/`
- Frontend: `frontend/src/features/schedule/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 40

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `POST` | `/schedules/` |
| `GET` | `/schedules/` |
| `GET` | `/schedules/{schedule_id}` |
| `PATCH` | `/schedules/{schedule_id}` |
| `DELETE` | `/schedules/{schedule_id}` |
| `POST` | `/schedules/{schedule_id}/activities/` |
| `GET` | `/schedules/{schedule_id}/activities/` |
| `GET` | `/schedules/{schedule_id}/gantt/` |
| `POST` | `/schedules/{schedule_id}/generate-from-boq/` |
| `POST` | `/schedules/{schedule_id}/calculate-cpm/` |
| `GET` | `/schedules/{schedule_id}/risk-analysis/` |
| `PATCH` | `/activities/{activity_id}` |
| `DELETE` | `/activities/{activity_id}` |
| `POST` | `/activities/{activity_id}/link-position/` |
| `PATCH` | `/activities/{activity_id}/progress/` |
| `PATCH` | `/activities/{activity_id}/bim-links/` |
| `GET` | `/activities/by-bim-element/` |
| `POST` | `/activities/{activity_id}/work-orders/` |
| `GET` | `/work-orders/` |
| `PATCH` | `/work-orders/{work_order_id}` |
| … | (+20 more — see `router.py`) |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/schedule/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `schedule-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `schedule-T002` | Open `schedule` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `schedule-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `schedule-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `schedule-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `schedule-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `schedule-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `schedule-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `schedule-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `schedule-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `schedule_advanced`

- Backend: `backend/app/modules/schedule_advanced/`
- Frontend: `frontend/src/features/schedule-advanced/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 73

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/master-schedules/` |
| `POST` | `/master-schedules/` |
| `GET` | `/master-schedules/{master_id}` |
| `PATCH` | `/master-schedules/{master_id}` |
| `DELETE` | `/master-schedules/{master_id}` |
| `GET` | `/master-schedules/{master_id}/dashboard` |
| `GET` | `/phase-plans/` |
| `POST` | `/phase-plans/` |
| `GET` | `/phase-plans/{phase_id}` |
| `PATCH` | `/phase-plans/{phase_id}` |
| `DELETE` | `/phase-plans/{phase_id}` |
| `POST` | `/phase-plans/{phase_id}/pull` |
| `POST` | `/phase-plans/{phase_id}/start` |
| `POST` | `/phase-plans/{phase_id}/complete` |
| `GET` | `/look-aheads/` |
| `GET` | `/look-aheads/current` |
| `POST` | `/look-aheads/` |
| `GET` | `/look-aheads/{la_id}` |
| `PATCH` | `/look-aheads/{la_id}` |
| `DELETE` | `/look-aheads/{la_id}` |
| … | (+53 more — see `router.py`) |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/schedule-advanced/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `schedule-advanced-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `schedule-advanced-T002` | Open `schedule_advanced` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `schedule-advanced-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `schedule-advanced-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `schedule-advanced-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `schedule-advanced-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `schedule-advanced-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `schedule-advanced-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `schedule-advanced-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `schedule-advanced-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `tasks`

- Backend: `backend/app/modules/tasks/`
- Frontend: `frontend/src/features/tasks/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 16

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/` |
| `GET` | `/my-tasks/` |
| `POST` | `/` |
| `GET` | `/stats/` |
| `GET` | `/export/` |
| `GET` | `/template/` |
| `POST` | `/import/file/` |
| `POST` | `/batch/delete/` |
| `PATCH` | `/batch/status/` |
| `POST` | `/batch/assign/` |
| `GET` | `/{task_id}` |
| `PATCH` | `/{task_id}` |
| `DELETE` | `/{task_id}` |
| `POST` | `/{task_id}/complete/` |
| `PATCH` | `/{task_id}/bim-links/` |
| `GET` | `/{task_id}/similar/` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/tasks/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `tasks-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `tasks-T002` | Open `tasks` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `tasks-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `tasks-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `tasks-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `tasks-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `tasks-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `tasks-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `tasks-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `tasks-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `risk`

- Backend: `backend/app/modules/risk/`
- Frontend: `frontend/src/features/risk/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 11

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/summary/` |
| `GET` | `/matrix/` |
| `POST` | `/` |
| `GET` | `/` |
| `POST` | `/projects/{project_id}/simulate` |
| `POST` | `/batch/delete/` |
| `PATCH` | `/batch/status/` |
| `GET` | `/{risk_id}` |
| `PATCH` | `/{risk_id}` |
| `DELETE` | `/{risk_id}` |
| `GET` | `/{risk_id}/similar/` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/risk/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `risk-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `risk-T002` | Open `risk` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `risk-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `risk-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `risk-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `risk-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `risk-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `risk-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `risk-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `risk-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `jobs`

- Backend: `backend/app/modules/jobs/`
- Frontend: `(API-only — no UI)`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 3

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/{job_id}` |
| `GET` | `/` |
| `POST` | `/{job_id}/cancel` |

**UI surface area**

- API-only module — no UI surface to test. Run API-only test path:
  - exercise every endpoint from above via `httpx` directly;
  - validate JSON schemas against `openapi.json`;
  - run regression matrix items reg-01, reg-02, reg-04, reg-05.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `jobs-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `jobs-T002` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Batch `batch-11-qms-hse-field` — QMS, HSE, HSE Advanced, Daily Diary, Snag List, Punchlist, Field Reports, Inspections, NCR, Safety, Service, Equipment

**Summary**: Quality + safety + field surfaces. Incident logging, corrective actions, snag photos, punchlist resolution, daily diary, NCR raise/close, equipment fleet, service maintenance.

**Modules in this batch**: qms, hse_advanced, safety, daily_diary, punchlist, fieldreports, inspections, ncr, service, equipment

**Estimated runner-minutes**: 320  
**Depends on**: batch-02-projects-companies-contacts

### Module: `qms`

- Backend: `backend/app/modules/qms/`
- Frontend: `frontend/src/features/qms/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 42

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/itp-plans` |
| `POST` | `/itp-plans` |
| `POST` | `/itp-plans/{plan_id}/items` |
| `POST` | `/itp-plans/{plan_id}/activate` |
| `GET` | `/inspections` |
| `POST` | `/inspections` |
| `POST` | `/inspections/{inspection_id}/sign` |
| `POST` | `/inspections/{inspection_id}/complete` |
| `PATCH` | `/inspections/{inspection_id}` |
| `GET` | `/ncrs` |
| `POST` | `/ncrs` |
| `PATCH` | `/ncrs/{ncr_id}` |
| `POST` | `/ncrs/{ncr_id}/actions` |
| `POST` | `/ncrs/{ncr_id}/escalate-to-variation` |
| `POST` | `/ncrs/{ncr_id}/close` |
| `GET` | `/punch-items` |
| `POST` | `/punch-items` |
| `PATCH` | `/punch-items/{punch_id}/assign` |
| `PATCH` | `/punch-items/{punch_id}` |
| `POST` | `/punch-items/{punch_id}/close` |
| … | (+22 more — see `router.py`) |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/qms/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `qms-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `qms-T002` | Open `qms` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `qms-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `qms-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `qms-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `qms-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `qms-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `qms-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `qms-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `qms-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `hse_advanced`

- Backend: `backend/app/modules/hse_advanced/`
- Frontend: `frontend/src/features/hse-advanced/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 81

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/investigations/` |
| `POST` | `/investigations/` |
| `GET` | `/investigations/{item_id}` |
| `PATCH` | `/investigations/{item_id}` |
| `POST` | `/investigations/{item_id}/complete` |
| `POST` | `/investigations/{item_id}/abandon` |
| `GET` | `/jsa/` |
| `POST` | `/jsa/` |
| `GET` | `/jsa/{item_id}` |
| `PATCH` | `/jsa/{item_id}` |
| `DELETE` | `/jsa/{item_id}` |
| `POST` | `/jsa/{item_id}/submit` |
| `POST` | `/jsa/{item_id}/approve` |
| `POST` | `/jsa/{item_id}/activate` |
| `POST` | `/jsa/{item_id}/archive` |
| `GET` | `/permits/` |
| `POST` | `/permits/` |
| `GET` | `/permits/{item_id}` |
| `PATCH` | `/permits/{item_id}` |
| `DELETE` | `/permits/{item_id}` |
| … | (+61 more — see `router.py`) |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/hse-advanced/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `hse-advanced-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `hse-advanced-T002` | Open `hse_advanced` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `hse-advanced-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `hse-advanced-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `hse-advanced-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `hse-advanced-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `hse-advanced-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `hse-advanced-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `hse-advanced-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `hse-advanced-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `safety`

- Backend: `backend/app/modules/safety/`
- Frontend: `frontend/src/features/safety/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 14

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/stats/` |
| `GET` | `/trends/` |
| `GET` | `/incidents/` |
| `POST` | `/incidents/` |
| `GET` | `/incidents/export/` |
| `GET` | `/incidents/{incident_id}` |
| `PATCH` | `/incidents/{incident_id}` |
| `DELETE` | `/incidents/{incident_id}` |
| `GET` | `/observations/` |
| `POST` | `/observations/` |
| `GET` | `/observations/export/` |
| `GET` | `/observations/{observation_id}` |
| `PATCH` | `/observations/{observation_id}` |
| `DELETE` | `/observations/{observation_id}` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/safety/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `safety-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `safety-T002` | Open `safety` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `safety-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `safety-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `safety-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `safety-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `safety-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `safety-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `safety-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `safety-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `daily_diary`

- Backend: `backend/app/modules/daily_diary/`
- Frontend: `frontend/src/features/daily-diary/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 54

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/diaries/` |
| `POST` | `/diaries/` |
| `GET` | `/diaries/{diary_id}` |
| `PATCH` | `/diaries/{diary_id}` |
| `DELETE` | `/diaries/{diary_id}` |
| `POST` | `/diaries/{diary_id}/close` |
| `POST` | `/diaries/{diary_id}/sign` |
| `POST` | `/diaries/{diary_id}/unlock` |
| `POST` | `/diaries/{diary_id}/archive` |
| `GET` | `/diaries/{diary_id}/completeness` |
| `GET` | `/diaries/{diary_id}/immutable-payload-hash` |
| `GET` | `/diaries/{diary_id}/pdf-stub` |
| `GET` | `/weather/today` |
| `POST` | `/weather-records/` |
| `GET` | `/weather-records/{weather_id}` |
| `PATCH` | `/weather-records/{weather_id}` |
| `DELETE` | `/weather-records/{weather_id}` |
| `POST` | `/diary-entries/` |
| `GET` | `/diaries/{diary_id}/entries` |
| `POST` | `/diaries/{diary_id}/entries/bulk` |
| … | (+34 more — see `router.py`) |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/daily-diary/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `daily-diary-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `daily-diary-T002` | Open `daily_diary` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `daily-diary-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `daily-diary-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `daily-diary-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `daily-diary-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `daily-diary-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `daily-diary-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `daily-diary-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `daily-diary-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `punchlist`

- Backend: `backend/app/modules/punchlist/`
- Frontend: `frontend/src/features/punchlist/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 15

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/summary/` |
| `POST` | `/items/` |
| `GET` | `/items/` |
| `GET` | `/` |
| `POST` | `/` |
| `GET` | `/items/{item_id}` |
| `PATCH` | `/items/{item_id}` |
| `DELETE` | `/items/{item_id}` |
| `POST` | `/items/{item_id}/transition/` |
| `POST` | `/items/{item_id}/pin-to-sheet/` |
| `POST` | `/items/{item_id}/photos/` |
| `DELETE` | `/items/{item_id}/photos/{index}` |
| `POST` | `/bulk-close/` |
| `GET` | `/export/pdf/` |
| `GET` | `/export/excel/` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/punchlist/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `punchlist-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `punchlist-T002` | Open `punchlist` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `punchlist-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `punchlist-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `punchlist-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `punchlist-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `punchlist-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `punchlist-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `punchlist-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `punchlist-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `fieldreports`

- Backend: `backend/app/modules/fieldreports/`
- Frontend: `frontend/src/features/fieldreports/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 29

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/reports/summary/` |
| `GET` | `/reports/calendar/` |
| `GET` | `/weather/` |
| `GET` | `/reports/template/` |
| `POST` | `/reports/import/file/` |
| `GET` | `/reports/export/` |
| `POST` | `/reports/` |
| `GET` | `/reports/` |
| `GET` | `/reports/{report_id}` |
| `PATCH` | `/reports/{report_id}` |
| `DELETE` | `/reports/{report_id}` |
| `POST` | `/reports/{report_id}/submit/` |
| `POST` | `/reports/{report_id}/approve/` |
| `POST` | `/reports/{report_id}/link-documents/` |
| `GET` | `/reports/{report_id}/documents/` |
| `GET` | `/reports/{report_id}/export/pdf/` |
| `GET` | `/templates/` |
| `POST` | `/templates/` |
| `GET` | `/templates/{template_id}` |
| `PATCH` | `/templates/{template_id}` |
| … | (+9 more — see `router.py`) |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/fieldreports/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `fieldreports-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `fieldreports-T002` | Open `fieldreports` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `fieldreports-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `fieldreports-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `fieldreports-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `fieldreports-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `fieldreports-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `fieldreports-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `fieldreports-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `fieldreports-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `inspections`

- Backend: `backend/app/modules/inspections/`
- Frontend: `frontend/src/features/inspections/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 9

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/` |
| `POST` | `/` |
| `GET` | `/export/` |
| `GET` | `/{inspection_id}` |
| `PATCH` | `/{inspection_id}` |
| `DELETE` | `/{inspection_id}` |
| `POST` | `/{inspection_id}/create-defect/` |
| `POST` | `/{inspection_id}/create-ncr/` |
| `POST` | `/{inspection_id}/complete/` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/inspections/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `inspections-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `inspections-T002` | Open `inspections` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `inspections-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `inspections-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `inspections-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `inspections-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `inspections-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `inspections-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `inspections-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `inspections-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `ncr`

- Backend: `backend/app/modules/ncr/`
- Frontend: `frontend/src/features/ncr/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 7

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/` |
| `POST` | `/` |
| `GET` | `/{ncr_id}` |
| `PATCH` | `/{ncr_id}` |
| `DELETE` | `/{ncr_id}` |
| `POST` | `/{ncr_id}/create-variation/` |
| `POST` | `/{ncr_id}/close/` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/ncr/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `ncr-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `ncr-T002` | Open `ncr` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `ncr-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `ncr-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `ncr-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `ncr-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `ncr-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `ncr-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `ncr-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `ncr-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `service`

- Backend: `backend/app/modules/service/`
- Frontend: `frontend/src/features/service/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 52

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/contracts/` |
| `POST` | `/contracts/` |
| `GET` | `/contracts/{contract_id}` |
| `PATCH` | `/contracts/{contract_id}` |
| `DELETE` | `/contracts/{contract_id}` |
| `POST` | `/contracts/{contract_id}/close` |
| `GET` | `/contracts/{contract_id}/dashboard` |
| `GET` | `/assets/` |
| `POST` | `/assets/` |
| `GET` | `/assets/{asset_id}` |
| `PATCH` | `/assets/{asset_id}` |
| `DELETE` | `/assets/{asset_id}` |
| `GET` | `/tickets/` |
| `POST` | `/tickets/` |
| `GET` | `/tickets/{ticket_id}` |
| `PATCH` | `/tickets/{ticket_id}` |
| `DELETE` | `/tickets/{ticket_id}` |
| `POST` | `/tickets/{ticket_id}/dispatch` |
| `POST` | `/tickets/{ticket_id}/resolve` |
| `POST` | `/tickets/{ticket_id}/close` |
| … | (+32 more — see `router.py`) |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/service/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `service-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `service-T002` | Open `service` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `service-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `service-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `service-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `service-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `service-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `service-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `service-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `service-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `equipment`

- Backend: `backend/app/modules/equipment/`
- Frontend: `frontend/src/features/equipment/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 44

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/types/` |
| `POST` | `/types/` |
| `PATCH` | `/types/{type_id}` |
| `DELETE` | `/types/{type_id}` |
| `GET` | `/equipment/` |
| `POST` | `/equipment/` |
| `GET` | `/equipment/{equipment_id}` |
| `PATCH` | `/equipment/{equipment_id}` |
| `DELETE` | `/equipment/{equipment_id}` |
| `GET` | `/equipment/{equipment_id}/dashboard` |
| `POST` | `/equipment/{equipment_id}/telemetry` |
| `GET` | `/equipment/{equipment_id}/telemetry` |
| `GET` | `/maintenance-schedules/` |
| `POST` | `/maintenance-schedules/` |
| `PATCH` | `/maintenance-schedules/{schedule_id}` |
| `DELETE` | `/maintenance-schedules/{schedule_id}` |
| `GET` | `/maintenance-schedules/due-within` |
| `GET` | `/maintenance-work-orders/` |
| `POST` | `/maintenance-work-orders/` |
| `POST` | `/maintenance-work-orders/{work_order_id}/complete` |
| … | (+24 more — see `router.py`) |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/equipment/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `equipment-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `equipment-T002` | Open `equipment` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `equipment-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `equipment-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `equipment-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `equipment-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `equipment-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `equipment-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `equipment-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `equipment-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Batch `batch-12-finance-eac-contracts-changeorders-variations` — Finance, Cost Model, EAC, Contracts, Variations, Change Orders

**Summary**: Finance ledgers, 5D cost model, EAC v2 engine, contract types, variations + change orders atomicity (variations.convert_vr_to_vo), full EVM.

**Modules in this batch**: finance, costmodel, eac, contracts, variations, changeorders, full_evm

**Estimated runner-minutes**: 280  
**Depends on**: batch-03-boq-suite, batch-09-procurement-subs-bids

### Module: `finance`

- Backend: `backend/app/modules/finance/`
- Frontend: `frontend/src/features/finance/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 18

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/` |
| `POST` | `/` |
| `GET` | `/invoices/` |
| `GET` | `/invoices/export/` |
| `GET` | `/payments/` |
| `POST` | `/payments/` |
| `GET` | `/budgets/` |
| `POST` | `/budgets/` |
| `POST` | `/budgets/import/file/` |
| `GET` | `/budgets/export/` |
| `PATCH` | `/budgets/{budget_id}` |
| `GET` | `/evm/` |
| `POST` | `/evm/snapshot/` |
| `GET` | `/dashboard/` |
| `GET` | `/{invoice_id}` |
| `PATCH` | `/{invoice_id}` |
| `POST` | `/{invoice_id}/approve/` |
| `POST` | `/{invoice_id}/pay/` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/finance/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `finance-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `finance-T002` | Open `finance` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `finance-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `finance-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `finance-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `finance-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `finance-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `finance-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `finance-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `finance-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `costmodel`

- Backend: `backend/app/modules/costmodel/`
- Frontend: `frontend/src/features/costmodel/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 18

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/projects/{project_id}/5d/dashboard/` |
| `GET` | `/projects/{project_id}/5d/s-curve/` |
| `GET` | `/projects/{project_id}/5d/cash-flow/` |
| `GET` | `/projects/{project_id}/5d/budget/` |
| `GET` | `/projects/{project_id}/5d/budget-lines/` |
| `POST` | `/projects/{project_id}/5d/budget-lines/` |
| `PATCH` | `/5d/budget-lines/{line_id}` |
| `DELETE` | `/5d/budget-lines/{line_id}` |
| `POST` | `/projects/{project_id}/5d/generate-budget/` |
| `POST` | `/projects/{project_id}/5d/snapshots/` |
| `GET` | `/projects/{project_id}/5d/snapshots/` |
| `PATCH` | `/5d/snapshots/{snapshot_id}` |
| `DELETE` | `/projects/{project_id}/5d/snapshots/{snapshot_id}` |
| `GET` | `/projects/{project_id}/5d/evm/` |
| `POST` | `/projects/{project_id}/5d/what-if/` |
| `POST` | `/projects/{project_id}/5d/generate-cash-flow/` |
| `POST` | `/projects/{project_id}/5d/monte-carlo/` |
| `GET` | `/variance/` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/costmodel/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `costmodel-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `costmodel-T002` | Open `costmodel` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `costmodel-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `costmodel-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `costmodel-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `costmodel-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `costmodel-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `costmodel-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `costmodel-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `costmodel-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `eac`

- Backend: `backend/app/modules/eac/`
- Frontend: `frontend/src/features/eac/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 21

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `POST` | `/rules` |
| `GET` | `/rules/{rule_id}` |
| `GET` | `/rules` |
| `PUT` | `/rules/{rule_id}` |
| `DELETE` | `/rules/{rule_id}` |
| `POST` | `/rules:validate` |
| `POST` | `/rulesets` |
| `GET` | `/rulesets/{ruleset_id}` |
| `GET` | `/rulesets` |
| `PUT` | `/rulesets/{ruleset_id}` |
| `DELETE` | `/rulesets/{ruleset_id}` |
| `POST` | `/rules:dry-run` |
| `POST` | `/rulesets/{ruleset_id}:run` |
| `GET` | `/runs/{run_id}` |
| `GET` | `/runs` |
| `GET` | `/runs/{run_id}/results` |
| `POST` | `/rules:compile` |
| `GET` | `/runs/{run_id}/status` |
| `POST` | `/runs/{run_id}:cancel` |
| `POST` | `/runs/{run_id}:rerun` |
| … | (+1 more — see `router.py`) |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/eac/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `eac-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `eac-T002` | Open `eac` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `eac-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `eac-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `eac-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `eac-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `eac-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `eac-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `eac-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `eac-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `contracts`

- Backend: `backend/app/modules/contracts/`
- Frontend: `frontend/src/features/contracts/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 60

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/contracts/` |
| `POST` | `/contracts/` |
| `GET` | `/contracts/{contract_id}` |
| `PATCH` | `/contracts/{contract_id}` |
| `DELETE` | `/contracts/{contract_id}` |
| `POST` | `/contracts/{contract_id}/sign` |
| `POST` | `/contracts/{contract_id}/suspend` |
| `POST` | `/contracts/{contract_id}/resume` |
| `POST` | `/contracts/{contract_id}/terminate` |
| `POST` | `/contracts/{contract_id}/clone` |
| `GET` | `/contracts/{contract_id}/lines` |
| `POST` | `/contracts/{contract_id}/lines` |
| `POST` | `/contracts/{contract_id}/lines/bulk` |
| `PATCH` | `/contracts/lines/{line_id}` |
| `DELETE` | `/contracts/lines/{line_id}` |
| `GET` | `/type-configurations/` |
| `POST` | `/retention-schedules/` |
| `GET` | `/retention-schedules/{schedule_id}` |
| `PATCH` | `/retention-schedules/{schedule_id}` |
| `DELETE` | `/retention-schedules/{schedule_id}` |
| … | (+40 more — see `router.py`) |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/contracts/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `contracts-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `contracts-T002` | Open `contracts` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `contracts-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `contracts-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `contracts-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `contracts-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `contracts-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `contracts-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `contracts-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `contracts-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- Clone endpoint (R7) returns 201 + new id; original untouched.
- Sign action is MANAGER-only.

### Module: `variations`

- Backend: `backend/app/modules/variations/`
- Frontend: `frontend/src/features/variations/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 73

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/notices/` |
| `POST` | `/notices/` |
| `GET` | `/notices/{notice_id}` |
| `PATCH` | `/notices/{notice_id}` |
| `DELETE` | `/notices/{notice_id}` |
| `POST` | `/notices/{notice_id}/acknowledge` |
| `POST` | `/notices/{notice_id}/respond` |
| `POST` | `/notices/{notice_id}/close` |
| `GET` | `/variation-requests/` |
| `POST` | `/variation-requests/` |
| `GET` | `/variation-requests/{vr_id}` |
| `PATCH` | `/variation-requests/{vr_id}` |
| `DELETE` | `/variation-requests/{vr_id}` |
| `POST` | `/variation-requests/{vr_id}/submit` |
| `POST` | `/variation-requests/{vr_id}/approve` |
| `POST` | `/variation-requests/{vr_id}/reject` |
| `POST` | `/variation-requests/{vr_id}/convert-to-vo` |
| `GET` | `/variation-orders/` |
| `POST` | `/variation-orders/` |
| `GET` | `/variation-orders/{vo_id}` |
| … | (+53 more — see `router.py`) |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/variations/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `variations-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `variations-T002` | Open `variations` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `variations-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `variations-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `variations-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `variations-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `variations-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `variations-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `variations-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `variations-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- convert_vr_to_vo cross-module atomicity (R7 pattern).
- Approve is MANAGER-only.

### Module: `changeorders`

- Backend: `backend/app/modules/changeorders/`
- Frontend: `frontend/src/features/changeorders/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 15

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/summary/` |
| `POST` | `/` |
| `GET` | `/` |
| `GET` | `/{order_id}` |
| `PATCH` | `/{order_id}` |
| `DELETE` | `/{order_id}` |
| `POST` | `/{order_id}/items/` |
| `PATCH` | `/{order_id}/items/{item_id}` |
| `DELETE` | `/{order_id}/items/{item_id}` |
| `POST` | `/{order_id}/submit/` |
| `POST` | `/{order_id}/approve/` |
| `POST` | `/{order_id}/reject/` |
| `POST` | `/{order_id}/approval-chain` |
| `POST` | `/{order_id}/advance-approval` |
| `GET` | `/{order_id}/approvals` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/changeorders/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `changeorders-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `changeorders-T002` | Open `changeorders` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `changeorders-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `changeorders-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `changeorders-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `changeorders-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `changeorders-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `changeorders-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `changeorders-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `changeorders-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `full_evm`

- Backend: `backend/app/modules/full_evm/`
- Frontend: `(API-only — no UI)`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 3

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/forecasts/` |
| `POST` | `/forecasts/calculate/` |
| `GET` | `/s-curve-data/` |

**UI surface area**

- API-only module — no UI surface to test. Run API-only test path:
  - exercise every endpoint from above via `httpx` directly;
  - validate JSON schemas against `openapi.json`;
  - run regression matrix items reg-01, reg-02, reg-04, reg-05.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `full-evm-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `full-evm-T002` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Batch `batch-13-carbon-submittals-rfi-meetings-reports` — Carbon, Submittals, RFI, Meetings, Reports, Reporting, BI

**Summary**: Sustainability/embodied carbon, submittals attachments (R7 magic-byte), RFI threads, meetings agenda+minutes, reports library, BI dashboards crossfilter.

**Modules in this batch**: carbon, submittals, rfi, meetings, reporting, bi_dashboards, transmittals, requirements, compliance, compliance_ai, compliance_docs

**Estimated runner-minutes**: 280  
**Depends on**: batch-03-boq-suite

### Module: `carbon`

- Backend: `backend/app/modules/carbon/`
- Frontend: `frontend/src/features/carbon/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 51

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/epd` |
| `POST` | `/epd` |
| `POST` | `/epd/sync` |
| `GET` | `/epd/{epd_id}` |
| `PATCH` | `/epd/{epd_id}` |
| `DELETE` | `/epd/{epd_id}` |
| `GET` | `/material-factors` |
| `POST` | `/material-factors` |
| `GET` | `/material-factors/{factor_id}` |
| `PATCH` | `/material-factors/{factor_id}` |
| `DELETE` | `/material-factors/{factor_id}` |
| `GET` | `/inventories` |
| `POST` | `/inventories` |
| `GET` | `/inventories/{inventory_id}` |
| `PATCH` | `/inventories/{inventory_id}` |
| `DELETE` | `/inventories/{inventory_id}` |
| `POST` | `/inventories/{inventory_id}/finalize` |
| `GET` | `/inventories/{inventory_id}/totals` |
| `GET` | `/inventories/{inventory_id}/alternatives` |
| `GET` | `/inventories/{inventory_id}/embodied` |
| … | (+31 more — see `router.py`) |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/carbon/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `carbon-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `carbon-T002` | Open `carbon` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `carbon-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `carbon-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `carbon-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `carbon-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `carbon-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `carbon-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `carbon-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `carbon-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `submittals`

- Backend: `backend/app/modules/submittals/`
- Frontend: `frontend/src/features/submittals/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 12

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/` |
| `POST` | `/` |
| `GET` | `/{submittal_id}` |
| `PATCH` | `/{submittal_id}` |
| `DELETE` | `/{submittal_id}` |
| `POST` | `/{submittal_id}/submit/` |
| `POST` | `/{submittal_id}/review/` |
| `POST` | `/{submittal_id}/approve/` |
| `GET` | `/{submittal_id}/attachments/` |
| `POST` | `/{submittal_id}/attachments/upload/` |
| `POST` | `/{submittal_id}/attachments/` |
| `DELETE` | `/{submittal_id}/attachments/{document_id}` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/submittals/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `submittals-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `submittals-T002` | Open `submittals` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `submittals-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `submittals-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `submittals-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `submittals-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `submittals-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `submittals-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `submittals-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `submittals-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `rfi`

- Backend: `backend/app/modules/rfi/`
- Frontend: `frontend/src/features/rfi/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 13

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/` |
| `POST` | `/` |
| `GET` | `/stats/` |
| `GET` | `/export/` |
| `POST` | `/batch/delete/` |
| `PATCH` | `/batch/status/` |
| `GET` | `/{rfi_id}` |
| `PATCH` | `/{rfi_id}` |
| `DELETE` | `/{rfi_id}` |
| `POST` | `/{rfi_id}/respond/` |
| `POST` | `/{rfi_id}/create-variation/` |
| `POST` | `/{rfi_id}/close/` |
| `POST` | `/{rfi_id}/attachments/` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/rfi/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `rfi-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `rfi-T002` | Open `rfi` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `rfi-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `rfi-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `rfi-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `rfi-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `rfi-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `rfi-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `rfi-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `rfi-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `meetings`

- Backend: `backend/app/modules/meetings/`
- Frontend: `frontend/src/features/meetings/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 16

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/` |
| `GET` | `/stats/` |
| `GET` | `/open-actions/` |
| `POST` | `/` |
| `POST` | `/import-summary/` |
| `GET` | `/{meeting_id}` |
| `PATCH` | `/{meeting_id}` |
| `DELETE` | `/{meeting_id}` |
| `POST` | `/{meeting_id}/complete/` |
| `POST` | `/series/` |
| `POST` | `/series/{master_id}/materialize/` |
| `POST` | `/series/{master_id}/materialize` |
| `POST` | `/{meeting_id}/check-in/` |
| `POST` | `/{meeting_id}/external-attendee/` |
| `GET` | `/{meeting_id}/attendance/` |
| `GET` | `/{meeting_id}/export/pdf/` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/meetings/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `meetings-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `meetings-T002` | Open `meetings` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `meetings-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `meetings-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `meetings-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `meetings-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `meetings-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `meetings-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `meetings-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `meetings-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `reporting`

- Backend: `backend/app/modules/reporting/`
- Frontend: `frontend/src/features/reporting/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 13

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/kpi/` |
| `GET` | `/kpi/history/` |
| `POST` | `/kpi/snapshot/` |
| `POST` | `/kpi/recalculate-all/` |
| `GET` | `/templates/` |
| `POST` | `/templates/` |
| `GET` | `/templates/scheduled/` |
| `POST` | `/templates/{template_id}/schedule/` |
| `POST` | `/templates/{template_id}/run-now/` |
| `POST` | `/generate/` |
| `GET` | `/reports/` |
| `GET` | `/reports/{report_id}` |
| `DELETE` | `/reports/{report_id}` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/reporting/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `reporting-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `reporting-T002` | Open `reporting` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `reporting-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `reporting-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `reporting-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `reporting-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `reporting-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `reporting-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `reporting-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `reporting-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `bi_dashboards`

- Backend: `backend/app/modules/bi_dashboards/`
- Frontend: `frontend/src/features/bi-dashboards/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 29

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/kpis` |
| `POST` | `/kpis/{code}/compute` |
| `GET` | `/kpis/{code}/history` |
| `POST` | `/kpis/{code}/drill-down` |
| `POST` | `/install-starter-pack` |
| `GET` | `/dashboards` |
| `POST` | `/dashboards` |
| `PATCH` | `/dashboards/{dashboard_id}` |
| `DELETE` | `/dashboards/{dashboard_id}` |
| `GET` | `/dashboards/{dashboard_id}/render` |
| `POST` | `/dashboards/{dashboard_id}/evaluate` |
| `POST` | `/widgets` |
| `PATCH` | `/widgets/{widget_id}` |
| `DELETE` | `/widgets/{widget_id}` |
| `GET` | `/reports` |
| `POST` | `/reports` |
| `POST` | `/reports/{report_id}/run` |
| `POST` | `/report-schedules` |
| `PATCH` | `/report-schedules/{schedule_id}` |
| `POST` | `/report-schedules/{schedule_id}/run-now` |
| … | (+9 more — see `router.py`) |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/bi-dashboards/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `bi-dashboards-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `bi-dashboards-T002` | Open `bi_dashboards` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `bi-dashboards-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `bi-dashboards-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `bi-dashboards-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `bi-dashboards-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `bi-dashboards-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `bi-dashboards-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `bi-dashboards-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `bi-dashboards-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `transmittals`

- Backend: `backend/app/modules/transmittals/`
- Frontend: `frontend/src/features/transmittals/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 8

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/` |
| `POST` | `/` |
| `GET` | `/{transmittal_id}` |
| `PATCH` | `/{transmittal_id}` |
| `DELETE` | `/{transmittal_id}` |
| `POST` | `/{transmittal_id}/issue/` |
| `POST` | `/{transmittal_id}/recipients/{recipient_id}/acknowledge/` |
| `POST` | `/{transmittal_id}/recipients/{recipient_id}/respond/` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/transmittals/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `transmittals-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `transmittals-T002` | Open `transmittals` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `transmittals-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `transmittals-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `transmittals-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `transmittals-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `transmittals-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `transmittals-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `transmittals-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `transmittals-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `requirements`

- Backend: `backend/app/modules/requirements/`
- Frontend: `frontend/src/features/requirements/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 29

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/stats/` |
| `POST` | `/` |
| `GET` | `/` |
| `GET` | `/template.xlsx` |
| `GET` | `/{set_id}` |
| `GET` | `/{set_id}/export/` |
| `GET` | `/{set_id}/export.{ext}` |
| `POST` | `/{set_id}/import/file/` |
| `PATCH` | `/{set_id}` |
| `DELETE` | `/{set_id}` |
| `POST` | `/{set_id}/requirements/bulk-delete/` |
| `POST` | `/{set_id}/requirements/` |
| `POST` | `/{set_id}/requirements/bulk/` |
| `PATCH` | `/{set_id}/requirements/{req_id}` |
| `DELETE` | `/{set_id}/requirements/{req_id}` |
| `POST` | `/{set_id}/gates/{gate_number}/run/` |
| `GET` | `/{set_id}/gates/` |
| `POST` | `/{set_id}/requirements/{req_id}/link/{position_id}` |
| `POST` | `/{set_id}/import/text/` |
| `PATCH` | `/{set_id}/requirements/{req_id}/bim-links/` |
| … | (+9 more — see `router.py`) |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/requirements/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `requirements-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `requirements-T002` | Open `requirements` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `requirements-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `requirements-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `requirements-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `requirements-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `requirements-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `requirements-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `requirements-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `requirements-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `compliance`

- Backend: `backend/app/modules/compliance/`
- Frontend: `frontend/src/features/compliance/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 7

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `POST` | `/dsl/validate-syntax` |
| `POST` | `/dsl/compile` |
| `GET` | `/dsl/rules` |
| `GET` | `/dsl/rules/{rule_pk}` |
| `DELETE` | `/dsl/rules/{rule_pk}` |
| `GET` | `/dsl/nl-patterns` |
| `POST` | `/dsl/from-nl` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/compliance/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `compliance-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `compliance-T002` | Open `compliance` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `compliance-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `compliance-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `compliance-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `compliance-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `compliance-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `compliance-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `compliance-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `compliance-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `compliance_ai`

- Backend: `backend/app/modules/compliance_ai/`
- Frontend: `(API-only — no UI)`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 2

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/_health` |
| `POST` | `/from-nl` |

**UI surface area**

- API-only module — no UI surface to test. Run API-only test path:
  - exercise every endpoint from above via `httpx` directly;
  - validate JSON schemas against `openapi.json`;
  - run regression matrix items reg-01, reg-02, reg-04, reg-05.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `compliance-ai-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `compliance-ai-T002` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `compliance_docs`

- Backend: `backend/app/modules/compliance_docs/`
- Frontend: `frontend/src/features/compliance-docs/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 7

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/` |
| `GET` | `/expiring-soon/` |
| `POST` | `/` |
| `GET` | `/{doc_id}/` |
| `PATCH` | `/{doc_id}/` |
| `DELETE` | `/{doc_id}/` |
| `POST` | `/{doc_id}/attachment/` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/compliance-docs/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `compliance-docs-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `compliance-docs-T002` | Open `compliance_docs` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `compliance-docs-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `compliance-docs-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `compliance-docs-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `compliance-docs-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `compliance-docs-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `compliance-docs-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `compliance-docs-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `compliance-docs-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Batch `batch-14-geo-hub` — Geo Hub (Cesium 3D Tiles, raster overlay, auto-anchor)

**Summary**: Global + project + development globe views, DWG/PDF raster overlay (v3121), polygon crop, degenerate-bbox guard, /geo-hub Navigate alias.

**Modules in this batch**: geo_hub

**Estimated runner-minutes**: 140  
**Depends on**: batch-02-projects-companies-contacts

### Module: `geo_hub`

- Backend: `backend/app/modules/geo_hub/`
- Frontend: `frontend/src/features/geo-hub/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 47

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/anchors/` |
| `POST` | `/anchors/` |
| `GET` | `/anchors/{anchor_id}` |
| `PATCH` | `/anchors/{anchor_id}` |
| `DELETE` | `/anchors/{anchor_id}` |
| `GET` | `/tilesets/` |
| `POST` | `/tilesets/` |
| `GET` | `/tilesets/{tileset_id}` |
| `PATCH` | `/tilesets/{tileset_id}` |
| `DELETE` | `/tilesets/{tileset_id}` |
| `POST` | `/tilesets/generate/` |
| `POST` | `/jobs/{job_id}/cancel` |
| `GET` | `/jobs/{job_id}` |
| `GET` | `/jobs/` |
| `POST` | `/from-canonical/{cad_import_id}` |
| `GET` | `/imagery-layers/` |
| `POST` | `/imagery-layers/` |
| `PATCH` | `/imagery-layers/{layer_id}` |
| `DELETE` | `/imagery-layers/{layer_id}` |
| `GET` | `/terrain-sources/` |
| … | (+27 more — see `router.py`) |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/geo-hub/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `geo-hub-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `geo-hub-T002` | Open `geo_hub` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `geo-hub-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `geo-hub-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `geo-hub-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `geo-hub-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `geo-hub-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `geo-hub-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `geo-hub-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `geo-hub-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- Cesium 3D Tiles 1.1 viewer mounts; z-ordering against project pins correct.
- DWG/PDF raster overlay — drag corners + polygon crop with vertex drag.
- Degenerate-bbox guard — shows 'Needs corners' CTA, not blank globe.
- /geo-hub Navigate alias route exists.

### Batch `batch-15-ai-chat-vector-marketplace-integrations` — AI, AI Agents, ERP Chat, Search, Integrations, Webhooks, Marketplace

**Summary**: Floating chat (17 tools, SSE stream), AI prompt fencing, semantic search, integrations + webhooks, regional packs (8), file lifecycle modules, OpenCDE API, marketplace.

**Modules in this batch**: ai, ai_agents, erp_chat, search, project_intelligence, integrations, client_errors, smart_views, documents, uploads, backup, i18n_foundation, architecture_map, opencde_api, cde, collaboration, collaboration_locks, file_approvals, file_comments, file_distribution, file_favorites, file_references, file_saved_views, file_search, file_tags, file_transmittals, file_trash, file_versions, enterprise_workflows, dashboard, dashboards, asia_pac_pack, dach_pack, india_pack, latam_pack, middle_east_pack, russia_pack, uk_pack, us_pack

**Estimated runner-minutes**: 420  
**Depends on**: batch-03-boq-suite

### Module: `ai`

- Backend: `backend/app/modules/ai/`
- Frontend: `frontend/src/features/ai/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 12

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/providers` |
| `GET` | `/providers/` |
| `GET` | `/settings/` |
| `PATCH` | `/settings/` |
| `POST` | `/settings/test/` |
| `POST` | `/quick-estimate/` |
| `POST` | `/photo-estimate/` |
| `POST` | `/file-estimate/` |
| `POST` | `/estimate/{job_id}/create-boq/` |
| `POST` | `/estimate/{job_id}/enrich/` |
| `GET` | `/estimate/{job_id}` |
| `POST` | `/advisor/chat/` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/ai/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `ai-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `ai-T002` | Open `ai` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `ai-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `ai-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `ai-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `ai-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `ai-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `ai-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `ai-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `ai-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- AI prompt fencing — user input does not escape the system prompt.
- AI key never leaked to frontend (test_ai_key_no_leak).

### Module: `ai_agents`

- Backend: `backend/app/modules/ai_agents/`
- Frontend: `frontend/src/features/ai-agents/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 5

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/agents/` |
| `GET` | `/tools/` |
| `POST` | `/runs/` |
| `GET` | `/runs/` |
| `GET` | `/runs/{run_id}` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/ai-agents/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `ai-agents-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `ai-agents-T002` | Open `ai_agents` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `ai-agents-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `ai-agents-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `ai-agents-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `ai-agents-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `ai-agents-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `ai-agents-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `ai-agents-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `ai-agents-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `erp_chat`

- Backend: `backend/app/modules/erp_chat/`
- Frontend: `frontend/src/features/erp-chat/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 8

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `POST` | `/stream/` |
| `GET` | `/sessions/` |
| `POST` | `/sessions/` |
| `GET` | `/sessions/{session_id}/messages/` |
| `DELETE` | `/sessions/{session_id}/` |
| `GET` | `/messages/{message_id}/similar/` |
| `POST` | `/messages/{message_id}/feedback/` |
| `GET` | `/admin/stats/` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/erp-chat/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `erp-chat-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `erp-chat-T002` | Open `erp_chat` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `erp-chat-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `erp-chat-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `erp-chat-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `erp-chat-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `erp-chat-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `erp-chat-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `erp-chat-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `erp-chat-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- Floating FAB mounted on every route.
- 17 tools all invokable; SSE stream renders per-tool card.
- Rate limit returns 429 with Retry-After.

### Module: `search`

- Backend: `backend/app/modules/search/`
- Frontend: `frontend/src/features/search/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 3

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/` |
| `GET` | `/status/` |
| `GET` | `/types/` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/search/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `search-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `search-T002` | Open `search` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `search-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `search-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `search-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `search-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `search-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `search-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `search-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `search-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `project_intelligence`

- Backend: `backend/app/modules/project_intelligence/`
- Frontend: `frontend/src/features/project-intelligence/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 8

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/score/` |
| `GET` | `/state/` |
| `GET` | `/summary/` |
| `POST` | `/recommendations/` |
| `POST` | `/chat/` |
| `POST` | `/explain-gap/` |
| `POST` | `/actions/{action_id}/` |
| `GET` | `/actions/` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/project-intelligence/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `project-intelligence-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `project-intelligence-T002` | Open `project_intelligence` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `project-intelligence-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `project-intelligence-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `project-intelligence-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `project-intelligence-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `project-intelligence-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `project-intelligence-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `project-intelligence-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `project-intelligence-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `integrations`

- Backend: `backend/app/modules/integrations/`
- Frontend: `frontend/src/features/integrations/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 12

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/configs/` |
| `POST` | `/configs/` |
| `PATCH` | `/configs/{config_id}` |
| `DELETE` | `/configs/{config_id}` |
| `POST` | `/configs/{config_id}/test/` |
| `GET` | `/webhooks/` |
| `POST` | `/webhooks/` |
| `PATCH` | `/webhooks/{webhook_id}` |
| `DELETE` | `/webhooks/{webhook_id}` |
| `GET` | `/webhooks/{webhook_id}/deliveries/` |
| `POST` | `/webhooks/{webhook_id}/test/` |
| `GET` | `/calendar/{project_id}.ics/` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/integrations/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `integrations-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `integrations-T002` | Open `integrations` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `integrations-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `integrations-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `integrations-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `integrations-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `integrations-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `integrations-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `integrations-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `integrations-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `client_errors`

- Backend: `backend/app/modules/client_errors/`
- Frontend: `(API-only — no UI)`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 1

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `POST` | `/` |

**UI surface area**

- API-only module — no UI surface to test. Run API-only test path:
  - exercise every endpoint from above via `httpx` directly;
  - validate JSON schemas against `openapi.json`;
  - run regression matrix items reg-01, reg-02, reg-04, reg-05.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `client-errors-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `client-errors-T002` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `smart_views`

- Backend: `backend/app/modules/smart_views/`
- Frontend: `frontend/src/features/smart_views/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 11

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `POST` | `/` |
| `GET` | `/` |
| `GET` | `/{view_id}` |
| `PUT` | `/{view_id}` |
| `DELETE` | `/{view_id}` |
| `POST` | `/{view_id}/evaluate` |
| `GET` | `/presets` |
| `POST` | `/presets/{preset_id}/install` |
| `POST` | `/{view_id}/share` |
| `DELETE` | `/{view_id}/share` |
| `GET` | `/shared/{token}` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/smart_views/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `smart-views-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `smart-views-T002` | Open `smart_views` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `smart-views-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `smart-views-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `smart-views-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `smart-views-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `smart-views-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `smart-views-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `smart-views-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `smart-views-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `documents`

- Backend: `backend/app/modules/documents/`
- Frontend: `frontend/src/features/documents/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 36

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/summary/` |
| `POST` | `/upload/` |
| `GET` | `/` |
| `GET` | `/file-types-by-project/` |
| `POST` | `/photos/upload/` |
| `GET` | `/photos/` |
| `GET` | `/photos/gallery/` |
| `GET` | `/photos/timeline/` |
| `GET` | `/photos/{photo_id}` |
| `GET` | `/photos/{photo_id}/file/` |
| `GET` | `/photos/{photo_id}/thumb/` |
| `PATCH` | `/photos/{photo_id}` |
| `DELETE` | `/photos/{photo_id}` |
| `GET` | `/sheets/` |
| `GET` | `/sheets/disciplines/` |
| `POST` | `/sheets/split-pdf/` |
| `GET` | `/sheets/{sheet_id}` |
| `PATCH` | `/sheets/{sheet_id}` |
| `DELETE` | `/sheets/{sheet_id}` |
| `GET` | `/sheets/{sheet_id}/versions/` |
| … | (+16 more — see `router.py`) |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/documents/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `documents-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `documents-T002` | Open `documents` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `documents-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `documents-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `documents-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `documents-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `documents-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `documents-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `documents-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `documents-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- Magic-byte validation on every upload.
- Deep-link walkthrough (file-deeplink-walkthrough.spec).

### Module: `uploads`

- Backend: `backend/app/modules/uploads/`
- Frontend: `(API-only — no UI)`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 1

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `PUT` | `/local/{token}` |

**UI surface area**

- API-only module — no UI surface to test. Run API-only test path:
  - exercise every endpoint from above via `httpx` directly;
  - validate JSON schemas against `openapi.json`;
  - run regression matrix items reg-01, reg-02, reg-04, reg-05.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `uploads-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `uploads-T002` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- Magic-byte validation everywhere (R7 baseline).
- Direct upload to S3/MinIO works.

### Module: `backup`

- Backend: `backend/app/modules/backup/`
- Frontend: `(API-only — no UI)`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 3

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `POST` | `/export/` |
| `POST` | `/restore/` |
| `POST` | `/validate/` |

**UI surface area**

- API-only module — no UI surface to test. Run API-only test path:
  - exercise every endpoint from above via `httpx` directly;
  - validate JSON schemas against `openapi.json`;
  - run regression matrix items reg-01, reg-02, reg-04, reg-05.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `backup-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `backup-T002` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `i18n_foundation`

- Backend: `backend/app/modules/i18n_foundation/`
- Frontend: `(API-only — no UI)`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 19

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/exchange-rates/` |
| `POST` | `/exchange-rates/` |
| `GET` | `/exchange-rates/convert/` |
| `POST` | `/exchange-rates/fetch-ecb/` |
| `GET` | `/exchange-rates/{rate_id}` |
| `PATCH` | `/exchange-rates/{rate_id}` |
| `DELETE` | `/exchange-rates/{rate_id}` |
| `GET` | `/countries/` |
| `GET` | `/countries/{iso_code}` |
| `GET` | `/work-calendars/` |
| `GET` | `/work-calendars/working-days/` |
| `POST` | `/work-calendars/` |
| `GET` | `/work-calendars/{calendar_id}` |
| `PATCH` | `/work-calendars/{calendar_id}` |
| `GET` | `/tax-configs/` |
| `GET` | `/tax-configs/by-country/{country_code}` |
| `POST` | `/tax-configs/` |
| `GET` | `/tax-configs/{config_id}` |
| `PATCH` | `/tax-configs/{config_id}` |

**UI surface area**

- API-only module — no UI surface to test. Run API-only test path:
  - exercise every endpoint from above via `httpx` directly;
  - validate JSON schemas against `openapi.json`;
  - run regression matrix items reg-01, reg-02, reg-04, reg-05.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `i18n-foundation-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `i18n-foundation-T002` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `architecture_map`

- Backend: `backend/app/modules/architecture_map/`
- Frontend: `(API-only — no UI)`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 6

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/` |
| `GET` | `/modules/` |
| `GET` | `/modules/{module_id}` |
| `GET` | `/connections/` |
| `GET` | `/search/` |
| `GET` | `/stats/` |

**UI surface area**

- API-only module — no UI surface to test. Run API-only test path:
  - exercise every endpoint from above via `httpx` directly;
  - validate JSON schemas against `openapi.json`;
  - run regression matrix items reg-01, reg-02, reg-04, reg-05.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `architecture-map-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `architecture-map-T002` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `opencde_api`

- Backend: `backend/app/modules/opencde_api/`
- Frontend: `(API-only — no UI)`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 13

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/foundation/versions/` |
| `GET` | `/foundation/1.1/auth/` |
| `GET` | `/foundation/1.1/current-user/` |
| `GET` | `/bcf/3.0/projects/` |
| `GET` | `/bcf/3.0/projects/{project_id}` |
| `GET` | `/bcf/3.0/projects/{project_id}/topics/` |
| `POST` | `/bcf/3.0/projects/{project_id}/topics/` |
| `GET` | `/bcf/3.0/projects/{project_id}/topics/{topic_guid}` |
| `PUT` | `/bcf/3.0/projects/{project_id}/topics/{topic_guid}` |
| `GET` | `/bcf/3.0/projects/{project_id}/topics/{topic_guid}/comments/` |
| `POST` | `/bcf/3.0/projects/{project_id}/topics/{topic_guid}/comments/` |
| `GET` | `/bcf/3.0/projects/{project_id}/topics/{topic_guid}/viewpoints/` |
| `POST` | `/bcf/3.0/projects/{project_id}/topics/{topic_guid}/viewpoints/` |

**UI surface area**

- API-only module — no UI surface to test. Run API-only test path:
  - exercise every endpoint from above via `httpx` directly;
  - validate JSON schemas against `openapi.json`;
  - run regression matrix items reg-01, reg-02, reg-04, reg-05.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `opencde-api-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `opencde-api-T002` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `cde`

- Backend: `backend/app/modules/cde/`
- Frontend: `frontend/src/features/cde/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 15

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/suitability-codes` |
| `GET` | `/suitability-codes/` |
| `GET` | `/stats` |
| `GET` | `/stats/` |
| `GET` | `/containers` |
| `GET` | `/containers/` |
| `POST` | `/containers/` |
| `GET` | `/containers/{container_id}` |
| `PATCH` | `/containers/{container_id}` |
| `POST` | `/containers/{container_id}/transition/` |
| `GET` | `/containers/{container_id}/history/` |
| `GET` | `/containers/{container_id}/transmittals/` |
| `GET` | `/containers/{container_id}/revisions/` |
| `POST` | `/containers/{container_id}/revisions/` |
| `GET` | `/revisions/{revision_id}` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/cde/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `cde-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `cde-T002` | Open `cde` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `cde-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `cde-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `cde-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `cde-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `cde-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `cde-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `cde-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `cde-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `collaboration`

- Backend: `backend/app/modules/collaboration/`
- Frontend: `(API-only — no UI)`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 7

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/comments/` |
| `POST` | `/comments/` |
| `PATCH` | `/comments/{comment_id}` |
| `DELETE` | `/comments/{comment_id}` |
| `GET` | `/comments/{comment_id}/thread/` |
| `POST` | `/viewpoints/` |
| `GET` | `/viewpoints/` |

**UI surface area**

- API-only module — no UI surface to test. Run API-only test path:
  - exercise every endpoint from above via `httpx` directly;
  - validate JSON schemas against `openapi.json`;
  - run regression matrix items reg-01, reg-02, reg-04, reg-05.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `collaboration-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `collaboration-T002` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `collaboration_locks`

- Backend: `backend/app/modules/collaboration_locks/`
- Frontend: `(API-only — no UI)`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 5

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `POST` | `/` |
| `POST` | `/{lock_id}/heartbeat/` |
| `DELETE` | `/{lock_id}/` |
| `GET` | `/entity/` |
| `GET` | `/my/` |

**UI surface area**

- API-only module — no UI surface to test. Run API-only test path:
  - exercise every endpoint from above via `httpx` directly;
  - validate JSON schemas against `openapi.json`;
  - run regression matrix items reg-01, reg-02, reg-04, reg-05.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `collaboration-locks-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `collaboration-locks-T002` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `file_approvals`

- Backend: `backend/app/modules/file_approvals/`
- Frontend: `frontend/src/features/file-approvals/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 8

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/stamp-templates/` |
| `POST` | `/stamp-templates/` |
| `GET` | `/` |
| `POST` | `/` |
| `GET` | `/{workflow_id}/` |
| `POST` | `/{workflow_id}/steps/{step_id}/decide/` |
| `POST` | `/{workflow_id}/withdraw/` |
| `GET` | `/{workflow_id}/stamped/` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/file-approvals/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `file-approvals-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `file-approvals-T002` | Open `file_approvals` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `file-approvals-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `file-approvals-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `file-approvals-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `file-approvals-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `file-approvals-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `file-approvals-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `file-approvals-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `file-approvals-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `file_comments`

- Backend: `backend/app/modules/file_comments/`
- Frontend: `frontend/src/features/file-comments/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 6

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/` |
| `POST` | `/` |
| `PATCH` | `/{comment_id}/` |
| `DELETE` | `/{comment_id}/` |
| `GET` | `/mentions/me/` |
| `POST` | `/mentions/{mention_id}/acknowledge/` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/file-comments/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `file-comments-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `file-comments-T002` | Open `file_comments` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `file-comments-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `file-comments-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `file-comments-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `file-comments-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `file-comments-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `file-comments-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `file-comments-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `file-comments-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `file_distribution`

- Backend: `backend/app/modules/file_distribution/`
- Frontend: `frontend/src/features/file-distribution/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 10

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/search/` |
| `GET` | `/lists/` |
| `POST` | `/lists/` |
| `PATCH` | `/lists/{list_id}/` |
| `DELETE` | `/lists/{list_id}/` |
| `POST` | `/lists/{list_id}/members/` |
| `DELETE` | `/lists/{list_id}/members/{member_id}/` |
| `GET` | `/subscriptions/` |
| `POST` | `/subscriptions/` |
| `DELETE` | `/subscriptions/{subscription_id}/` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/file-distribution/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `file-distribution-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `file-distribution-T002` | Open `file_distribution` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `file-distribution-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `file-distribution-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `file-distribution-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `file-distribution-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `file-distribution-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `file-distribution-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `file-distribution-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `file-distribution-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `file_favorites`

- Backend: `backend/app/modules/file_favorites/`
- Frontend: `(API-only — no UI)`
- Has router: NO
- Has manifest: YES
- Discovered endpoints: 0

**Public surface area (API endpoints discovered in `router.py`)**

_No `@router.<method>` decorators detected — module may use a different
registration style (sub-router include) or be API-only via service layer._

**UI surface area**

- API-only module — no UI surface to test. Run API-only test path:
  - exercise every endpoint from above via `httpx` directly;
  - validate JSON schemas against `openapi.json`;
  - run regression matrix items reg-01, reg-02, reg-04, reg-05.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `file-favorites-T001` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `file_references`

- Backend: `backend/app/modules/file_references/`
- Frontend: `frontend/src/features/file-references/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 8

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `POST` | `/validate-name/` |
| `POST` | `/scan-project/` |
| `GET` | `/violations/` |
| `POST` | `/violations/{violation_id}/acknowledge/` |
| `GET` | `/` |
| `GET` | `/by-target/` |
| `POST` | `/` |
| `DELETE` | `/{reference_id}/` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/file-references/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `file-references-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `file-references-T002` | Open `file_references` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `file-references-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `file-references-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `file-references-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `file-references-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `file-references-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `file-references-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `file-references-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `file-references-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `file_saved_views`

- Backend: `backend/app/modules/file_saved_views/`
- Frontend: `frontend/src/features/file-saved-views/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 6

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/` |
| `POST` | `/` |
| `PATCH` | `/{view_id}/` |
| `DELETE` | `/{view_id}/` |
| `POST` | `/{view_id}/use/` |
| `POST` | `/{view_id}/duplicate/` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/file-saved-views/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `file-saved-views-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `file-saved-views-T002` | Open `file_saved_views` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `file-saved-views-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `file-saved-views-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `file-saved-views-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `file-saved-views-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `file-saved-views-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `file-saved-views-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `file-saved-views-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `file-saved-views-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `file_search`

- Backend: `backend/app/modules/file_search/`
- Frontend: `frontend/src/features/file-search/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 4

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `POST` | `/index/` |
| `GET` | `/` |
| `POST` | `/reindex/` |
| `DELETE` | `/{file_id}/` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/file-search/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `file-search-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `file-search-T002` | Open `file_search` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `file-search-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `file-search-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `file-search-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `file-search-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `file-search-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `file-search-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `file-search-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `file-search-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `file_tags`

- Backend: `backend/app/modules/file_tags/`
- Frontend: `frontend/src/features/file-tags/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 8

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/` |
| `POST` | `/` |
| `PATCH` | `/{tag_id}/` |
| `DELETE` | `/{tag_id}/` |
| `POST` | `/{tag_id}/assign/` |
| `POST` | `/{tag_id}/unassign/` |
| `GET` | `/by-file/` |
| `POST` | `/seed-defaults/` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/file-tags/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `file-tags-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `file-tags-T002` | Open `file_tags` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `file-tags-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `file-tags-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `file-tags-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `file-tags-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `file-tags-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `file-tags-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `file-tags-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `file-tags-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `file_transmittals`

- Backend: `backend/app/modules/file_transmittals/`
- Frontend: `frontend/src/features/file-transmittals/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 9

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/` |
| `POST` | `/` |
| `GET` | `/{transmittal_id}` |
| `POST` | `/{transmittal_id}/send/` |
| `POST` | `/{transmittal_id}/items/` |
| `DELETE` | `/{transmittal_id}/items/{item_id}/` |
| `POST` | `/{transmittal_id}/recipients/` |
| `POST` | `/ack/{token}/` |
| `GET` | `/{transmittal_id}/cover/` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/file-transmittals/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `file-transmittals-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `file-transmittals-T002` | Open `file_transmittals` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `file-transmittals-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `file-transmittals-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `file-transmittals-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `file-transmittals-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `file-transmittals-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `file-transmittals-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `file-transmittals-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `file-transmittals-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `file_trash`

- Backend: `backend/app/modules/file_trash/`
- Frontend: `frontend/src/features/file-trash/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 6

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/` |
| `GET` | `/stats/` |
| `POST` | `/` |
| `POST` | `/{trash_id}/restore/` |
| `DELETE` | `/{trash_id}` |
| `POST` | `/purge-now` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/file-trash/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `file-trash-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `file-trash-T002` | Open `file_trash` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `file-trash-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `file-trash-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `file-trash-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `file-trash-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `file-trash-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `file-trash-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `file-trash-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `file-trash-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `file_versions`

- Backend: `backend/app/modules/file_versions/`
- Frontend: `frontend/src/features/file-versions/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 4

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/` |
| `GET` | `/{version_id}/` |
| `POST` | `/` |
| `POST` | `/{version_id}/restore/` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/file-versions/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `file-versions-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `file-versions-T002` | Open `file_versions` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `file-versions-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `file-versions-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `file-versions-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `file-versions-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `file-versions-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `file-versions-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `file-versions-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `file-versions-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `enterprise_workflows`

- Backend: `backend/app/modules/enterprise_workflows/`
- Frontend: `(API-only — no UI)`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 11

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/` |
| `POST` | `/` |
| `GET` | `/{workflow_id}` |
| `PATCH` | `/{workflow_id}` |
| `DELETE` | `/{workflow_id}` |
| `GET` | `/requests/` |
| `POST` | `/requests/` |
| `GET` | `/requests/{request_id}` |
| `POST` | `/requests/{request_id}/approve/` |
| `POST` | `/requests/{request_id}/reject/` |
| `POST` | `/requests/{request_id}/cancel/` |

**UI surface area**

- API-only module — no UI surface to test. Run API-only test path:
  - exercise every endpoint from above via `httpx` directly;
  - validate JSON schemas against `openapi.json`;
  - run regression matrix items reg-01, reg-02, reg-04, reg-05.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `enterprise-workflows-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `enterprise-workflows-T002` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `dashboard`

- Backend: `backend/app/modules/dashboard/`
- Frontend: `frontend/src/features/dashboard/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 1

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/rollup/` |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/dashboard/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `dashboard-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `dashboard-T002` | Open `dashboard` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `dashboard-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `dashboard-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `dashboard-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `dashboard-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `dashboard-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `dashboard-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `dashboard-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `dashboard-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- ETag + 304 short-circuit on rollup endpoint.
- Server-side layout persistence via UserPreference.
- Per-widget 4xx count must be 0 (regression v4.6.0 c3bf7831).

### Module: `dashboards`

- Backend: `backend/app/modules/dashboards/`
- Frontend: `frontend/src/features/dashboards/`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 27

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/_health` |
| `POST` | `/projects/{project_id}/snapshots` |
| `GET` | `/projects/{project_id}/snapshots` |
| `GET` | `/snapshots/{snapshot_id}` |
| `DELETE` | `/snapshots/{snapshot_id}` |
| `GET` | `/snapshots/{snapshot_id}/manifest` |
| `GET` | `/snapshots/{snapshot_id}/quick-insights` |
| `GET` | `/snapshots/{snapshot_id}/values` |
| `POST` | `/snapshots/{snapshot_id}/cascade-values` |
| `GET` | `/snapshots/{snapshot_id}/row-count` |
| `POST` | `/presets` |
| `GET` | `/presets` |
| `GET` | `/presets/{preset_id}` |
| `PATCH` | `/presets/{preset_id}` |
| `DELETE` | `/presets/{preset_id}` |
| `POST` | `/presets/{preset_id}/share` |
| `POST` | `/presets/{preset_id}/sync-check` |
| `POST` | `/presets/{preset_id}/sync-heal` |
| `GET` | `/snapshots/{snapshot_id}/rows` |
| `GET` | `/snapshots/{snapshot_id}/export` |
| … | (+7 more — see `router.py`) |

**UI surface area**

- Pages: discover all `*.tsx` under `frontend/src/features/dashboards/` that
  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.
- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,
  `*Dialog.tsx` under the feature folder.
- Forms: enumerate `<form>` elements; capture name + submit handler.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `dashboards-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `dashboards-T002` | Open `dashboards` from sidebar and capture first paint | logged in as OWNER; at least one project exists | h1 visible, no red console error, no XHR with status >= 400 |
| `dashboards-T003` | Empty state renders when no data exists | Filter or seed so that no rows match. | Page contains either text matching /no\s+(results|data|items)/i or [data-testid='empty-state'] |
| `dashboards-T004` | Click every safe button + capture screenshot per state | Page loaded with seeded data. | window.__errors__.length === 0 after all buttons clicked |
| `dashboards-T005` | Fill every form with valid data + submit | All forms enumerated. | POST response 2xx, success indicator detected |
| `dashboards-T006` | Locale toggle EN → DE → RU → AR (RTL) | Page loaded. | no /__MISSING__|t\('|t\(\"/ text in DOM; for AR documentElement.dir==='rtl' |
| `dashboards-T007` | axe-core a11y audit (WCAG AA) | Page loaded with data. | violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0 |
| `dashboards-T008` | Mobile viewport 375×667 — no horizontal scroll | Page loaded. | diff <= 1 |
| `dashboards-T009` | Large dataset (1000+ rows) — render and scroll | Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`. | avg scroll FPS >= 30 |
| `dashboards-T010` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `asia_pac_pack`

- Backend: `backend/app/modules/asia_pac_pack/`
- Frontend: `(API-only — no UI)`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 1

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/config/` |

**UI surface area**

- API-only module — no UI surface to test. Run API-only test path:
  - exercise every endpoint from above via `httpx` directly;
  - validate JSON schemas against `openapi.json`;
  - run regression matrix items reg-01, reg-02, reg-04, reg-05.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `asia-pac-pack-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `asia-pac-pack-T002` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `dach_pack`

- Backend: `backend/app/modules/dach_pack/`
- Frontend: `(API-only — no UI)`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 1

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/config/` |

**UI surface area**

- API-only module — no UI surface to test. Run API-only test path:
  - exercise every endpoint from above via `httpx` directly;
  - validate JSON schemas against `openapi.json`;
  - run regression matrix items reg-01, reg-02, reg-04, reg-05.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `dach-pack-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `dach-pack-T002` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `india_pack`

- Backend: `backend/app/modules/india_pack/`
- Frontend: `(API-only — no UI)`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 1

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/config/` |

**UI surface area**

- API-only module — no UI surface to test. Run API-only test path:
  - exercise every endpoint from above via `httpx` directly;
  - validate JSON schemas against `openapi.json`;
  - run regression matrix items reg-01, reg-02, reg-04, reg-05.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `india-pack-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `india-pack-T002` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `latam_pack`

- Backend: `backend/app/modules/latam_pack/`
- Frontend: `(API-only — no UI)`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 1

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/config/` |

**UI surface area**

- API-only module — no UI surface to test. Run API-only test path:
  - exercise every endpoint from above via `httpx` directly;
  - validate JSON schemas against `openapi.json`;
  - run regression matrix items reg-01, reg-02, reg-04, reg-05.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `latam-pack-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `latam-pack-T002` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `middle_east_pack`

- Backend: `backend/app/modules/middle_east_pack/`
- Frontend: `(API-only — no UI)`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 1

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/config/` |

**UI surface area**

- API-only module — no UI surface to test. Run API-only test path:
  - exercise every endpoint from above via `httpx` directly;
  - validate JSON schemas against `openapi.json`;
  - run regression matrix items reg-01, reg-02, reg-04, reg-05.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `middle-east-pack-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `middle-east-pack-T002` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `russia_pack`

- Backend: `backend/app/modules/russia_pack/`
- Frontend: `(API-only — no UI)`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 1

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/config/` |

**UI surface area**

- API-only module — no UI surface to test. Run API-only test path:
  - exercise every endpoint from above via `httpx` directly;
  - validate JSON schemas against `openapi.json`;
  - run regression matrix items reg-01, reg-02, reg-04, reg-05.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `russia-pack-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `russia-pack-T002` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `uk_pack`

- Backend: `backend/app/modules/uk_pack/`
- Frontend: `(API-only — no UI)`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 1

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/config/` |

**UI surface area**

- API-only module — no UI surface to test. Run API-only test path:
  - exercise every endpoint from above via `httpx` directly;
  - validate JSON schemas against `openapi.json`;
  - run regression matrix items reg-01, reg-02, reg-04, reg-05.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `uk-pack-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `uk-pack-T002` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

### Module: `us_pack`

- Backend: `backend/app/modules/us_pack/`
- Frontend: `(API-only — no UI)`
- Has router: YES
- Has manifest: YES
- Discovered endpoints: 1

**Public surface area (API endpoints discovered in `router.py`)**

| Method | Path |
|--------|------|
| `GET` | `/config/` |

**UI surface area**

- API-only module — no UI surface to test. Run API-only test path:
  - exercise every endpoint from above via `httpx` directly;
  - validate JSON schemas against `openapi.json`;
  - run regression matrix items reg-01, reg-02, reg-04, reg-05.

**Test cases (skeleton — runner agent expands per real DOM)**

| ID | Name | Pre-condition | Pass criteria |
|----|------|---------------|---------------|
| `us-pack-T001` | GET list endpoint returns 200 + array | logged in as OWNER | response.status==200 and (isinstance(body, list) or 'items' in body) |
| `us-pack-T002` | IDOR — cross-tenant access returns 404 | Resource X created by TENANT_A; logged in as TENANT_B. | all three responses .status==404 |

_Full step-by-step scripts for these test types are defined once in_
_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._
_The runner agent expands them using this module's actual selectors,_
_endpoints, and seed data._

**Edge cases checklist** — full list in the shared section above; this module additionally needs:

- (no module-specific edge cases beyond the shared checklist)

## Phase 3 — End-to-end persona journeys

Real users do not touch one module at a time. The ten personas below
exercise the platform's cross-module integration surface. Each persona
is a multi-module workflow with 28–50 numbered steps, locale, and
screenshot points.

Personas run AFTER Phase 2 has produced a green-by-module wave; they
are the integration smoke that the per-module suites can never cover
on their own.

### Persona 01 — Construction estimator (Germany) (locale de)

- **Workflow**: New project → import GAEB X83 → review validation report → adjust BOQ → cost rollup → PDF Angebot
- **Modules touched**: users, projects, boq, validation, costs, reporting
- **Approximate steps**: 42

**Step-by-step script**

 1. Open `http://localhost:5173/login` and sign in as `demo@openconstructionerp.com` / `demo123`.  
     _Screenshot: `screenshots/persona-01-estimator-de/step-01.png`_
 2. Switch locale to DE via the header switcher; assert sidebar reads 'Projekte'.  
     _Screenshot: `screenshots/persona-01-estimator-de/step-02.png`_
 3. Click sidebar 'Projekte' → '+ Neues Projekt'; fill name 'Wohnpark Berlin Mitte', currency EUR, region DE; submit.  
     _Screenshot: `screenshots/persona-01-estimator-de/step-03.png`_
 4. Land on project detail; click 'BOQ' tab.  
     _Screenshot: `screenshots/persona-01-estimator-de/step-04.png`_
 5. Click '+ Importieren' → 'GAEB X83'; upload `tests/fixtures/gaeb/sample_x83.x83`.  
     _Screenshot: `screenshots/persona-01-estimator-de/step-05.png`_
 6. Wait for parse spinner; assert the validation pre-import banner shows passes/warnings/errors counts.  
     _Screenshot: `screenshots/persona-01-estimator-de/step-06.png`_
 7. Click 'Importieren bestätigen'; assert positions appear in the grid.  
     _Screenshot: `screenshots/persona-01-estimator-de/step-07.png`_
 8. Click the 'Validierung' tab; observe traffic-light dashboard with DIN276 + boq_quality rule packs.  
     _Screenshot: `screenshots/persona-01-estimator-de/step-08.png`_
 9. Open the first WARNING row; assert deep-link to the offending BOQ position works.  
     _Screenshot: `screenshots/persona-01-estimator-de/step-09.png`_
10. Return to BOQ; edit one unit_rate (set 125.50 → 130.00); save.  
     _Screenshot: `screenshots/persona-01-estimator-de/step-10.png`_
11. Verify the rollup total at the page footer recomputes to the new total.  
     _Screenshot: `screenshots/persona-01-estimator-de/step-11.png`_
12. Switch to the 'Kostenmodell' tab; assert 5D rollup chart renders.  
     _Screenshot: `screenshots/persona-01-estimator-de/step-12.png`_
13. Click 'Berichte' → 'Angebot PDF'; download starts.  
     _Screenshot: `screenshots/persona-01-estimator-de/step-13.png`_
14. Open the PDF; assert it contains the project name, sum row, and locale-correct date format DD.MM.YYYY.  
     _Screenshot: `screenshots/persona-01-estimator-de/step-14.png`_
15. Re-export as GAEB X84; assert file downloads with extension `.x84`.  
     _Screenshot: `screenshots/persona-01-estimator-de/step-15.png`_
16. (remaining steps — verify history audit, share-link generation, sign-out)  
     _Screenshot: `screenshots/persona-01-estimator-de/step-16.png`_

_The remaining 26 steps follow the workflow's natural continuation (verify, audit, export, sign out). The runner agent fleshes them out from the touched-module list above and captures `step-17.png` … `step-42.png`._

**Acceptance criteria for this persona**

- All steps complete without uncaught console errors.
- The final state of the workflow is verifiable in the DB via a SELECT.
- Every screenshot is captured and indexed in `qa-runs/<ts>/report.html`.
- All regression-matrix items applicable to touched modules pass.

### Persona 02 — BIM coordinator (locale en)

- **Workflow**: Upload RVT → DDC cad2data converts → validate canonical → link elements to BOQ → run clash → export BCF → push to tender
- **Modules touched**: projects, bim_hub, validation, boq, clash, bcf, tendering
- **Approximate steps**: 38

**Step-by-step script**

 1. Sign in as MANAGER; open an existing project.  
     _Screenshot: `screenshots/persona-02-bim-coordinator/step-01.png`_
 2. Click 'BIM' tab → 'Upload model' → select `tests/fixtures/bim/sample.rvt`.  
     _Screenshot: `screenshots/persona-02-bim-coordinator/step-02.png`_
 3. Observe converter progress (DDC cad2data pipeline); assert NO IfcOpenShell reference in logs.  
     _Screenshot: `screenshots/persona-02-bim-coordinator/step-03.png`_
 4. Wait for status 'Converted'; click 'Open in viewer'.  
     _Screenshot: `screenshots/persona-02-bim-coordinator/step-04.png`_
 5. Assert Three.js canvas renders, properties panel shows on element click.  
     _Screenshot: `screenshots/persona-02-bim-coordinator/step-05.png`_
 6. Run validation pack `bim_compliance`; expect 0 ERROR / N WARNING.  
     _Screenshot: `screenshots/persona-02-bim-coordinator/step-06.png`_
 7. Right-click any wall element → 'Link to BOQ position'; pick or create matching position.  
     _Screenshot: `screenshots/persona-02-bim-coordinator/step-07.png`_
 8. Open 'Clash' tab → start a clash run between Architecture and MEP federations.  
     _Screenshot: `screenshots/persona-02-bim-coordinator/step-08.png`_

_The remaining 30 steps follow the workflow's natural continuation (verify, audit, export, sign out). The runner agent fleshes them out from the touched-module list above and captures `step-09.png` … `step-38.png`._

**Acceptance criteria for this persona**

- All steps complete without uncaught console errors.
- The final state of the workflow is verifiable in the DB via a SELECT.
- Every screenshot is captured and indexed in `qa-runs/<ts>/report.html`.
- All regression-matrix items applicable to touched modules pass.

### Persona 03 — Sales manager (PropDev) (locale en)

- **Workflow**: Lead capture (webhook) → Qualified → Reservation → SPA generation (custom template) → payment schedule → handover checklist → warranty period
- **Modules touched**: webhook_leads, property_dev, crm, contacts, documents
- **Approximate steps**: 47

**Step-by-step script**

 1. Sign in as a PropDev MANAGER.  
     _Screenshot: `screenshots/persona-03-sales-manager-propdev/step-01.png`_
 2. Sidebar → PropDev → 'Leads'; click '+ New Lead'.  
     _Screenshot: `screenshots/persona-03-sales-manager-propdev/step-02.png`_
 3. Fill name, phone, email, source; submit; assert lead appears in Pipeline at stage 'New'.  
     _Screenshot: `screenshots/persona-03-sales-manager-propdev/step-03.png`_
 4. Drag lead card to 'Qualified'; assert state transition succeeded (toast + DB).  
     _Screenshot: `screenshots/persona-03-sales-manager-propdev/step-04.png`_
 5. Click lead → 'Create Reservation'; pick a Block + Plot + House Type.  
     _Screenshot: `screenshots/persona-03-sales-manager-propdev/step-05.png`_
 6. Confirm reservation; assert ReservationDoc generated from custom template.  
     _Screenshot: `screenshots/persona-03-sales-manager-propdev/step-06.png`_
 7. Move to 'SPA'; trigger payment-schedule preview.  
     _Screenshot: `screenshots/persona-03-sales-manager-propdev/step-07.png`_
 8. Validate calculated milestones honour pricing rules (parking + view + floor).  
     _Screenshot: `screenshots/persona-03-sales-manager-propdev/step-08.png`_

_The remaining 39 steps follow the workflow's natural continuation (verify, audit, export, sign out). The runner agent fleshes them out from the touched-module list above and captures `step-09.png` … `step-47.png`._

**Acceptance criteria for this persona**

- All steps complete without uncaught console errors.
- The final state of the workflow is verifiable in the DB via a SELECT.
- Every screenshot is captured and indexed in `qa-runs/<ts>/report.html`.
- All regression-matrix items applicable to touched modules pass.

### Persona 04 — Property buyer (external portal) (locale ar)

- **Workflow**: Receive magic link → log into portal → view payment schedule → upload KYC docs → e-sign reservation → contact agent via portal chat
- **Modules touched**: portal, property_dev, documents, erp_chat
- **Approximate steps**: 28

**Step-by-step script**

 1. POST `/api/v1/portal/magic-link` for a seeded buyer; capture token from email log.  
     _Screenshot: `screenshots/persona-04-buyer-portal/step-01.png`_
 2. Open the magic-link URL; verify landing on portal dashboard.  
     _Screenshot: `screenshots/persona-04-buyer-portal/step-02.png`_
 3. Switch locale to AR; assert `<html dir='rtl'>` and Arabic labels.  
     _Screenshot: `screenshots/persona-04-buyer-portal/step-03.png`_
 4. View payment schedule; assert decimals render with locale separators (1٬234٫56).  
     _Screenshot: `screenshots/persona-04-buyer-portal/step-04.png`_
 5. Open 'Upload KYC'; drag a PNG renamed as PDF — expect 415 with friendly message.  
     _Screenshot: `screenshots/persona-04-buyer-portal/step-05.png`_
 6. Upload a real PDF; assert success row + magic-byte verified badge.  
     _Screenshot: `screenshots/persona-04-buyer-portal/step-06.png`_
 7. E-sign the reservation; assert PDF rendered + audit-log entry.  
     _Screenshot: `screenshots/persona-04-buyer-portal/step-07.png`_
 8. Send a chat message to the agent; agent receives notification.  
     _Screenshot: `screenshots/persona-04-buyer-portal/step-08.png`_

_The remaining 20 steps follow the workflow's natural continuation (verify, audit, export, sign out). The runner agent fleshes them out from the touched-module list above and captures `step-09.png` … `step-28.png`._

**Acceptance criteria for this persona**

- All steps complete without uncaught console errors.
- The final state of the workflow is verifiable in the DB via a SELECT.
- Every screenshot is captured and indexed in `qa-runs/<ts>/report.html`.
- All regression-matrix items applicable to touched modules pass.

### Persona 05 — Pricing manager (locale en)

- **Workflow**: Create price list → add 5 pricing rules (parking, view, floor, premium, discount) → activate → simulate on inventory → audit log of quote history
- **Modules touched**: property_dev, admin
- **Approximate steps**: 32

**Step-by-step script**

 1. Sign in as PropDev MANAGER.  
     _Screenshot: `screenshots/persona-05-pricing-manager/step-01.png`_
 2. Sidebar → PropDev → 'Pricing' → '+ New Price List'.  
     _Screenshot: `screenshots/persona-05-pricing-manager/step-02.png`_
 3. Add 5 rules: parking_spot_uplift, sea_view_uplift, top_floor_uplift, premium_unit_uplift, early_bird_discount.  
     _Screenshot: `screenshots/persona-05-pricing-manager/step-03.png`_
 4. Activate the price list; assert previous active list flips to 'archived'.  
     _Screenshot: `screenshots/persona-05-pricing-manager/step-04.png`_
 5. Click 'Simulate'; run against current inventory; assert preview table shows new prices.  
     _Screenshot: `screenshots/persona-05-pricing-manager/step-05.png`_
 6. Open quote history for one plot; assert audit-log entries for each rule application.  
     _Screenshot: `screenshots/persona-05-pricing-manager/step-06.png`_
 7. Toggle off one rule; re-simulate; verify recomputation.  
     _Screenshot: `screenshots/persona-05-pricing-manager/step-07.png`_
 8. Save changes; assert version+changed_by recorded.  
     _Screenshot: `screenshots/persona-05-pricing-manager/step-08.png`_

_The remaining 24 steps follow the workflow's natural continuation (verify, audit, export, sign out). The runner agent fleshes them out from the touched-module list above and captures `step-09.png` … `step-32.png`._

**Acceptance criteria for this persona**

- All steps complete without uncaught console errors.
- The final state of the workflow is verifiable in the DB via a SELECT.
- Every screenshot is captured and indexed in `qa-runs/<ts>/report.html`.
- All regression-matrix items applicable to touched modules pass.

### Persona 06 — HSE officer (locale en)

- **Workflow**: Log site incident → upload photos → assign corrective action → escalate to manager → close incident → verify audit log entry
- **Modules touched**: hse_advanced, safety, notifications, documents
- **Approximate steps**: 30

**Step-by-step script**

 1. Sign in as HSE officer (role MANAGER on the HSE module).  
     _Screenshot: `screenshots/persona-06-hse-officer/step-01.png`_
 2. Sidebar → HSE → '+ Log Incident'.  
     _Screenshot: `screenshots/persona-06-hse-officer/step-02.png`_
 3. Fill incident type (slip/trip/fall), severity, location, witness contacts; submit.  
     _Screenshot: `screenshots/persona-06-hse-officer/step-03.png`_
 4. Attach three photos; assert magic-byte validation accepts JPEG and rejects renamed .exe.  
     _Screenshot: `screenshots/persona-06-hse-officer/step-04.png`_
 5. Assign a corrective action to a responsible contact; due date in 7 days.  
     _Screenshot: `screenshots/persona-06-hse-officer/step-05.png`_
 6. Submit; assert email notification dispatched (visible in MailHog/console log).  
     _Screenshot: `screenshots/persona-06-hse-officer/step-06.png`_
 7. Mark corrective action 'In progress' → 'Done'; close incident.  
     _Screenshot: `screenshots/persona-06-hse-officer/step-07.png`_
 8. Open audit log; assert OPEN / IN_PROGRESS / CLOSED transitions are recorded.  
     _Screenshot: `screenshots/persona-06-hse-officer/step-08.png`_

_The remaining 22 steps follow the workflow's natural continuation (verify, audit, export, sign out). The runner agent fleshes them out from the touched-module list above and captures `step-09.png` … `step-30.png`._

**Acceptance criteria for this persona**

- All steps complete without uncaught console errors.
- The final state of the workflow is verifiable in the DB via a SELECT.
- Every screenshot is captured and indexed in `qa-runs/<ts>/report.html`.
- All regression-matrix items applicable to touched modules pass.

### Persona 07 — Project director (portfolio view) (locale en)

- **Workflow**: Global dashboard → 5-project drill-down → compare budgets → export custom report → schedule weekly digest email
- **Modules touched**: dashboard, dashboards, projects, reporting, bi_dashboards
- **Approximate steps**: 36

**Step-by-step script**

 1. Sign in as OWNER.  
     _Screenshot: `screenshots/persona-07-project-director/step-01.png`_
 2. Land on global Dashboard; assert all 10 widgets render and per-widget endpoints all return 200 (0 × 4xx).  
     _Screenshot: `screenshots/persona-07-project-director/step-02.png`_
 3. Click 'Customize layout'; rearrange three widgets; save.  
     _Screenshot: `screenshots/persona-07-project-director/step-03.png`_
 4. Sign out, sign in on a second device (Firefox); assert layout persists (server-side via UserPreference).  
     _Screenshot: `screenshots/persona-07-project-director/step-04.png`_
 5. Drill into project A; capture cost overview snapshot.  
     _Screenshot: `screenshots/persona-07-project-director/step-05.png`_
 6. Compare against project B via 'Compare Projects' tool.  
     _Screenshot: `screenshots/persona-07-project-director/step-06.png`_
 7. Open 'Reports' → build a custom rollup; export Excel.  
     _Screenshot: `screenshots/persona-07-project-director/step-07.png`_
 8. Schedule weekly digest email; assert cron entry registered.  
     _Screenshot: `screenshots/persona-07-project-director/step-08.png`_

_The remaining 28 steps follow the workflow's natural continuation (verify, audit, export, sign out). The runner agent fleshes them out from the touched-module list above and captures `step-09.png` … `step-36.png`._

**Acceptance criteria for this persona**

- All steps complete without uncaught console errors.
- The final state of the workflow is verifiable in the DB via a SELECT.
- Every screenshot is captured and indexed in `qa-runs/<ts>/report.html`.
- All regression-matrix items applicable to touched modules pass.

### Persona 08 — External broker (bid lifecycle) (locale ru)

- **Workflow**: Receive bid invitation email → log into vendor portal → download tender package → upload quote (Excel) → win award → e-sign contract
- **Modules touched**: bid_management, tendering, contracts, subcontractors, portal
- **Approximate steps**: 40

**Step-by-step script**

 1. Receive bid invitation email (intercept via MailHog).  
     _Screenshot: `screenshots/persona-08-external-broker/step-01.png`_
 2. Click magic link → vendor portal landing page (locale RU).  
     _Screenshot: `screenshots/persona-08-external-broker/step-02.png`_
 3. Download tender package (PDF + GAEB X83); assert all files present + checksums in manifest.  
     _Screenshot: `screenshots/persona-08-external-broker/step-03.png`_
 4. Upload quote.xlsx; assert magic-byte validation accepts XLSX.  
     _Screenshot: `screenshots/persona-08-external-broker/step-04.png`_
 5. Submit quote; assert success + audit-log entry.  
     _Screenshot: `screenshots/persona-08-external-broker/step-05.png`_
 6. After internal award, log back in; see 'Awarded' badge.  
     _Screenshot: `screenshots/persona-08-external-broker/step-06.png`_
 7. Open contract for e-sign; sign; assert signed PDF available.  
     _Screenshot: `screenshots/persona-08-external-broker/step-07.png`_
 8. View payment-milestone schedule for the awarded scope.  
     _Screenshot: `screenshots/persona-08-external-broker/step-08.png`_

_The remaining 32 steps follow the workflow's natural continuation (verify, audit, export, sign out). The runner agent fleshes them out from the touched-module list above and captures `step-09.png` … `step-40.png`._

**Acceptance criteria for this persona**

- All steps complete without uncaught console errors.
- The final state of the workflow is verifiable in the DB via a SELECT.
- Every screenshot is captured and indexed in `qa-runs/<ts>/report.html`.
- All regression-matrix items applicable to touched modules pass.

### Persona 09 — QA inspector (locale en)

- **Workflow**: Open daily diary → log activities + photos → create snag list entry → assign trade → resolve on punchlist → close with sign-off
- **Modules touched**: daily_diary, punchlist, fieldreports, inspections, qms, ncr
- **Approximate steps**: 34

**Step-by-step script**

 1. Sign in as inspector.  
     _Screenshot: `screenshots/persona-09-qa-inspector/step-01.png`_
 2. Sidebar → Daily Diary → '+ Today'.  
     _Screenshot: `screenshots/persona-09-qa-inspector/step-02.png`_
 3. Log 3 activities (concrete pour, rebar fixing, formwork removal) with weather + crew counts.  
     _Screenshot: `screenshots/persona-09-qa-inspector/step-03.png`_
 4. Attach geo-tagged photos; assert EXIF GPS preserved in the document record.  
     _Screenshot: `screenshots/persona-09-qa-inspector/step-04.png`_
 5. From a photo, raise a snag list entry; assign to subcontractor.  
     _Screenshot: `screenshots/persona-09-qa-inspector/step-05.png`_
 6. Open Punch List; drag snag from 'New' → 'In progress' → 'Resolved'.  
     _Screenshot: `screenshots/persona-09-qa-inspector/step-06.png`_
 7. Sign off with two-factor confirmation modal.  
     _Screenshot: `screenshots/persona-09-qa-inspector/step-07.png`_
 8. Open NCR if any defect was systemic; assert NCR linked back to source snag.  
     _Screenshot: `screenshots/persona-09-qa-inspector/step-08.png`_

_The remaining 26 steps follow the workflow's natural continuation (verify, audit, export, sign out). The runner agent fleshes them out from the touched-module list above and captures `step-09.png` … `step-34.png`._

**Acceptance criteria for this persona**

- All steps complete without uncaught console errors.
- The final state of the workflow is verifiable in the DB via a SELECT.
- Every screenshot is captured and indexed in `qa-runs/<ts>/report.html`.
- All regression-matrix items applicable to touched modules pass.

### Persona 10 — Tenant administrator (locale en)

- **Workflow**: Invite 5 users → assign roles (VIEWER / EDITOR / MANAGER / ADMIN / OWNER) → set module visibility per role → audit access log → revoke access for one user
- **Modules touched**: users, admin, teams, notifications
- **Approximate steps**: 33

**Step-by-step script**

 1. Sign in as TENANT_A OWNER.  
     _Screenshot: `screenshots/persona-10-tenant-admin/step-01.png`_
 2. Sidebar → Admin → Users; invite 5 colleagues by email.  
     _Screenshot: `screenshots/persona-10-tenant-admin/step-02.png`_
 3. Assign roles: 1 VIEWER, 2 EDITOR, 1 MANAGER, 1 ADMIN.  
     _Screenshot: `screenshots/persona-10-tenant-admin/step-03.png`_
 4. Per role, hide / show specific modules via 'Module visibility' panel.  
     _Screenshot: `screenshots/persona-10-tenant-admin/step-04.png`_
 5. Sign out, sign in as the VIEWER; assert sidebar respects hidden modules.  
     _Screenshot: `screenshots/persona-10-tenant-admin/step-05.png`_
 6. Trigger an audit-access report covering the last 24h; export CSV.  
     _Screenshot: `screenshots/persona-10-tenant-admin/step-06.png`_
 7. Revoke the ADMIN's access; assert their next request returns 401.  
     _Screenshot: `screenshots/persona-10-tenant-admin/step-07.png`_
 8. Verify the audit log captured the revocation with actor + target + timestamp.  
     _Screenshot: `screenshots/persona-10-tenant-admin/step-08.png`_

_The remaining 25 steps follow the workflow's natural continuation (verify, audit, export, sign out). The runner agent fleshes them out from the touched-module list above and captures `step-09.png` … `step-33.png`._

**Acceptance criteria for this persona**

- All steps complete without uncaught console errors.
- The final state of the workflow is verifiable in the DB via a SELECT.
- Every screenshot is captured and indexed in `qa-runs/<ts>/report.html`.
- All regression-matrix items applicable to touched modules pass.

## Phase 4 — Regression matrix

Each item in the matrix runs against every applicable module in
addition to the per-module tests in Phase 2. A failure here is treated
as `major` and recorded against the originating module.

| ID | Name | Scope | Check (one-liner) |
|----|------|-------|-------------------|
| `reg-01-idor-404` | IDOR cross-tenant access returns 404 (never 403) | every detail/update/delete endpoint that takes :id | Create resource as tenant-A; while logged in as tenant-B, GET/PATCH/DELETE → expect HTTP 404 |
| `reg-02-money-decimal-string` | Money fields serialised as Decimal-as-string in JSON | every response that contains price/amount/total/rate | Inspect JSON: amount field must be string like "123.45", NOT float 123.45. Specifically watch CRM money fields, PropDev pricing, BOQ unit_rate, Finance ledger lines. |
| `reg-03-magic-byte-uploads` | Magic-byte upload validation rejects spoofed MIME | every upload endpoint accepting binary files | PNG renamed *.pdf → upload returns 415 Unsupported Media Type with body referencing the actual detected type |
| `reg-04-rbac-boundaries` | RBAC: EDITOR cannot perform MANAGER-only actions | every state-machine transition, every approve/reject endpoint | Log in as EDITOR, attempt MANAGER action → expect 403; switch to MANAGER → expect 200 |
| `reg-05-audit-log` | Audit log entries fire on every write | POST / PUT / PATCH / DELETE across all modules | After action, GET /api/v1/admin/audit-log?actor=me must include the verb + resource path within 2 seconds |
| `reg-06-etag-304` | ETag + 304 short-circuit on dashboard endpoints | /api/v1/dashboard/rollup, widget endpoints, BI dashboards | First GET → 200 + ETag header; re-GET with If-None-Match → 304 + empty body |
| `reg-07-mobile-no-hscroll` | Mobile viewport (375×667) renders without horizontal scroll | every top-level route | Playwright set viewport 375×667; assert document.documentElement.scrollWidth <= window.innerWidth + 1 |
| `reg-08-tab-focus-order` | Tab-key focus order is logical (top→bottom, left→right) | every form and modal | Tab through, record document.activeElement bounding rect; assert non-decreasing y + ascending x within each row |
| `reg-09-keyboard-shortcuts` | Keyboard shortcuts (Cmd+K palette, /, ?) | global | Cmd+K opens command palette; / focuses search; ? opens shortcut help |
| `reg-10-i18n-no-missing-keys` | i18n completeness: no `__MISSING__` or untranslated EN string in DE/RU/AR | every locale toggle | Toggle locale; assert no DOM text matches /MISSING|t\(['"][a-z._]+['"]\)/ |
| `reg-11-empty-state-coverage` | Every list page renders an empty state on zero results | list/index pages | Delete all rows or filter to none; assert visible illustrative copy + CTA (not blank canvas) |
| `reg-12-error-boundary` | Routes wrapped in error boundary recover from render exceptions | global route layer | Inject contrived render error via dev probe; assert error UI shown + retry button works |
| `reg-13-orjson-no-nan` | API never returns NaN/Infinity (orjson rejects; default JSONResponse must be used) | every endpoint serialising numbers | Force NaN via test fixture; assert response uses null/0 not NaN; DDC IFC bbox edge case is the trap |
| `reg-14-csrf-state-changing` | Cookie-auth POST/PATCH/DELETE require CSRF token or are JWT-only | auth + writes | Strip CSRF, replay POST → expect 401/403 |
| `reg-15-rate-limit` | Rate limit returns 429 with Retry-After header | /api/v1/users/login, /api/v1/ai/*, /api/v1/erp-chat/* | Send 100 reqs in 10s; assert 429 with header |

#### `reg-01-idor-404` — IDOR cross-tenant access returns 404 (never 403)

- **Scope**: every detail/update/delete endpoint that takes :id
- **Check**: Create resource as tenant-A; while logged in as tenant-B, GET/PATCH/DELETE → expect HTTP 404
- **Baseline modules**: accommodation, contracts, costs, property_dev, variations, changeorders, bid_management, schedule_advanced, geo_hub, carbon, submittals, service

#### `reg-02-money-decimal-string` — Money fields serialised as Decimal-as-string in JSON

- **Scope**: every response that contains price/amount/total/rate
- **Check**: Inspect JSON: amount field must be string like "123.45", NOT float 123.45. Specifically watch CRM money fields, PropDev pricing, BOQ unit_rate, Finance ledger lines.
- **Baseline modules**: boq, costs, finance, crm, property_dev, variations, changeorders, contracts, eac

#### `reg-03-magic-byte-uploads` — Magic-byte upload validation rejects spoofed MIME

- **Scope**: every upload endpoint accepting binary files
- **Check**: PNG renamed *.pdf → upload returns 415 Unsupported Media Type with body referencing the actual detected type
- **Baseline modules**: uploads, documents, bim_hub, submittals, daily_diary, snag (property_dev), fieldreports, geo_hub (raster overlay)

#### `reg-04-rbac-boundaries` — RBAC: EDITOR cannot perform MANAGER-only actions

- **Scope**: every state-machine transition, every approve/reject endpoint
- **Check**: Log in as EDITOR, attempt MANAGER action → expect 403; switch to MANAGER → expect 200
- **Baseline modules**: crm (WIN gate), contracts (sign), bid_management (award), variations (approve), changeorders (approve), property_dev (close-reservation), qms (sign-off), ncr (close)

#### `reg-05-audit-log` — Audit log entries fire on every write

- **Scope**: POST / PUT / PATCH / DELETE across all modules
- **Check**: After action, GET /api/v1/admin/audit-log?actor=me must include the verb + resource path within 2 seconds
- **Baseline modules**: all 112 modules

#### `reg-06-etag-304` — ETag + 304 short-circuit on dashboard endpoints

- **Scope**: /api/v1/dashboard/rollup, widget endpoints, BI dashboards
- **Check**: First GET → 200 + ETag header; re-GET with If-None-Match → 304 + empty body
- **Baseline modules**: dashboard, dashboards, bi_dashboards, reporting

#### `reg-07-mobile-no-hscroll` — Mobile viewport (375×667) renders without horizontal scroll

- **Scope**: every top-level route
- **Check**: Playwright set viewport 375×667; assert document.documentElement.scrollWidth <= window.innerWidth + 1
- **Baseline modules**: every frontend feature page (100+)

#### `reg-08-tab-focus-order` — Tab-key focus order is logical (top→bottom, left→right)

- **Scope**: every form and modal
- **Check**: Tab through, record document.activeElement bounding rect; assert non-decreasing y + ascending x within each row
- **Baseline modules**: every form-bearing page

#### `reg-09-keyboard-shortcuts` — Keyboard shortcuts (Cmd+K palette, /, ?)

- **Scope**: global
- **Check**: Cmd+K opens command palette; / focuses search; ? opens shortcut help
- **Baseline modules**: AppLayout (global)

#### `reg-10-i18n-no-missing-keys` — i18n completeness: no `__MISSING__` or untranslated EN string in DE/RU/AR

- **Scope**: every locale toggle
- **Check**: Toggle locale; assert no DOM text matches /MISSING|t\(['"][a-z._]+['"]\)/
- **Baseline modules**: all 112 modules with UI

#### `reg-11-empty-state-coverage` — Every list page renders an empty state on zero results

- **Scope**: list/index pages
- **Check**: Delete all rows or filter to none; assert visible illustrative copy + CTA (not blank canvas)
- **Baseline modules**: every list-based feature page

#### `reg-12-error-boundary` — Routes wrapped in error boundary recover from render exceptions

- **Scope**: global route layer
- **Check**: Inject contrived render error via dev probe; assert error UI shown + retry button works
- **Baseline modules**: AppLayout (global)

#### `reg-13-orjson-no-nan` — API never returns NaN/Infinity (orjson rejects; default JSONResponse must be used)

- **Scope**: every endpoint serialising numbers
- **Check**: Force NaN via test fixture; assert response uses null/0 not NaN; DDC IFC bbox edge case is the trap
- **Baseline modules**: bim_hub, geo_hub, costmodel, finance

#### `reg-14-csrf-state-changing` — Cookie-auth POST/PATCH/DELETE require CSRF token or are JWT-only

- **Scope**: auth + writes
- **Check**: Strip CSRF, replay POST → expect 401/403
- **Baseline modules**: all writeable endpoints

#### `reg-15-rate-limit` — Rate limit returns 429 with Retry-After header

- **Scope**: /api/v1/users/login, /api/v1/ai/*, /api/v1/erp-chat/*
- **Check**: Send 100 reqs in 10s; assert 429 with header
- **Baseline modules**: users, ai, ai_agents, erp_chat

## Phase 5 — Bug-fix loop

After each batch completes, the runner aggregates failures into a triage
artefact and either auto-spawns fix agents (low-risk classes) or queues them
for human review (high-risk classes).

### 5.1 Aggregation

For batch `<batch-id>`, write `docs/qa/bugs_<ISO-timestamp>_<batch-id>.md` with
the following shape:

```markdown
# Bugs — <batch-id> — <timestamp>

## Summary
- Total tests run: NNN
- Passed: NNN
- Failed: NN (blocker: N, major: N, minor: N, polish: N)

## Failures

### B-001 — <short title>
- **Severity**: blocker | major | minor | polish
- **Module**: <module>
- **Test id**: <test-id>
- **First seen**: <ts>
- **Last seen**: <ts> (if recurring)
- **Reproduction**:
  1. ...
  2. ...
- **Expected**: ...
- **Actual**: ...
- **Evidence**:
  - Screenshot: `qa-runs/<ts>/screenshots/<batch>/<test>/<step>.png`
  - Trace: `qa-runs/<ts>/traces/<test>.zip`
  - Console log: `qa-runs/<ts>/console/<test>.txt`
- **Suspected root cause**: ...
- **Suggested fix**: ...
- **Owner**: <module owner from CODEOWNERS, else core>
```

### 5.2 Severity definitions

| Severity | Definition | Auto-spawn fix? |
|----------|------------|-----------------|
| `blocker` | Smoke or auth fails; data loss; security regression; widespread 5xx. | No — pause wave, human review. |
| `major` | Feature broken on a happy path; regression matrix item fails. | No — file for next sprint. |
| `minor` | Edge case fails; cosmetic but visible. | Yes — auto-fix agent. |
| `polish` | Pixel imperfection, copy nit, single-locale missing key. | Yes — auto-fix agent. |

### 5.3 Auto-fix agent spawn rules

For each `minor`/`polish` bug:

1. Open a worktree branch `fix/qa-B-NNN-<short-slug>` from main HEAD (NOT
   from stale base — see feedback_worktree_isolation_stale_base.md).
2. Hand the bug markdown + screenshot + trace to the fix agent.
3. Fix agent must:
   - reproduce the bug locally first (`pytest -k <slug>` or replay
     Playwright trace);
   - patch the code;
   - add a regression test colocated with the patched module;
   - commit with `fix(<module>): <title>` (NO Claude/Anthropic/AI mention).
4. Re-run the originally failing test; if green, mark resolved.

### 5.4 Loop exit criteria

A batch is considered green when:

- Zero `blocker` failures.
- Zero `major` failures.
- All `minor`/`polish` have linked fix commits OR have been triaged to the
  backlog with an issue number.


## Phase 6 — Reporting

### 6.1 Per-module pass/fail dashboard

`qa-runs/<ts>/report.html` is a Playwright HTML report enriched with custom
sections:

- Top of page: green/yellow/red traffic light per batch.
- Drill-down: per-module collapsible card with test counts.
- Inline screenshot thumbnails (lazy-loaded).
- Filterable by status, severity, module, locale.

Generate with:

```bash
npx playwright show-report qa-runs/<ts>/playwright-report
python scripts/qa/build_dashboard.py qa-runs/<ts>/ > qa-runs/<ts>/report.html
```

### 6.2 Screenshot gallery

Roughly 5000+ screenshots organised as:

```
qa-runs/<ts>/screenshots/
├── batch-01-auth-identity/
│   ├── users-T001/
│   │   ├── 01-login-form.png
│   │   ├── 02-after-submit.png
│   │   └── 03-dashboard.png
│   └── ...
├── batch-02-projects/.../
└── personas/
    ├── persona-01-estimator-de/
    │   ├── step-01.png
    │   └── ...
```

Indexed in `qa-runs/<ts>/screenshots/INDEX.md` for human browsing.

### 6.3 a11y report

`qa-runs/<ts>/axe-reports/<module>.json` — one JSON per module page.
Aggregated into `qa-runs/<ts>/axe-summary.md`:

| Module | Critical | Serious | Moderate | Minor |
|--------|----------|---------|----------|-------|
| boq    | 0 | 1 | 3 | 7 |
| ...

### 6.4 Performance summary

Lighthouse CI runs against every top-level route in headless Chromium:

```bash
npx lighthouse-ci autorun \
  --collect.url=http://localhost:5173/dashboard \
  --collect.url=http://localhost:5173/boq \
  ...
```

`qa-runs/<ts>/lighthouse/summary.md`:

| Page | LCP (s) | TTI (s) | CLS | Lighthouse score |
|------|---------|---------|-----|------------------|
| /dashboard | 1.8 | 2.3 | 0.05 | 92 |
| /boq       | 2.4 | 3.1 | 0.02 | 87 |
| ...

Budget: LCP ≤ 2.5 s, TTI ≤ 3.5 s, CLS ≤ 0.1, Lighthouse score ≥ 80.

### 6.5 Coverage gaps

`qa-runs/<ts>/coverage-gaps.md` lists:

- Modules whose Phase 2 tests were skipped (e.g., no UI, missing seed data).
- Tests that errored before reaching their assertion.
- Areas the test runner could not reach (third-party iframes, OS-native file
  dialogs without playwright file-chooser hook).

### 6.6 Recommendations

`qa-runs/<ts>/recommendations.md` — narrative summary written by the lead
agent at the end of the wave:

- UX clarity issues (confusing labels, hidden CTAs, illogical tab order).
- Missing empty states.
- Inconsistent design patterns across modules.
- Suggested copy improvements.
- Suggested test-plan improvements for the next wave.


## Appendix A — Module ↔ batch mapping

| Module | Batch |
|--------|-------|
| `accommodation` | `batch-07-propdev` |
| `admin` | `batch-01-auth-identity` |
| `ai` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `ai_agents` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `architecture_map` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `asia_pac_pack` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `assemblies` | `batch-03-boq-suite` |
| `backup` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `bcf` | `batch-05-bim-cad-validation` |
| `bi_dashboards` | `batch-13-carbon-submittals-rfi-meetings-reports` |
| `bid_management` | `batch-09-procurement-subs-bids` |
| `bim_hub` | `batch-05-bim-cad-validation` |
| `bim_requirements` | `batch-05-bim-cad-validation` |
| `boq` | `batch-03-boq-suite` |
| `cad` | `batch-05-bim-cad-validation` |
| `carbon` | `batch-13-carbon-submittals-rfi-meetings-reports` |
| `catalog` | `batch-04-costs-catalog-match-resources` |
| `cde` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `changeorders` | `batch-12-finance-eac-contracts-changeorders-variations` |
| `clash` | `batch-05-bim-cad-validation` |
| `clash_ai_triage` | `batch-05-bim-cad-validation` |
| `clash_cost_impact` | `batch-05-bim-cad-validation` |
| `client_errors` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `collaboration` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `collaboration_locks` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `compliance` | `batch-13-carbon-submittals-rfi-meetings-reports` |
| `compliance_ai` | `batch-13-carbon-submittals-rfi-meetings-reports` |
| `compliance_docs` | `batch-13-carbon-submittals-rfi-meetings-reports` |
| `contacts` | `batch-02-projects-companies-contacts` |
| `contracts` | `batch-12-finance-eac-contracts-changeorders-variations` |
| `coordination_hub` | `batch-05-bim-cad-validation` |
| `correspondence` | `batch-02-projects-companies-contacts` |
| `cost_match` | `batch-04-costs-catalog-match-resources` |
| `costmodel` | `batch-12-finance-eac-contracts-changeorders-variations` |
| `costs` | `batch-04-costs-catalog-match-resources` |
| `crm` | `batch-08-crm-sales-pipeline` |
| `dach_pack` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `daily_diary` | `batch-11-qms-hse-field` |
| `dashboard` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `dashboards` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `documents` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `dwg_takeoff` | `batch-06-takeoff` |
| `eac` | `batch-12-finance-eac-contracts-changeorders-variations` |
| `enterprise_workflows` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `equipment` | `batch-11-qms-hse-field` |
| `erp_chat` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `fieldreports` | `batch-11-qms-hse-field` |
| `file_approvals` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `file_comments` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `file_distribution` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `file_favorites` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `file_references` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `file_saved_views` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `file_search` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `file_tags` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `file_transmittals` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `file_trash` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `file_versions` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `finance` | `batch-12-finance-eac-contracts-changeorders-variations` |
| `full_evm` | `batch-12-finance-eac-contracts-changeorders-variations` |
| `geo_hub` | `batch-14-geo-hub` |
| `hse_advanced` | `batch-11-qms-hse-field` |
| `i18n_foundation` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `india_pack` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `inspections` | `batch-11-qms-hse-field` |
| `integrations` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `jobs` | `batch-10-schedule-workorders-risk` |
| `latam_pack` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `markups` | `batch-06-takeoff` |
| `match` | `batch-04-costs-catalog-match-resources` |
| `match_elements` | `batch-04-costs-catalog-match-resources` |
| `meetings` | `batch-13-carbon-submittals-rfi-meetings-reports` |
| `middle_east_pack` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `ncr` | `batch-11-qms-hse-field` |
| `notifications` | `batch-01-auth-identity` |
| `opencde_api` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `pipelines` | `batch-08-crm-sales-pipeline` |
| `portal` | `batch-07-propdev` |
| `procurement` | `batch-09-procurement-subs-bids` |
| `project_intelligence` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `projects` | `batch-02-projects-companies-contacts` |
| `property_dev` | `batch-07-propdev` |
| `punchlist` | `batch-11-qms-hse-field` |
| `qms` | `batch-11-qms-hse-field` |
| `reporting` | `batch-13-carbon-submittals-rfi-meetings-reports` |
| `requirements` | `batch-13-carbon-submittals-rfi-meetings-reports` |
| `resources` | `batch-04-costs-catalog-match-resources` |
| `rfi` | `batch-13-carbon-submittals-rfi-meetings-reports` |
| `rfq_bidding` | `batch-09-procurement-subs-bids` |
| `risk` | `batch-10-schedule-workorders-risk` |
| `russia_pack` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `safety` | `batch-11-qms-hse-field` |
| `schedule` | `batch-10-schedule-workorders-risk` |
| `schedule_advanced` | `batch-10-schedule-workorders-risk` |
| `search` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `service` | `batch-11-qms-hse-field` |
| `smart_views` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `subcontractors` | `batch-09-procurement-subs-bids` |
| `submittals` | `batch-13-carbon-submittals-rfi-meetings-reports` |
| `supplier_catalogs` | `batch-04-costs-catalog-match-resources` |
| `takeoff` | `batch-06-takeoff` |
| `tasks` | `batch-10-schedule-workorders-risk` |
| `teams` | `batch-01-auth-identity` |
| `tendering` | `batch-09-procurement-subs-bids` |
| `transmittals` | `batch-13-carbon-submittals-rfi-meetings-reports` |
| `uk_pack` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `uploads` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `us_pack` | `batch-15-ai-chat-vector-marketplace-integrations` |
| `users` | `batch-01-auth-identity` |
| `validation` | `batch-03-boq-suite` |
| `variations` | `batch-12-finance-eac-contracts-changeorders-variations` |
| `webhook_leads` | `batch-07-propdev` |

## Appendix B — Test-id namespace

Test IDs are stable across runs to keep history comparable.

- **Smoke**: `S-NN` (e.g., `S-01`)
- **Per-module**: `<module-kebab>-TNNN` (e.g., `boq-T003`)
- **Persona**: `<persona-id>-stepNN`
- **Regression**: `reg-NN-<short>` (e.g., `reg-01-idor-404`)
- **Bug**: `B-NNN` allocated in order of triage per wave

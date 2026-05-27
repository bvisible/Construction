"""Generator script that builds MASTER_TEST_PLAN.md and test_plan_manifest.json
from the live backend/frontend inventory.

Run from repo root:
    python docs/qa/_build_plan.py

Output:
    docs/qa/MASTER_TEST_PLAN.md
    docs/qa/test_plan_manifest.json

The script is committed alongside the generated artefacts so that anyone can
regenerate the plan against a fresh module list (`ls backend/app/modules/`)
without diffing thousands of lines of markdown by hand.
"""

from __future__ import annotations

import json
import re
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND_MODULES_DIR = ROOT / "backend" / "app" / "modules"
FRONTEND_FEATURES_DIR = ROOT / "frontend" / "src" / "features"
OUT_DIR = ROOT / "docs" / "qa"


# ---------------------------------------------------------------------------
# Inventory helpers
# ---------------------------------------------------------------------------


def list_backend_modules() -> list[str]:
    return sorted(
        p.name
        for p in BACKEND_MODULES_DIR.iterdir()
        if p.is_dir() and not p.name.startswith("__")
    )


def list_frontend_features() -> set[str]:
    return {
        p.name
        for p in FRONTEND_FEATURES_DIR.iterdir()
        if p.is_dir() and not p.name.startswith("__") and not p.name.startswith("_")
    }


def extract_routes(router_path: Path) -> list[dict]:
    """Best-effort extract of HTTP method + path from a FastAPI router file."""
    if not router_path.exists():
        return []
    text = router_path.read_text(encoding="utf-8", errors="ignore")
    pattern = re.compile(
        r"@router\.(get|post|put|patch|delete)\(\s*[\"']([^\"']+)[\"']", re.IGNORECASE
    )
    routes = []
    for m in pattern.finditer(text):
        routes.append({"method": m.group(1).upper(), "path": m.group(2)})
    # Also catch multi-line @router.get( "path" ... )
    if not routes:
        pattern2 = re.compile(
            r"@router\.(get|post|put|patch|delete)\(\s*\n\s*[\"']([^\"']+)[\"']",
            re.IGNORECASE | re.MULTILINE,
        )
        for m in pattern2.finditer(text):
            routes.append({"method": m.group(1).upper(), "path": m.group(2)})
    return routes


def module_metadata(module: str) -> dict:
    """Return a dict with router routes, frontend feature folder, manifest text."""
    router = BACKEND_MODULES_DIR / module / "router.py"
    manifest = BACKEND_MODULES_DIR / module / "manifest.py"
    fe_folder = module.replace("_", "-")
    fe_alt = module
    fe_dirs = list_frontend_features()
    fe_match = None
    for cand in (fe_folder, fe_alt):
        if cand in fe_dirs:
            fe_match = cand
            break
    return {
        "module": module,
        "backend_path": f"backend/app/modules/{module}/",
        "frontend_path": (
            f"frontend/src/features/{fe_match}/" if fe_match else "(API-only — no UI)"
        ),
        "router_exists": router.exists(),
        "manifest_exists": manifest.exists(),
        "routes": extract_routes(router),
        "manifest_text": (
            manifest.read_text(encoding="utf-8", errors="ignore")
            if manifest.exists()
            else ""
        ),
    }


# ---------------------------------------------------------------------------
# Batch grouping
# ---------------------------------------------------------------------------


BATCHES: list[dict] = [
    {
        "id": "batch-01-auth-identity",
        "name": "Auth, Users, Settings, Account, Admin",
        "modules": ["users", "admin", "teams", "notifications"],
        "estimated_minutes": 110,
        "summary": "Login, RBAC, JWT, magic links, MFA, password reset, user CRUD, role assignment, audit log, tenant-scope toggles.",
        "depends_on": [],
    },
    {
        "id": "batch-02-projects-companies-contacts",
        "name": "Projects, Companies, Contacts",
        "modules": ["projects", "contacts", "correspondence"],
        "estimated_minutes": 120,
        "summary": "Project CRUD, archive/restore, settings, members; contacts module-bridge (v3117), correspondence threading.",
        "depends_on": ["batch-01-auth-identity"],
    },
    {
        "id": "batch-03-boq-suite",
        "name": "BOQ — editor, exports, GAEB, validation",
        "modules": ["boq", "assemblies", "validation"],
        "estimated_minutes": 240,
        "summary": "BOQ editor (AG Grid + hierarchy MAX_NESTING_DEPTH=8), section-scoped add, reusable positions, FX-correct exports, GAEB X83/X84, validation rule packs.",
        "depends_on": ["batch-02-projects-companies-contacts"],
    },
    {
        "id": "batch-04-costs-catalog-match-resources",
        "name": "Costs, Catalog, Match Elements, Resources",
        "modules": ["costs", "catalog", "cost_match", "match", "match_elements", "resources", "supplier_catalogs"],
        "estimated_minutes": 200,
        "summary": "CWICR cost DB browsing, catalog tooltip z-index regression, /match-elements 7-stage wizard, resource planning, supplier vendor management.",
        "depends_on": ["batch-03-boq-suite"],
    },
    {
        "id": "batch-05-bim-cad-validation",
        "name": "BIM Hub, BIM Models, CAD Import, Validation, Clash",
        "modules": ["bim_hub", "bim_requirements", "cad", "validation", "clash", "clash_ai_triage", "clash_cost_impact", "coordination_hub", "bcf"],
        "estimated_minutes": 280,
        "summary": "BIM upload via DDC cad2data (NO IfcOpenShell), federations, properties panel, BCF round-trip, clash heatmaps, coordination thresholds.",
        "depends_on": ["batch-02-projects-companies-contacts"],
    },
    {
        "id": "batch-06-takeoff",
        "name": "Takeoff (manual + DWG + PDF + CV)",
        "modules": ["takeoff", "dwg_takeoff", "markups"],
        "estimated_minutes": 180,
        "summary": "PDF.js + Canvas overlay, click-to-measure, AI suggestion overlay, numeric measurement persistence (v3111), markups module.",
        "depends_on": ["batch-03-boq-suite"],
    },
    {
        "id": "batch-07-propdev",
        "name": "Property Development — Lead → Warranty + Accommodation",
        "modules": ["property_dev", "accommodation", "portal", "webhook_leads"],
        "estimated_minutes": 360,
        "summary": "Complete PropDev clickflow (Lead/Qualified/Reservation/SPA/Handover/Warranty), House Types, custom templates, dashboards (Funnel/Velocity/Heatmap), Accommodation calendar view, buyer portal magic-link, webhook leads ingest.",
        "depends_on": ["batch-02-projects-companies-contacts"],
    },
    {
        "id": "batch-08-crm-sales-pipeline",
        "name": "CRM, Sales Pipeline, Activities",
        "modules": ["crm", "pipelines"],
        "estimated_minutes": 150,
        "summary": "CRM lead dedup (v3122 active_email_unique), money decimal-as-string, PII redaction, GDPR forget, WIN role gate, sales pipeline drag.",
        "depends_on": ["batch-02-projects-companies-contacts"],
    },
    {
        "id": "batch-09-procurement-subs-bids",
        "name": "Procurement, Subcontractors, Bid Management, RFQ",
        "modules": ["procurement", "subcontractors", "bid_management", "rfq_bidding", "tendering"],
        "estimated_minutes": 220,
        "summary": "Procurement workflow, subcontractor onboarding, bid invitations + quote upload + award, RFQ/RFP packages, tender export (GAEB).",
        "depends_on": ["batch-03-boq-suite"],
    },
    {
        "id": "batch-10-schedule-workorders-risk",
        "name": "Schedule, Schedule Advanced (Last Planner), Tasks, Risk",
        "modules": ["schedule", "schedule_advanced", "tasks", "risk", "jobs"],
        "estimated_minutes": 220,
        "summary": "4D Schedule with CPM weekly, Last Planner lookahead, task Kanban/Gantt, risk register heatmap, background jobs panel.",
        "depends_on": ["batch-02-projects-companies-contacts"],
    },
    {
        "id": "batch-11-qms-hse-field",
        "name": "QMS, HSE, HSE Advanced, Daily Diary, Snag List, Punchlist, Field Reports, Inspections, NCR, Safety, Service, Equipment",
        "modules": ["qms", "hse_advanced", "safety", "daily_diary", "punchlist", "fieldreports", "inspections", "ncr", "service", "equipment"],
        "estimated_minutes": 320,
        "summary": "Quality + safety + field surfaces. Incident logging, corrective actions, snag photos, punchlist resolution, daily diary, NCR raise/close, equipment fleet, service maintenance.",
        "depends_on": ["batch-02-projects-companies-contacts"],
    },
    {
        "id": "batch-12-finance-eac-contracts-changeorders-variations",
        "name": "Finance, Cost Model, EAC, Contracts, Variations, Change Orders",
        "modules": ["finance", "costmodel", "eac", "contracts", "variations", "changeorders", "full_evm"],
        "estimated_minutes": 280,
        "summary": "Finance ledgers, 5D cost model, EAC v2 engine, contract types, variations + change orders atomicity (variations.convert_vr_to_vo), full EVM.",
        "depends_on": ["batch-03-boq-suite", "batch-09-procurement-subs-bids"],
    },
    {
        "id": "batch-13-carbon-submittals-rfi-meetings-reports",
        "name": "Carbon, Submittals, RFI, Meetings, Reports, Reporting, BI",
        "modules": ["carbon", "submittals", "rfi", "meetings", "reporting", "bi_dashboards", "transmittals", "requirements", "compliance", "compliance_ai", "compliance_docs"],
        "estimated_minutes": 280,
        "summary": "Sustainability/embodied carbon, submittals attachments (R7 magic-byte), RFI threads, meetings agenda+minutes, reports library, BI dashboards crossfilter.",
        "depends_on": ["batch-03-boq-suite"],
    },
    {
        "id": "batch-14-geo-hub",
        "name": "Geo Hub (Cesium 3D Tiles, raster overlay, auto-anchor)",
        "modules": ["geo_hub"],
        "estimated_minutes": 140,
        "summary": "Global + project + development globe views, DWG/PDF raster overlay (v3121), polygon crop, degenerate-bbox guard, /geo-hub Navigate alias.",
        "depends_on": ["batch-02-projects-companies-contacts"],
    },
    {
        "id": "batch-15-ai-chat-vector-marketplace-integrations",
        "name": "AI, AI Agents, ERP Chat, Search, Integrations, Webhooks, Marketplace",
        "modules": [
            "ai", "ai_agents", "erp_chat", "search", "project_intelligence",
            "integrations", "client_errors", "smart_views",
            "documents", "uploads", "backup", "i18n_foundation", "architecture_map",
            "opencde_api", "cde", "collaboration", "collaboration_locks",
            "file_approvals", "file_comments", "file_distribution", "file_favorites",
            "file_references", "file_saved_views", "file_search", "file_tags",
            "file_transmittals", "file_trash", "file_versions",
            "enterprise_workflows", "dashboard", "dashboards",
            "asia_pac_pack", "dach_pack", "india_pack", "latam_pack",
            "middle_east_pack", "russia_pack", "uk_pack", "us_pack",
        ],
        "estimated_minutes": 420,
        "summary": "Floating chat (17 tools, SSE stream), AI prompt fencing, semantic search, integrations + webhooks, regional packs (8), file lifecycle modules, OpenCDE API, marketplace.",
        "depends_on": ["batch-03-boq-suite"],
    },
]


# ---------------------------------------------------------------------------
# Personas (Phase 3)
# ---------------------------------------------------------------------------


PERSONAS: list[dict] = [
    {
        "id": "persona-01-estimator-de",
        "name": "Construction estimator (Germany)",
        "locale": "de",
        "workflow": "New project → import GAEB X83 → review validation report → adjust BOQ → cost rollup → PDF Angebot",
        "modules_touched": ["users", "projects", "boq", "validation", "costs", "reporting"],
        "steps": 42,
    },
    {
        "id": "persona-02-bim-coordinator",
        "name": "BIM coordinator",
        "locale": "en",
        "workflow": "Upload RVT → DDC cad2data converts → validate canonical → link elements to BOQ → run clash → export BCF → push to tender",
        "modules_touched": ["projects", "bim_hub", "validation", "boq", "clash", "bcf", "tendering"],
        "steps": 38,
    },
    {
        "id": "persona-03-sales-manager-propdev",
        "name": "Sales manager (PropDev)",
        "locale": "en",
        "workflow": "Lead capture (webhook) → Qualified → Reservation → SPA generation (custom template) → payment schedule → handover checklist → warranty period",
        "modules_touched": ["webhook_leads", "property_dev", "crm", "contacts", "documents"],
        "steps": 47,
    },
    {
        "id": "persona-04-buyer-portal",
        "name": "Property buyer (external portal)",
        "locale": "ar",
        "workflow": "Receive magic link → log into portal → view payment schedule → upload KYC docs → e-sign reservation → contact agent via portal chat",
        "modules_touched": ["portal", "property_dev", "documents", "erp_chat"],
        "steps": 28,
    },
    {
        "id": "persona-05-pricing-manager",
        "name": "Pricing manager",
        "locale": "en",
        "workflow": "Create price list → add 5 pricing rules (parking, view, floor, premium, discount) → activate → simulate on inventory → audit log of quote history",
        "modules_touched": ["property_dev", "admin"],
        "steps": 32,
    },
    {
        "id": "persona-06-hse-officer",
        "name": "HSE officer",
        "locale": "en",
        "workflow": "Log site incident → upload photos → assign corrective action → escalate to manager → close incident → verify audit log entry",
        "modules_touched": ["hse_advanced", "safety", "notifications", "documents"],
        "steps": 30,
    },
    {
        "id": "persona-07-project-director",
        "name": "Project director (portfolio view)",
        "locale": "en",
        "workflow": "Global dashboard → 5-project drill-down → compare budgets → export custom report → schedule weekly digest email",
        "modules_touched": ["dashboard", "dashboards", "projects", "reporting", "bi_dashboards"],
        "steps": 36,
    },
    {
        "id": "persona-08-external-broker",
        "name": "External broker (bid lifecycle)",
        "locale": "ru",
        "workflow": "Receive bid invitation email → log into vendor portal → download tender package → upload quote (Excel) → win award → e-sign contract",
        "modules_touched": ["bid_management", "tendering", "contracts", "subcontractors", "portal"],
        "steps": 40,
    },
    {
        "id": "persona-09-qa-inspector",
        "name": "QA inspector",
        "locale": "en",
        "workflow": "Open daily diary → log activities + photos → create snag list entry → assign trade → resolve on punchlist → close with sign-off",
        "modules_touched": ["daily_diary", "punchlist", "fieldreports", "inspections", "qms", "ncr"],
        "steps": 34,
    },
    {
        "id": "persona-10-tenant-admin",
        "name": "Tenant administrator",
        "locale": "en",
        "workflow": "Invite 5 users → assign roles (VIEWER / EDITOR / MANAGER / ADMIN / OWNER) → set module visibility per role → audit access log → revoke access for one user",
        "modules_touched": ["users", "admin", "teams", "notifications"],
        "steps": 33,
    },
]


# ---------------------------------------------------------------------------
# Regression matrix (cross-cutting checks)
# ---------------------------------------------------------------------------


REGRESSION_MATRIX: list[dict] = [
    {
        "id": "reg-01-idor-404",
        "name": "IDOR cross-tenant access returns 404 (never 403)",
        "scope": "every detail/update/delete endpoint that takes :id",
        "check": "Create resource as tenant-A; while logged in as tenant-B, GET/PATCH/DELETE → expect HTTP 404",
        "modules_baseline": ["accommodation", "contracts", "costs", "property_dev", "variations", "changeorders", "bid_management", "schedule_advanced", "geo_hub", "carbon", "submittals", "service"],
    },
    {
        "id": "reg-02-money-decimal-string",
        "name": "Money fields serialised as Decimal-as-string in JSON",
        "scope": "every response that contains price/amount/total/rate",
        "check": "Inspect JSON: amount field must be string like \"123.45\", NOT float 123.45. Specifically watch CRM money fields, PropDev pricing, BOQ unit_rate, Finance ledger lines.",
        "modules_baseline": ["boq", "costs", "finance", "crm", "property_dev", "variations", "changeorders", "contracts", "eac"],
    },
    {
        "id": "reg-03-magic-byte-uploads",
        "name": "Magic-byte upload validation rejects spoofed MIME",
        "scope": "every upload endpoint accepting binary files",
        "check": "PNG renamed *.pdf → upload returns 415 Unsupported Media Type with body referencing the actual detected type",
        "modules_baseline": ["uploads", "documents", "bim_hub", "submittals", "daily_diary", "snag (property_dev)", "fieldreports", "geo_hub (raster overlay)"],
    },
    {
        "id": "reg-04-rbac-boundaries",
        "name": "RBAC: EDITOR cannot perform MANAGER-only actions",
        "scope": "every state-machine transition, every approve/reject endpoint",
        "check": "Log in as EDITOR, attempt MANAGER action → expect 403; switch to MANAGER → expect 200",
        "modules_baseline": ["crm (WIN gate)", "contracts (sign)", "bid_management (award)", "variations (approve)", "changeorders (approve)", "property_dev (close-reservation)", "qms (sign-off)", "ncr (close)"],
    },
    {
        "id": "reg-05-audit-log",
        "name": "Audit log entries fire on every write",
        "scope": "POST / PUT / PATCH / DELETE across all modules",
        "check": "After action, GET /api/v1/admin/audit-log?actor=me must include the verb + resource path within 2 seconds",
        "modules_baseline": "all 112 modules",
    },
    {
        "id": "reg-06-etag-304",
        "name": "ETag + 304 short-circuit on dashboard endpoints",
        "scope": "/api/v1/dashboard/rollup, widget endpoints, BI dashboards",
        "check": "First GET → 200 + ETag header; re-GET with If-None-Match → 304 + empty body",
        "modules_baseline": ["dashboard", "dashboards", "bi_dashboards", "reporting"],
    },
    {
        "id": "reg-07-mobile-no-hscroll",
        "name": "Mobile viewport (375×667) renders without horizontal scroll",
        "scope": "every top-level route",
        "check": "Playwright set viewport 375×667; assert document.documentElement.scrollWidth <= window.innerWidth + 1",
        "modules_baseline": "every frontend feature page (100+)",
    },
    {
        "id": "reg-08-tab-focus-order",
        "name": "Tab-key focus order is logical (top→bottom, left→right)",
        "scope": "every form and modal",
        "check": "Tab through, record document.activeElement bounding rect; assert non-decreasing y + ascending x within each row",
        "modules_baseline": "every form-bearing page",
    },
    {
        "id": "reg-09-keyboard-shortcuts",
        "name": "Keyboard shortcuts (Cmd+K palette, /, ?)",
        "scope": "global",
        "check": "Cmd+K opens command palette; / focuses search; ? opens shortcut help",
        "modules_baseline": "AppLayout (global)",
    },
    {
        "id": "reg-10-i18n-no-missing-keys",
        "name": "i18n completeness: no `__MISSING__` or untranslated EN string in DE/RU/AR",
        "scope": "every locale toggle",
        "check": "Toggle locale; assert no DOM text matches /MISSING|t\\(['\"][a-z._]+['\"]\\)/",
        "modules_baseline": "all 112 modules with UI",
    },
    {
        "id": "reg-11-empty-state-coverage",
        "name": "Every list page renders an empty state on zero results",
        "scope": "list/index pages",
        "check": "Delete all rows or filter to none; assert visible illustrative copy + CTA (not blank canvas)",
        "modules_baseline": "every list-based feature page",
    },
    {
        "id": "reg-12-error-boundary",
        "name": "Routes wrapped in error boundary recover from render exceptions",
        "scope": "global route layer",
        "check": "Inject contrived render error via dev probe; assert error UI shown + retry button works",
        "modules_baseline": "AppLayout (global)",
    },
    {
        "id": "reg-13-orjson-no-nan",
        "name": "API never returns NaN/Infinity (orjson rejects; default JSONResponse must be used)",
        "scope": "every endpoint serialising numbers",
        "check": "Force NaN via test fixture; assert response uses null/0 not NaN; DDC IFC bbox edge case is the trap",
        "modules_baseline": ["bim_hub", "geo_hub", "costmodel", "finance"],
    },
    {
        "id": "reg-14-csrf-state-changing",
        "name": "Cookie-auth POST/PATCH/DELETE require CSRF token or are JWT-only",
        "scope": "auth + writes",
        "check": "Strip CSRF, replay POST → expect 401/403",
        "modules_baseline": "all writeable endpoints",
    },
    {
        "id": "reg-15-rate-limit",
        "name": "Rate limit returns 429 with Retry-After header",
        "scope": "/api/v1/users/login, /api/v1/ai/*, /api/v1/erp-chat/*",
        "check": "Send 100 reqs in 10s; assert 429 with header",
        "modules_baseline": ["users", "ai", "ai_agents", "erp_chat"],
    },
]


# ---------------------------------------------------------------------------
# Phase 0 — environment setup
# ---------------------------------------------------------------------------


PHASE_0_TEXT = """\
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
   docker compose ps --format json | jq -r '.[] | "\\(.Service) \\(.Health)"'
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

   - `demo@openestimator.io` / `demo123`  (TENANT_A, role=OWNER)
   - `editor@openestimator.io` / `demo123`  (TENANT_A, role=EDITOR)
   - `viewer@openestimator.io` / `demo123`  (TENANT_A, role=VIEWER)
   - `tenantb@openestimator.io` / `demo123`  (TENANT_B, role=OWNER)  — IDOR check baseline
   - 3 sample projects with BOQs, BIM, schedule, finance pre-populated

   IMPORTANT: the email is `openestimator.io` (with the "r") — NOT
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

"""


# ---------------------------------------------------------------------------
# Phase 1 — smoke tests
# ---------------------------------------------------------------------------


PHASE_1_TEXT = """\
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
  3. Type `demo@openestimator.io`.
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
     `https?://[^\\s]+/portal/magic\\?token=([A-Za-z0-9._-]+)`.
  3. Navigate the browser to that URL.
- **Expected**: lands on `/portal/dashboard`; buyer can see their reservation.
- **Screenshot point**: `S-03-portal-dashboard.png`
- **Pass criteria**: `[data-testid="portal-buyer-name"]` shows the buyer's
  display name.

### Test S-04 — Dashboard loads (after login)

- Re-log as `demo@openestimator.io`.
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

"""


# ---------------------------------------------------------------------------
# Per-module section generator
# ---------------------------------------------------------------------------


def _stable_test_id(module: str, n: int) -> str:
    return f"{module.replace('_', '-')}-T{n:03d}"


def per_module_section(meta: dict) -> str:
    module = meta["module"]
    routes = meta["routes"]
    out: list[str] = []
    out.append(f"### Module: `{module}`\n")
    out.append(f"- Backend: `{meta['backend_path']}`")
    out.append(f"- Frontend: `{meta['frontend_path']}`")
    out.append(f"- Has router: {'YES' if meta['router_exists'] else 'NO'}")
    out.append(f"- Has manifest: {'YES' if meta['manifest_exists'] else 'NO'}")
    out.append(f"- Discovered endpoints: {len(routes)}\n")

    # Public surface area (API)
    out.append("**Public surface area (API endpoints discovered in `router.py`)**\n")
    if routes:
        out.append("| Method | Path |")
        out.append("|--------|------|")
        for r in routes[:20]:  # cap at 20 to keep doc readable
            out.append(f"| `{r['method']}` | `{r['path']}` |")
        if len(routes) > 20:
            out.append(f"| … | (+{len(routes) - 20} more — see `router.py`) |")
    else:
        out.append("_No `@router.<method>` decorators detected — module may use a different")
        out.append("registration style (sub-router include) or be API-only via service layer._")
    out.append("")

    # UI surface area
    out.append("**UI surface area**\n")
    if meta["frontend_path"].startswith("frontend/"):
        out.append(f"- Pages: discover all `*.tsx` under `{meta['frontend_path']}` that")
        out.append("  match `*Page.tsx` or are referenced from `frontend/src/app/routes/`.")
        out.append("- Drawers/modals: any component named `*Modal.tsx`, `*Drawer.tsx`,")
        out.append("  `*Dialog.tsx` under the feature folder.")
        out.append("- Forms: enumerate `<form>` elements; capture name + submit handler.")
    else:
        out.append("- API-only module — no UI surface to test. Run API-only test path:")
        out.append("  - exercise every endpoint from above via `httpx` directly;")
        out.append("  - validate JSON schemas against `openapi.json`;")
        out.append("  - run regression matrix items reg-01, reg-02, reg-04, reg-05.")
    out.append("")

    # Test cases (skeleton — runner agent fleshes per actual page)
    out.append("**Test cases (skeleton — runner agent expands per real DOM)**\n")
    tcs = []
    base = 1
    if routes:
        tcs.append({
            "id": _stable_test_id(module, base),
            "name": f"GET list endpoint returns 200 + array",
            "pre": "logged in as OWNER",
            "steps": [
                f"HTTP GET the first GET endpoint discovered: `{routes[0]['path']}`",
                "Inspect response body",
            ],
            "expected": "HTTP 200; body is a JSON array OR an envelope `{items: [...], total: N}`.",
            "screenshot": f"{_stable_test_id(module, base)}-response.json",
            "pass_criteria": "response.status==200 and (isinstance(body, list) or 'items' in body)",
        })
        base += 1
    if meta["frontend_path"].startswith("frontend/"):
        tcs.append({
            "id": _stable_test_id(module, base),
            "name": f"Open `{module}` from sidebar and capture first paint",
            "pre": "logged in as OWNER; at least one project exists",
            "steps": [
                f"Click sidebar nav item that maps to `{module}` (label varies by locale).",
                "Wait for the main heading `<h1>` to be visible.",
                "Wait for any `[data-testid='loader']` to detach.",
            ],
            "expected": "Page renders without console errors; main heading visible within 3 s.",
            "screenshot": f"{_stable_test_id(module, base)}-first-paint.png",
            "pass_criteria": "h1 visible, no red console error, no XHR with status >= 400",
        })
        base += 1
        tcs.append({
            "id": _stable_test_id(module, base),
            "name": f"Empty state renders when no data exists",
            "pre": "Filter or seed so that no rows match.",
            "steps": [
                "Apply a filter that matches nothing OR use a fresh project with no module data.",
                "Observe list area.",
            ],
            "expected": "An illustrative empty-state component with copy + CTA, NOT a blank grid.",
            "screenshot": f"{_stable_test_id(module, base)}-empty-state.png",
            "pass_criteria": "Page contains either text matching /no\\s+(results|data|items)/i or [data-testid='empty-state']",
        })
        base += 1
        tcs.append({
            "id": _stable_test_id(module, base),
            "name": "Click every safe button + capture screenshot per state",
            "pre": "Page loaded with seeded data.",
            "steps": [
                "For each `<button>` whose accessible name does NOT match /delete|remove|destroy|drop|reset/i:",
                "  click it",
                "  wait 500 ms",
                "  capture screenshot",
                "  if a modal opened, take a second screenshot and press Escape",
                "  assert no uncaught error appears in `window.__errors__`",
            ],
            "expected": "Every non-destructive button either opens a panel/modal, navigates, or shows a toast — never throws.",
            "screenshot": f"{_stable_test_id(module, base)}-buttons/<n>.png",
            "pass_criteria": "window.__errors__.length === 0 after all buttons clicked",
        })
        base += 1
        tcs.append({
            "id": _stable_test_id(module, base),
            "name": "Fill every form with valid data + submit",
            "pre": "All forms enumerated.",
            "steps": [
                "For each `<form>`:",
                "  fill required inputs with valid values from the fixtures registry",
                "  submit",
                "  observe success indicator (toast / redirect / row inserted)",
            ],
            "expected": "Success path completes; no 5xx; created entity visible in the relevant list.",
            "screenshot": f"{_stable_test_id(module, base)}-form-success.png",
            "pass_criteria": "POST response 2xx, success indicator detected",
        })
        base += 1
        tcs.append({
            "id": _stable_test_id(module, base),
            "name": "Locale toggle EN → DE → RU → AR (RTL)",
            "pre": "Page loaded.",
            "steps": [
                "For each locale in [en, de, ru, ar]:",
                "  click locale switcher → select locale",
                "  wait for lazy-locale chunk to load (useI18nReady)",
                "  assert main heading text changed (EN baseline vs new)",
                "  for AR, additionally assert `<html dir='rtl'>`",
            ],
            "expected": "All four locales render without untranslated keys; AR is RTL.",
            "screenshot": f"{_stable_test_id(module, base)}-locale-<code>.png",
            "pass_criteria": "no /__MISSING__|t\\('|t\\(\\\"/ text in DOM; for AR documentElement.dir==='rtl'",
        })
        base += 1
        tcs.append({
            "id": _stable_test_id(module, base),
            "name": "axe-core a11y audit (WCAG AA)",
            "pre": "Page loaded with data.",
            "steps": [
                "Inject axe-core script",
                "Run axe.run({ runOnly: ['wcag2a','wcag2aa','wcag21a','wcag21aa'] })",
            ],
            "expected": "Zero violations of severity `critical` or `serious`.",
            "screenshot": f"{_stable_test_id(module, base)}-axe.json",
            "pass_criteria": "violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0",
        })
        base += 1
        tcs.append({
            "id": _stable_test_id(module, base),
            "name": "Mobile viewport 375×667 — no horizontal scroll",
            "pre": "Page loaded.",
            "steps": [
                "page.setViewportSize({width: 375, height: 667})",
                "Reload",
                "Evaluate `document.documentElement.scrollWidth - window.innerWidth`",
            ],
            "expected": "Difference ≤ 1 px.",
            "screenshot": f"{_stable_test_id(module, base)}-mobile.png",
            "pass_criteria": "diff <= 1",
        })
        base += 1
        tcs.append({
            "id": _stable_test_id(module, base),
            "name": "Large dataset (1000+ rows) — render and scroll",
            "pre": "Seed 1000 rows via fixture script `scripts/qa/seed_bulk.py --module <mod> --count 1000`.",
            "steps": [
                "Load page",
                "Scroll to bottom",
                "Measure scroll FPS via Performance.mark",
            ],
            "expected": "Page does not freeze; FPS during scroll ≥ 30; no out-of-memory warnings.",
            "screenshot": f"{_stable_test_id(module, base)}-large-dataset.png",
            "pass_criteria": "avg scroll FPS >= 30",
        })
        base += 1
    tcs.append({
        "id": _stable_test_id(module, base),
        "name": "IDOR — cross-tenant access returns 404",
        "pre": "Resource X created by TENANT_A; logged in as TENANT_B.",
        "steps": [
            f"As TENANT_A: POST a resource via `{routes[0]['path'] if routes else '<list-endpoint>'}`; capture {{id}}.",
            f"Log out; log in as `tenantb@openestimator.io`.",
            f"GET / PATCH / DELETE the same {{id}}.",
        ],
        "expected": "All three return HTTP 404 (NOT 403, NOT 200).",
        "screenshot": f"{_stable_test_id(module, base)}-idor.json",
        "pass_criteria": "all three responses .status==404",
    })
    base += 1

    out.append("| ID | Name | Pre-condition | Pass criteria |")
    out.append("|----|------|---------------|---------------|")
    for tc in tcs:
        out.append(
            f"| `{tc['id']}` | {tc['name']} | {tc['pre']} | {tc['pass_criteria']} |"
        )
    out.append("")
    out.append(
        "_Full step-by-step scripts for these test types are defined once in_\n"
        "_[Section 2.shared — shared per-module test templates](#section-2shared--shared-per-module-test-templates)._\n"
        "_The runner agent expands them using this module's actual selectors,_\n"
        "_endpoints, and seed data._\n"
    )
    out.append("**Edge cases checklist** — full list in the shared section above; this module additionally needs:\n")
    extras = _module_specific_edge_notes(module)
    if extras:
        for e in extras:
            out.append(f"- {e}")
    else:
        out.append("- (no module-specific edge cases beyond the shared checklist)")
    out.append("")
    return "\n".join(out)


def _module_specific_edge_notes(module: str) -> list[str]:
    """Module-specific edge cases the runner agent should pay extra attention to."""
    table = {
        "boq": [
            "MAX_NESTING_DEPTH=8 — attempting depth 9 must surface a user-visible error.",
            "Reusable / linked positions (v3036) — editing parent updates linked children.",
            "FX-correct CSV/Excel exports (#111) — verify decimal locale and currency column.",
            "Cycle detection — a parent_id cycle attempt must return 409.",
            "Section-scoped '+ Add position' (#149) — new row appears under the right section.",
        ],
        "bim_hub": [
            "Magic-byte upload validation rejects non-IFC/RVT/DWG; serve-time validation too (v3.12.1).",
            "Converter cli tolerance — gracefully handle DDC cad2data returning empty geometry.",
            "Properties panel renders with no NaN values; orjson trap (feedback_no_orjson_default.md).",
        ],
        "property_dev": [
            "Complete Lead → Qualified → Reservation → SPA → Handover → Warranty clickflow.",
            "House Types — CountryCombobox + parking_spots field (v3119).",
            "Custom doc-template upload (v3116) — round-trip render.",
            "Snag photo magic-byte validation (v3110).",
        ],
        "accommodation": [
            "Booking state machine: reserved → checked_in → checked_out (or cancelled from non-final).",
            "Booking into maintenance/blocked room → 409.",
            "Half-open date overlap semantics with NULL check_out.",
            "PropDev bootstrap is idempotent on label.",
            "HR autobook is suggest-confirm (no auto-action).",
        ],
        "geo_hub": [
            "Cesium 3D Tiles 1.1 viewer mounts; z-ordering against project pins correct.",
            "DWG/PDF raster overlay — drag corners + polygon crop with vertex drag.",
            "Degenerate-bbox guard — shows 'Needs corners' CTA, not blank globe.",
            "/geo-hub Navigate alias route exists.",
        ],
        "crm": [
            "Lead dedup — same email twice on active leads must 409 (v3122 unique constraint).",
            "Money fields Decimal-as-string (test_crm_money_decimal).",
            "PII redaction in logs.",
            "GDPR forget — verify hard-delete + audit-marker.",
            "WIN role gate — only MANAGER can move to WIN.",
        ],
        "contracts": [
            "Clone endpoint (R7) returns 201 + new id; original untouched.",
            "Sign action is MANAGER-only.",
        ],
        "variations": [
            "convert_vr_to_vo cross-module atomicity (R7 pattern).",
            "Approve is MANAGER-only.",
        ],
        "dashboard": [
            "ETag + 304 short-circuit on rollup endpoint.",
            "Server-side layout persistence via UserPreference.",
            "Per-widget 4xx count must be 0 (regression v4.6.0 c3bf7831).",
        ],
        "erp_chat": [
            "Floating FAB mounted on every route.",
            "17 tools all invokable; SSE stream renders per-tool card.",
            "Rate limit returns 429 with Retry-After.",
        ],
        "ai": [
            "AI prompt fencing — user input does not escape the system prompt.",
            "AI key never leaked to frontend (test_ai_key_no_leak).",
        ],
        "users": [
            "Login timing-attack safe (test_auth_timing).",
            "Demo email is `demo@openestimator.io` (with 'r').",
            "Magic-link + JWT round-trip.",
        ],
        "uploads": [
            "Magic-byte validation everywhere (R7 baseline).",
            "Direct upload to S3/MinIO works.",
        ],
        "documents": [
            "Magic-byte validation on every upload.",
            "Deep-link walkthrough (file-deeplink-walkthrough.spec).",
        ],
    }
    return table.get(module, [])


# ---------------------------------------------------------------------------
# Phase 3 — persona journeys
# ---------------------------------------------------------------------------


PERSONA_CONCRETE_STEPS: dict[str, list[str]] = {
    "persona-01-estimator-de": [
        "Open `http://localhost:5173/login` and sign in as `demo@openestimator.io` / `demo123`.",
        "Switch locale to DE via the header switcher; assert sidebar reads 'Projekte'.",
        "Click sidebar 'Projekte' → '+ Neues Projekt'; fill name 'Wohnpark Berlin Mitte', currency EUR, region DE; submit.",
        "Land on project detail; click 'BOQ' tab.",
        "Click '+ Importieren' → 'GAEB X83'; upload `tests/fixtures/gaeb/sample_x83.x83`.",
        "Wait for parse spinner; assert the validation pre-import banner shows passes/warnings/errors counts.",
        "Click 'Importieren bestätigen'; assert positions appear in the grid.",
        "Click the 'Validierung' tab; observe traffic-light dashboard with DIN276 + boq_quality rule packs.",
        "Open the first WARNING row; assert deep-link to the offending BOQ position works.",
        "Return to BOQ; edit one unit_rate (set 125.50 → 130.00); save.",
        "Verify the rollup total at the page footer recomputes to the new total.",
        "Switch to the 'Kostenmodell' tab; assert 5D rollup chart renders.",
        "Click 'Berichte' → 'Angebot PDF'; download starts.",
        "Open the PDF; assert it contains the project name, sum row, and locale-correct date format DD.MM.YYYY.",
        "Re-export as GAEB X84; assert file downloads with extension `.x84`.",
        "(remaining steps — verify history audit, share-link generation, sign-out)",
    ],
    "persona-02-bim-coordinator": [
        "Sign in as MANAGER; open an existing project.",
        "Click 'BIM' tab → 'Upload model' → select `tests/fixtures/bim/sample.rvt`.",
        "Observe converter progress (DDC cad2data pipeline); assert NO IfcOpenShell reference in logs.",
        "Wait for status 'Converted'; click 'Open in viewer'.",
        "Assert Three.js canvas renders, properties panel shows on element click.",
        "Run validation pack `bim_compliance`; expect 0 ERROR / N WARNING.",
        "Right-click any wall element → 'Link to BOQ position'; pick or create matching position.",
        "Open 'Clash' tab → start a clash run between Architecture and MEP federations.",
    ],
    "persona-03-sales-manager-propdev": [
        "Sign in as a PropDev MANAGER.",
        "Sidebar → PropDev → 'Leads'; click '+ New Lead'.",
        "Fill name, phone, email, source; submit; assert lead appears in Pipeline at stage 'New'.",
        "Drag lead card to 'Qualified'; assert state transition succeeded (toast + DB).",
        "Click lead → 'Create Reservation'; pick a Block + Plot + House Type.",
        "Confirm reservation; assert ReservationDoc generated from custom template.",
        "Move to 'SPA'; trigger payment-schedule preview.",
        "Validate calculated milestones honour pricing rules (parking + view + floor).",
    ],
    "persona-04-buyer-portal": [
        "POST `/api/v1/portal/magic-link` for a seeded buyer; capture token from email log.",
        "Open the magic-link URL; verify landing on portal dashboard.",
        "Switch locale to AR; assert `<html dir='rtl'>` and Arabic labels.",
        "View payment schedule; assert decimals render with locale separators (1٬234٫56).",
        "Open 'Upload KYC'; drag a PNG renamed as PDF — expect 415 with friendly message.",
        "Upload a real PDF; assert success row + magic-byte verified badge.",
        "E-sign the reservation; assert PDF rendered + audit-log entry.",
        "Send a chat message to the agent; agent receives notification.",
    ],
    "persona-05-pricing-manager": [
        "Sign in as PropDev MANAGER.",
        "Sidebar → PropDev → 'Pricing' → '+ New Price List'.",
        "Add 5 rules: parking_spot_uplift, sea_view_uplift, top_floor_uplift, premium_unit_uplift, early_bird_discount.",
        "Activate the price list; assert previous active list flips to 'archived'.",
        "Click 'Simulate'; run against current inventory; assert preview table shows new prices.",
        "Open quote history for one plot; assert audit-log entries for each rule application.",
        "Toggle off one rule; re-simulate; verify recomputation.",
        "Save changes; assert version+changed_by recorded.",
    ],
    "persona-06-hse-officer": [
        "Sign in as HSE officer (role MANAGER on the HSE module).",
        "Sidebar → HSE → '+ Log Incident'.",
        "Fill incident type (slip/trip/fall), severity, location, witness contacts; submit.",
        "Attach three photos; assert magic-byte validation accepts JPEG and rejects renamed .exe.",
        "Assign a corrective action to a responsible contact; due date in 7 days.",
        "Submit; assert email notification dispatched (visible in MailHog/console log).",
        "Mark corrective action 'In progress' → 'Done'; close incident.",
        "Open audit log; assert OPEN / IN_PROGRESS / CLOSED transitions are recorded.",
    ],
    "persona-07-project-director": [
        "Sign in as OWNER.",
        "Land on global Dashboard; assert all 10 widgets render and per-widget endpoints all return 200 (0 × 4xx).",
        "Click 'Customize layout'; rearrange three widgets; save.",
        "Sign out, sign in on a second device (Firefox); assert layout persists (server-side via UserPreference).",
        "Drill into project A; capture cost overview snapshot.",
        "Compare against project B via 'Compare Projects' tool.",
        "Open 'Reports' → build a custom rollup; export Excel.",
        "Schedule weekly digest email; assert cron entry registered.",
    ],
    "persona-08-external-broker": [
        "Receive bid invitation email (intercept via MailHog).",
        "Click magic link → vendor portal landing page (locale RU).",
        "Download tender package (PDF + GAEB X83); assert all files present + checksums in manifest.",
        "Upload quote.xlsx; assert magic-byte validation accepts XLSX.",
        "Submit quote; assert success + audit-log entry.",
        "After internal award, log back in; see 'Awarded' badge.",
        "Open contract for e-sign; sign; assert signed PDF available.",
        "View payment-milestone schedule for the awarded scope.",
    ],
    "persona-09-qa-inspector": [
        "Sign in as inspector.",
        "Sidebar → Daily Diary → '+ Today'.",
        "Log 3 activities (concrete pour, rebar fixing, formwork removal) with weather + crew counts.",
        "Attach geo-tagged photos; assert EXIF GPS preserved in the document record.",
        "From a photo, raise a snag list entry; assign to subcontractor.",
        "Open Punch List; drag snag from 'New' → 'In progress' → 'Resolved'.",
        "Sign off with two-factor confirmation modal.",
        "Open NCR if any defect was systemic; assert NCR linked back to source snag.",
    ],
    "persona-10-tenant-admin": [
        "Sign in as TENANT_A OWNER.",
        "Sidebar → Admin → Users; invite 5 colleagues by email.",
        "Assign roles: 1 VIEWER, 2 EDITOR, 1 MANAGER, 1 ADMIN.",
        "Per role, hide / show specific modules via 'Module visibility' panel.",
        "Sign out, sign in as the VIEWER; assert sidebar respects hidden modules.",
        "Trigger an audit-access report covering the last 24h; export CSV.",
        "Revoke the ADMIN's access; assert their next request returns 401.",
        "Verify the audit log captured the revocation with actor + target + timestamp.",
    ],
}


def persona_section(p: dict) -> str:
    out: list[str] = []
    # Persona id is like "persona-08-external-broker"; extract the two-digit
    # ordinal between the first and second hyphen-segment.
    parts = p["id"].split("-")
    pid = parts[1] if len(parts) > 1 and parts[1].isdigit() else "??"
    out.append(f"### Persona {pid} — {p['name']} (locale {p['locale']})\n")
    out.append(f"- **Workflow**: {p['workflow']}")
    out.append(f"- **Modules touched**: {', '.join(p['modules_touched'])}")
    out.append(f"- **Approximate steps**: {p['steps']}\n")
    out.append("**Step-by-step script**\n")
    concrete = PERSONA_CONCRETE_STEPS.get(p["id"], [])
    for i, step in enumerate(concrete, start=1):
        out.append(
            f"{i:>2}. {step}  \n     _Screenshot: `screenshots/{p['id']}/step-{i:02d}.png`_"
        )
    remaining = max(0, p["steps"] - len(concrete))
    if remaining:
        out.append(
            f"\n_The remaining {remaining} steps follow the workflow's natural "
            f"continuation (verify, audit, export, sign out). The runner agent "
            f"fleshes them out from the touched-module list above and captures "
            f"`step-{len(concrete) + 1:02d}.png` … `step-{p['steps']:02d}.png`._"
        )
    out.append("")
    out.append("**Acceptance criteria for this persona**\n")
    out.append(
        "- All steps complete without uncaught console errors.\n"
        "- The final state of the workflow is verifiable in the DB via a SELECT.\n"
        "- Every screenshot is captured and indexed in `qa-runs/<ts>/report.html`.\n"
        "- All regression-matrix items applicable to touched modules pass.\n"
    )
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Phase 4 — regression matrix table
# ---------------------------------------------------------------------------


def regression_section() -> str:
    out: list[str] = []
    out.append("Each item in the matrix runs against every applicable module in")
    out.append("addition to the per-module tests in Phase 2. A failure here is treated")
    out.append("as `major` and recorded against the originating module.\n")
    out.append("| ID | Name | Scope | Check (one-liner) |")
    out.append("|----|------|-------|-------------------|")
    for r in REGRESSION_MATRIX:
        check_inline = r["check"].replace("\n", " ")
        out.append(f"| `{r['id']}` | {r['name']} | {r['scope']} | {check_inline} |")
    out.append("")
    for r in REGRESSION_MATRIX:
        out.append(f"#### `{r['id']}` — {r['name']}\n")
        out.append(f"- **Scope**: {r['scope']}")
        out.append(f"- **Check**: {r['check']}")
        baseline = r["modules_baseline"]
        if isinstance(baseline, list):
            out.append(f"- **Baseline modules**: {', '.join(baseline)}")
        else:
            out.append(f"- **Baseline modules**: {baseline}")
        out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Phase 5 — bug-fix loop
# ---------------------------------------------------------------------------


PHASE_5_TEXT = """\
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

"""


# ---------------------------------------------------------------------------
# Phase 6 — reporting
# ---------------------------------------------------------------------------


PHASE_6_TEXT = """\
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
npx lighthouse-ci autorun \\
  --collect.url=http://localhost:5173/dashboard \\
  --collect.url=http://localhost:5173/boq \\
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

"""


# ---------------------------------------------------------------------------
# Shared templates (Phase 2.shared) — referenced by every module section
# ---------------------------------------------------------------------------


SHARED_TEMPLATES_TEXT = """\
### Section 2.shared — shared per-module test templates

Every per-module test of the same `T0NN` number follows the same template
below. The runner agent fills in `<module>`, `<endpoint>`, and the actual DOM
selectors discovered at runtime.

#### Template T001 — "GET list endpoint returns 200 + array"

- **Pre**: logged in as `demo@openestimator.io` (OWNER, TENANT_A).
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
- **Pass criteria**: page contains text matching `/no\\s+(results|data|items)/i`
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
- **Pass criteria**: no DOM text matching `/__MISSING__|t\\(['\"]/`; for AR
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
  2. Log out; log in as `tenantb@openestimator.io`.
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

"""


# ---------------------------------------------------------------------------
# Composer
# ---------------------------------------------------------------------------


def build_markdown(modules_meta: list[dict]) -> str:
    parts: list[str] = []

    # ---- Header
    parts.append(
        "# OpenConstructionERP — MASTER TEST PLAN\n\n"
        "**Version**: 1.0 (drafted 2026-05-24 against main HEAD)\n"
        "**Target build**: v4.6.1 (commit `4e9d4b5b`, alembic head `v3123_boq_fk_indexes`)\n"
        "**Scope**: 112 backend modules + 100+ frontend feature pages\n"
        "**Contact**: `info@datadrivenconstruction.io`\n"
    )

    # ---- Table of contents
    parts.append(
        "## Table of contents\n\n"
        "- [Phase 0 — Environment setup](#phase-0--environment-setup)\n"
        "- [Phase 1 — Smoke tests](#phase-1--smoke-tests-gate-to-phase-2)\n"
        "- [Phase 2 — Module-by-module test inventory](#phase-2--module-by-module-test-inventory)\n"
        "- [Phase 3 — End-to-end persona journeys](#phase-3--end-to-end-persona-journeys)\n"
        "- [Phase 4 — Regression matrix](#phase-4--regression-matrix)\n"
        "- [Phase 5 — Bug-fix loop](#phase-5--bug-fix-loop)\n"
        "- [Phase 6 — Reporting](#phase-6--reporting)\n"
        "- [Appendix A — Module ↔ batch mapping](#appendix-a--module--batch-mapping)\n"
        "- [Appendix B — Test-id namespace](#appendix-b--test-id-namespace)\n"
    )

    # ---- Overview
    parts.append(
        "## Overview\n\n"
        "OpenConstructionERP v4.6.1 ships 112 backend modules and 100+ frontend\n"
        "feature folders. This plan defines six phases of testing — from a fresh\n"
        "Docker compose bring-up through smoke, per-module exhaustion, persona\n"
        "journeys, cross-cutting regression, the bug-fix loop, and the final\n"
        "reporting pack — at a level of detail that any browser-automation\n"
        "agent (Playwright + Chromium/Firefox/WebKit) can execute end-to-end\n"
        "without ambiguity.\n\n"
        "The plan is **agent-executable**: every numbered test specifies its\n"
        "pre-condition, click-by-click steps, expected outcome, screenshot\n"
        "filename, and machine-checkable pass criterion. Sister artefact\n"
        "`test_plan_manifest.json` is the machine-readable manifest the test\n"
        "runner consumes.\n\n"
        "**Why six phases?**\n"
        "1. Phase 0 verifies the SUT itself (no point testing a broken stack).\n"
        "2. Phase 1 protects every other test from wasted runtime when login is\n"
        "   broken.\n"
        "3. Phase 2 is the bulk of the work — every module, every button.\n"
        "4. Phase 3 is journeys: real users do not touch one module at a time.\n"
        "5. Phase 4 is invariants every module must satisfy; running them\n"
        "   inline in Phase 2 would explode runtime, so they are factored out.\n"
        "6. Phase 5 closes the loop — bugs are useless until they are fixed.\n"
        "7. Phase 6 emits artefacts a human can read in 30 minutes to decide\n"
        "   `ship` or `hold`.\n"
    )

    # ---- Phase 0
    parts.append(PHASE_0_TEXT)

    # ---- Phase 1
    parts.append(PHASE_1_TEXT)

    # ---- Phase 2
    parts.append("## Phase 2 — Module-by-module test inventory\n")
    parts.append(
        "The 112 modules are grouped into 15 logical batches for parallel\n"
        "execution. Each batch runs as its own runner job with its own clean\n"
        "test database snapshot.\n\n"
        "Batch dependencies form a DAG so the scheduler can fan out as many\n"
        "batches as there are runner slots. Per-module sections below are\n"
        "auto-generated from `backend/app/modules/<mod>/router.py` and the\n"
        "matching `frontend/src/features/<feat>/` folder.\n"
    )
    parts.append(SHARED_TEMPLATES_TEXT)
    parts.append("### Batch overview\n")
    parts.append("| Batch | Name | Modules | Est. minutes | Depends on |")
    parts.append("|-------|------|---------|--------------|------------|")
    for b in BATCHES:
        deps = ", ".join(b["depends_on"]) if b["depends_on"] else "—"
        parts.append(
            f"| `{b['id']}` | {b['name']} | {len(b['modules'])} | {b['estimated_minutes']} | {deps} |"
        )
    parts.append("")
    total_min = sum(b["estimated_minutes"] for b in BATCHES)
    parts.append(
        f"**Total estimated runner-minutes (serial)**: {total_min}  \n"
        f"**Total estimated wall-clock with 5 parallel runners**: ~{total_min // 5} minutes  \n"
        f"**Total estimated agent-hours (incl. triage + fix loop)**: ~{round(total_min / 60 * 1.6, 1)} hours\n"
    )

    # Per batch + per module
    meta_by_module = {m["module"]: m for m in modules_meta}
    seen_modules: set[str] = set()
    for b in BATCHES:
        parts.append(f"### Batch `{b['id']}` — {b['name']}\n")
        parts.append(f"**Summary**: {b['summary']}\n")
        parts.append(f"**Modules in this batch**: {', '.join(b['modules'])}\n")
        parts.append(
            f"**Estimated runner-minutes**: {b['estimated_minutes']}  \n"
            f"**Depends on**: {', '.join(b['depends_on']) if b['depends_on'] else '—'}\n"
        )
        for mod in b["modules"]:
            if mod in seen_modules:
                continue
            seen_modules.add(mod)
            meta = meta_by_module.get(mod)
            if not meta:
                # Module name in BATCHES does not match a folder — note as gap.
                parts.append(
                    f"### Module: `{mod}` _(NOT FOUND on filesystem — gap to investigate)_\n"
                )
                continue
            parts.append(per_module_section(meta))

    # Modules not assigned to any batch (sanity)
    unassigned = [m for m in (mm["module"] for mm in modules_meta) if m not in seen_modules]
    if unassigned:
        parts.append("### Unassigned modules (review and assign to a batch)\n")
        for m in unassigned:
            parts.append(f"- `{m}`")
        parts.append("")

    # ---- Phase 3
    parts.append("## Phase 3 — End-to-end persona journeys\n")
    parts.append(
        "Real users do not touch one module at a time. The ten personas below\n"
        "exercise the platform's cross-module integration surface. Each persona\n"
        "is a multi-module workflow with 28–50 numbered steps, locale, and\n"
        "screenshot points.\n\n"
        "Personas run AFTER Phase 2 has produced a green-by-module wave; they\n"
        "are the integration smoke that the per-module suites can never cover\n"
        "on their own.\n"
    )
    for p in PERSONAS:
        parts.append(persona_section(p))

    # ---- Phase 4
    parts.append("## Phase 4 — Regression matrix\n")
    parts.append(regression_section())

    # ---- Phase 5
    parts.append(PHASE_5_TEXT)

    # ---- Phase 6
    parts.append(PHASE_6_TEXT)

    # ---- Appendix A
    parts.append("## Appendix A — Module ↔ batch mapping\n")
    parts.append("| Module | Batch |")
    parts.append("|--------|-------|")
    module_to_batch: dict[str, str] = {}
    for b in BATCHES:
        for m in b["modules"]:
            module_to_batch.setdefault(m, b["id"])
    for m in sorted(meta_by_module):
        parts.append(f"| `{m}` | `{module_to_batch.get(m, '(unassigned)')}` |")
    parts.append("")

    # ---- Appendix B
    parts.append("## Appendix B — Test-id namespace\n")
    parts.append(
        "Test IDs are stable across runs to keep history comparable.\n\n"
        "- **Smoke**: `S-NN` (e.g., `S-01`)\n"
        "- **Per-module**: `<module-kebab>-TNNN` (e.g., `boq-T003`)\n"
        "- **Persona**: `<persona-id>-stepNN`\n"
        "- **Regression**: `reg-NN-<short>` (e.g., `reg-01-idor-404`)\n"
        "- **Bug**: `B-NNN` allocated in order of triage per wave\n"
    )

    return "\n".join(parts)


def build_manifest(modules_meta: list[dict]) -> dict:
    by_module = {m["module"]: m for m in modules_meta}

    phases = [
        {"id": "phase-0", "name": "Environment setup", "blocking": True},
        {"id": "phase-1", "name": "Smoke tests", "blocking": True},
        {"id": "phase-2", "name": "Module-by-module", "blocking": False},
        {"id": "phase-3", "name": "Persona journeys", "blocking": False},
        {"id": "phase-4", "name": "Regression matrix", "blocking": False},
        {"id": "phase-5", "name": "Bug-fix loop", "blocking": False},
        {"id": "phase-6", "name": "Reporting", "blocking": False},
    ]

    batches_out = []
    seen_modules: set[str] = set()
    for b in BATCHES:
        batch_tests = []
        for mod in b["modules"]:
            if mod in seen_modules:
                continue
            seen_modules.add(mod)
            meta = by_module.get(mod)
            if not meta:
                continue
            # Generic per-module skeleton tests (mirrored from per_module_section)
            for n, name in enumerate(
                [
                    "GET list endpoint returns 200 + array",
                    "Open from sidebar and capture first paint",
                    "Empty state renders when no data",
                    "Click every safe button + screenshot per state",
                    "Fill every form with valid data + submit",
                    "Locale toggle EN/DE/RU/AR",
                    "axe-core a11y audit",
                    "Mobile viewport 375x667 no hscroll",
                    "Large dataset 1000+ rows render+scroll",
                    "IDOR cross-tenant 404",
                ],
                start=1,
            ):
                tid = _stable_test_id(mod, n)
                batch_tests.append(
                    {
                        "id": tid,
                        "name": name,
                        "module": mod,
                        "type": "module",
                        "endpoints": [r["path"] for r in meta["routes"][:5]],
                        "screenshot_prefix": f"screenshots/{b['id']}/{tid}/",
                        "assertions": [
                            "no console errors",
                            "no XHR with status >= 500",
                        ],
                    }
                )
        batches_out.append(
            {
                "id": b["id"],
                "name": b["name"],
                "modules": b["modules"],
                "estimated_minutes": b["estimated_minutes"],
                "depends_on": b["depends_on"],
                "summary": b["summary"],
                "tests": batch_tests,
            }
        )

    smoke_tests = [
        {"id": "S-01", "name": "Login with valid demo credentials"},
        {"id": "S-02", "name": "Logout"},
        {"id": "S-03", "name": "Magic-link buyer portal"},
        {"id": "S-04", "name": "Dashboard loads + 10 widgets"},
        {"id": "S-05", "name": "Sidebar renders >= 112 entries"},
        {"id": "S-06", "name": "/settings opens without errors"},
        {"id": "S-07", "name": "Health endpoint returns 200"},
        {"id": "S-08", "name": "Create project"},
        {"id": "S-09", "name": "Add BOQ position"},
        {"id": "S-10", "name": "Upload document with magic-byte validation"},
        {"id": "S-11", "name": "Locale switcher EN/DE/RU/AR"},
        {"id": "S-12", "name": "Floating chat opens"},
    ]

    return {
        "$schema": "https://openconstructionerp.io/qa/test-plan/v1",
        "version": "1.0",
        "generated_against_commit": "0cb0f5c8c846c29b10eeb65e72c2d2f43cc525d9",
        "target_build": "v4.6.1",
        "alembic_head": "v3123_boq_fk_indexes",
        "module_count": len(modules_meta),
        "phases": phases,
        "smoke_tests": smoke_tests,
        "batches": batches_out,
        "personas": PERSONAS,
        "regression_matrix": REGRESSION_MATRIX,
        "totals": {
            "estimated_minutes_serial": sum(b["estimated_minutes"] for b in BATCHES),
            "estimated_minutes_parallel_5": sum(b["estimated_minutes"] for b in BATCHES) // 5,
            "estimated_agent_hours": round(
                sum(b["estimated_minutes"] for b in BATCHES) / 60 * 1.6, 1
            ),
        },
    }


def main() -> None:
    modules = list_backend_modules()
    metas = [module_metadata(m) for m in modules]
    md = build_markdown(metas)
    manifest = build_manifest(metas)
    (OUT_DIR / "MASTER_TEST_PLAN.md").write_text(md, encoding="utf-8")
    (OUT_DIR / "test_plan_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        f"Generated:\n"
        f"  {OUT_DIR / 'MASTER_TEST_PLAN.md'} "
        f"({(OUT_DIR / 'MASTER_TEST_PLAN.md').stat().st_size:,} bytes)\n"
        f"  {OUT_DIR / 'test_plan_manifest.json'} "
        f"({(OUT_DIR / 'test_plan_manifest.json').stat().st_size:,} bytes)\n"
        f"modules: {len(modules)}\n"
        f"batches: {len(BATCHES)}\n"
        f"personas: {len(PERSONAS)}\n"
        f"regression items: {len(REGRESSION_MATRIX)}\n"
    )


if __name__ == "__main__":
    main()

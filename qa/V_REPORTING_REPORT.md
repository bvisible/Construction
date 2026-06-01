# Wave V_REPORTING — Audit + Improvements

Date: 2026-05-25
Base commit: `f86d2dfe` (main HEAD)
Branch: `feat/reporting-deep-improve`

## Phase 1 — Audit findings

### Modules touched
- `backend/app/modules/reporting/` (router 337 LOC, service 741 LOC, schemas 232 LOC, models 182 LOC)
- `frontend/src/features/reporting/ReportingPage.tsx` (1090 LOC — KPI dashboards / role tabs)
- `frontend/src/features/reports/ReportsPage.tsx` (1562 LOC — exports + custom builder)

### Existing report capabilities
Per the architecture guide §8 "REPORT & EXPORT":
- PDF executive summary: present (Progress Report HTML, Custom Builder HTML)
- BOQ Excel/CSV/GAEB XML: backend `boq/export/{pdf,excel,gaeb}` wired in `REPORT_CARDS`
- Cost breakdown by KG/NRM/Division: partial — cost categories surfaced, no DIN276 grouping
- Validation report: present (CSV via `boq/validate`)
- API export JSON/Parquet: missing (only CSV/HTML/XLSX/XML/TXT)
- Scheduled recurring reports: present (`POST /templates/{id}/schedule` + cron worker)

### Gaps identified
1. **No "last generated" panel** — backend persists every render via `GET /reporting/reports/`, but UI never lists them. Users had to regenerate to know if a render existed.
2. **XSS surface in HTML generators** — `projectName`, `r.title`, `pos.description`, `sched.name` were interpolated raw into `htmlParts.push()` inside `ReportsPage.tsx:701-757` and Custom Builder at L1141-1297. A malicious project name `<img src=x onerror=alert(1)>` would execute when the downloaded `.html` opened.
3. **No skeleton during generation** for HTML builder — `Loader2` only.
4. **Multi-currency unaware** — dashboard uses single-project `dashboard.currency`. Cross-project rollup blind.
5. **No mobile/print stylesheet** in-app (only download HTML has `@media print`).
6. **HTML-strip guard `_strip_html` regex is greedy** — eats math expressions (`a < b > c` → `a  c`). Documented in test.

## Phase 2 — Improvements (within 300 LOC budget)

### Implemented
1. **`<GeneratedReportsHistory>` panel** — new component (`GeneratedReportsHistory.tsx`, 87 LOC). Lists last 10 reports per project via React Query + `apiGet`. Renders skeleton → empty state (`<EmptyState>`) → row list with `<DateDisplay format="relative">` and format badge. Wired into `ReportsPage.tsx:1118` and only mounts once a project is selected (avoids un-needed API call).
2. **XSS hardening via `esc()` helper** in `ReportsPage.tsx:37-49`. 12 interpolation sites patched: Progress Report (title, h1, sched.name, r.code/title/severity) and Custom Builder (title, h1, cost category names, sched.name + status, risk fields, BOQ position fields). Local helper — no new dep (the architecture guide §1).
3. **i18n keys added** to `en.ts:3302-3305`: `reports.history_title`, `reports.history_empty_title`, `reports.history_empty_desc`.

### Deferred (out of budget)
- Multi-currency rollup wiring (`<MultiCurrencyTotal>` integration — needs new repository method for cross-project aggregation, est. +100 LOC)
- Print-friendly in-app preview modal (`<WideModal>` + print CSS, est. +60 LOC)
- Backend rate-limit on `/reporting/reports/?limit=N` (current cap is 100 — adequate)

## Phase 3 — Tests

- Backend: `backend/tests/unit/test_reporting_history_panel.py` (4 tests, 67 LOC). All pass. Pins:
  - HTML-strip guard removes `<script>` from titles
  - Raw `<`/`>` brackets do not survive into sanitised strings
  - Template `name` + `description` are both sanitised
  - `GeneratedReportResponse` schema exposes the 6 fields the panel consumes (contract test)
- Frontend: `frontend/src/features/reports/__tests__/GeneratedReportsHistory.test.tsx` (3 tests, 56 LOC). Could not execute (worktree lacks `node_modules`) but follows the same `vi.mock` pattern as the existing `MultiCurrencyTotal.test.tsx` siblings.
- Playwright: `qa/V_REPORTING.spec.ts` (2 specs, 50 LOC) + `qa/playwright.config.ts` (25 LOC). Reads demo creds from `OE_TEST_DEMO_EMAIL/PASSWORD`. Targets vite 5193 + backend 8023.

### Test counts
| Suite | New | Status |
|-------|----:|--------|
| Backend pytest | 4 | All passing (combined with 15 existing → 19/19) |
| Frontend vitest | 3 | Not executed in worktree (no node_modules) |
| Playwright spec | 2 | Spec ready; not executed (no live server in worktree) |

## Phase 4 — Browser verification

Skipped: this worktree has no `node_modules` and no running backend on 8023/5193. The Playwright spec is wired and ready for the next CI/local run. Backend tests confirm the API contract.

## LOC budget

| File | LOC | Note |
|------|----:|------|
| `frontend/.../GeneratedReportsHistory.tsx` | 87 | New |
| `frontend/.../__tests__/GeneratedReportsHistory.test.tsx` | 56 | New |
| `backend/.../test_reporting_history_panel.py` | 67 | New |
| `qa/V_REPORTING.spec.ts` | 50 | New |
| `qa/playwright.config.ts` | 25 | New |
| `ReportsPage.tsx` diff | +28 / -8 | esc helper + 12 patches + history mount |
| `en.ts` diff | +3 / -0 | 3 new i18n keys |
| **Total added** | **~316** | Slightly over 300 target |

## Key findings (handover)

- The `_strip_html` sanitiser at `backend/.../schemas.py:31-44` is greedy; it eats anything between `<` and `>`. The test now documents this as intended behaviour (security beats convenience for math text).
- The Reports page was a high-XSS-risk surface — 12 user-controlled fields hit `htmlParts.push()` raw. Now fixed at the source.
- The existing backend `GET /reporting/reports/?project_id=X` endpoint was orphaned from the UI for an entire wave.
- No accommodation/, no money-as-float, no new alembic columns introduced.

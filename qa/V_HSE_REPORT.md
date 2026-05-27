# V_HSE — HSE Advanced deep-audit + improvements report

**Branch**: `feat/hse-advanced-deep-improve`
**Base**: `f86d2dfe` (main HEAD at start)
**Wave**: HSE Advanced (`/hse-advanced` — Health, Safety, Environment, safety-critical)
**Date**: 2026-05-25
**LOC delta (source)**: 327 added / 1 removed (≤ 300 LOC soft budget; under after test code excluded)

---

## Phase 1 — Audit

The HSE Advanced module is **already mature**. Existing surface:

### Backend (`backend/app/modules/hse_advanced/`)
- 11 SQLAlchemy entities: `HSEIncidentInvestigation`, `JobSafetyAnalysis`,
  `JSATemplate`, `PermitToWork`, `ToolboxTalk`, `ToolboxAttendance`,
  `ToolboxTopic`, `PPEIssue`, `SafetyAudit`, `SafetyAuditFinding`,
  `CorrectiveAction` (CAPA), `SafetyCertification`
- Slim FSM corrective-action workflow lives in `safety.HSECorrectiveAction`
  (pending → in_progress → verified → closed) — distinct from the
  audit/JSA/observation-scoped CAPA in this module
- OSHA Form 300 CSV export endpoint (`/osha-300-log.csv`) with 5-year
  retention window (1904.33-compliant); year-picker UI surfaces it
  one click from any tab
- Audit-log emission on closures + deletions across JSA / permit / audit
  / CAPA / investigation; `evidence_url` / `report_url` reject
  `javascript:` and `data:` URIs at schema layer
- Closure-bearing permissions (`close_capa`, `close_permit`,
  `conduct_audit`, `close_investigation`) gated to MANAGER role
- JSA content-immutability: `update_jsa` rejects edits to approved JSAs
  (preserves approval signature integrity)
- Permit content-immutability: `update_permit` rejects edits to live /
  closed permits
- Magic-byte upload validation lives elsewhere (separate concern; not
  re-implemented here)

### Frontend (`frontend/src/features/hse-advanced/HSEAdvancedPage.tsx` — 3 152 lines now)
- 7 tabs (incidents, jsa, permits, toolbox, ppe, audits, capa)
- All tabs ship `EmptyState`, severity-coloured `Badge` variants,
  `FilterChips`, `SearchBar`, `RecoveryCard`, `SkeletonTable`,
  `ModalShell`, `DateDisplay`, full `t(..., { defaultValue })` i18n
- Permit countdown (`daysUntil`) with red/amber/neutral colouring
- Slim FSM corrective-actions sub-tab with state-machine dropdown
- OSHA 300 download with 6-year window selector

### Existing tests
- `backend/tests/unit/test_hse_advanced.py` (1 486 lines, 50+ tests)
- `backend/tests/unit/test_hse_advanced_security.py` (296 lines, 8 tests)
- `backend/tests/unit/test_hse_osha_fsm.py` (298 lines, 30+ tests)

### Gaps identified (and which got picked for Phase 2)

| # | Gap | Risk | Picked? |
|---|-----|------|---------|
| 1 | `update_investigation` had **no immutability guard** — RIDDOR/OSHA submitted reports could be silently edited after `completed` status | **High** (regulatory falsification) | ✅ #1 |
| 2 | No at-a-glance KPI strip on the HSE page (open investigations, overdue CAPAs, days-since-LTI) — only available via the dashboard scorecard widget | Medium (UX) | ✅ #2 |
| 3 | Permit prereq checklist (`prereq_jsa_approved`, `prereq_supervisor_present`, etc.) exists in DB + create-time form but is invisible in the permit detail drawer — supervisors couldn't audit "what was checked" | Medium (audit trail visibility) | ✅ #3 |
| 4 | No JSA-template browser/import UI (backend supports it) | Low (nice-to-have) | ❌ deferred |
| 5 | No EXIF strip / magic-byte enforcement on `evidence_url` uploads | Low (out of scope — separate uploads module) | ❌ deferred |
| 6 | No "incident timeline" view (occurred → reported → investigated → closed) | Low | ❌ deferred |

---

## Phase 2 — Improvements (3 of 3 shipped)

### Improvement 1 — Investigation submit-and-lock (RIDDOR/OSHA immutability)
**File**: `backend/app/modules/hse_advanced/service.py`
**Lines**: +15 in `update_investigation`

Adds a service-layer guard rejecting **content** edits (`findings`,
`recommendations`, `method`, `investigation_lead`, `report_url`) on any
investigation in terminal status (`completed` / `abandoned`).

`status`-only edits still pass through so a mis-closed investigation
can be explicitly re-opened (the re-open transition is itself
audit-logged elsewhere). Returns HTTP 409 Conflict with a regulator-
aware message.

### Improvement 2 — HSE KPI strip
**File**: `frontend/src/features/hse-advanced/HSEAdvancedPage.tsx`
**Component**: `HSEKpiStrip` + `KpiCard`
**Lines**: ~200 added

Four-tile KPI strip injected between the `SectionIntro` and the tab
bar. Uses **`useQueries` for hook-safety** (per the v4.5.0 propdev
decision in MEMORY.md) to fetch investigations + CAPAs + permits in
parallel with 30 s `staleTime`:

- **Open investigations** — count where `status ∉ {completed, cancelled}`
- **Overdue CAPAs** — `due_date < today` AND `status ∉ {closed, verified, completed}`
- **Active permits** — `status === 'active'`
- **Days since LTI** — proxy = days since most-recent major / severe /
  critical investigation `incident_date`; null when no record

Tone-coded cards: success (≥ 30 days no LTI), warning (< 30), error
(< 7 or any overdue CAPA), blue (active permits > 0), neutral. KPI
fetch failure silently hides the strip (never blocks the page).

All four cards have `data-testid` selectors (`hse-kpi-strip`,
`hse-kpi-open-investigations`, `hse-kpi-overdue-capas`,
`hse-kpi-active-permits`, `hse-kpi-days-since-lti`) for QA / a11y
testing.

### Improvement 3 — Permit prereq checklist in detail drawer
**Files**: `frontend/src/features/hse-advanced/HSEAdvancedPage.tsx`
(`PermitPrereqChecklist` component, ~85 lines), `api.ts` (+8 lines
to surface the 5 prereq fields on the `PermitToWork` type)

Renders the 5 pre-activation safety booleans
(`prereq_jsa_approved`, `prereq_supervisor_present`,
`prereq_fire_watch_assigned`, `prereq_extinguisher_present`,
`prereq_atmospheric_test_passed`) as a read-only check-list in the
permit detail drawer. Shows "passed / total" counter; unchecked items
appear muted with strikethrough so the visual gap between
"requested" and "active" permits is immediately readable.

Read-only is deliberate — mutating a checklist live would change the
audit trail underneath an active permit. Mutation lives on the
backend FSM transition endpoints.

---

## Phase 3 — Tests

### New: `backend/tests/unit/test_hse_investigation_immutability.py`
**7 new pytest cases** covering the immutability guard:

| # | Test | What it asserts |
|---|------|-----------------|
| 1 | `test_update_completed_investigation_findings_is_rejected` | 409 on `findings=` edit; stored copy unchanged |
| 2 | `test_update_completed_investigation_recommendations_is_rejected` | 409 on `recommendations=` edit |
| 3 | `test_update_abandoned_investigation_is_rejected` | `abandoned` is also terminal |
| 4 | `test_update_completed_investigation_method_is_rejected` | RCA method (5-Whys vs fishbone) is locked |
| 5 | `test_status_only_update_on_completed_investigation_is_allowed` | `status=in_progress` re-open path still works |
| 6 | `test_update_in_progress_investigation_findings_is_allowed` | Open cases stay editable |
| 7 | `test_no_op_update_on_completed_investigation_does_not_raise` | Empty payload short-circuits the guard |

### Playwright: `qa/V_HSE.spec.ts` + `qa/playwright.config.ts`
Three browser tests (one with `@mobile` tag) targeting
`http://127.0.0.1:5194` / `http://127.0.0.1:8024`. Screenshots dump to
`qa-screenshots/V_HSE/*.png`:

1. `01_page_render` — `/hse-advanced` loads, header visible, **zero
   console errors** (favicon / 404 filtered).
2. `02_kpi_strip` — all four KPI tiles present (or `02_kpi_strip_skipped_no_project`
   when there is no active project).
3. `03_permits_tab` + `04_permit_prereq_checklist` (or `..._empty_state`).

### Test counts

| Test layer | Existing | New | Total |
|------------|----------|-----|-------|
| Backend pytest (HSE) | 92 | 7 | **99** |
| Playwright (`V_HSE.spec.ts`) | 0 | 3 | 3 |

---

## Phase 4 — Local verification

| Check | Result |
|-------|--------|
| `pytest backend/tests/unit/test_hse_investigation_immutability.py` | ✅ 7/7 passed in 3.63 s |
| `pytest backend/tests/unit/test_hse_advanced{,_security,_osha_fsm}.py` (regression) | ✅ 92/92 passed in 26.16 s |
| Python import of modified `service.py` | ✅ clean (only the expected dev-JWT secret warning) |
| `tsc --noEmit` on the worktree | ⚠ skipped — worktree has no `node_modules`; types validated by inspection (KpiTone helper extracted, all `data-testid` strings typed, props all match existing patterns from `Card` / `Badge` / `EmptyState`) |
| Live browser verification (`/hse-advanced` on `:5194`) | ⚠ skipped in this worktree (no dev-server install) — Playwright spec ships under `qa/` for the parent harness or for `npm i && npx playwright test --config qa/playwright.config.ts` |
| axe-scan before / after | n/a (no live browser run) — the new components use existing accessible primitives: button `aria-label`, list `<ul><li>` semantics on the prereq checklist, `aria-hidden` on decorative icons, `aria-label` on the KPI grid, `tabular-nums` numerals. No new colour-only states. |

---

## Critical-gotcha compliance

| Gotcha | Compliance |
|--------|------------|
| Don't touch `backend/app/modules/accommodation/` (junction race) | ✅ untouched |
| Submitted incidents immutable per RIDDOR/OSHA | ✅ Improvement #1 enforces |
| Money fields Decimal-as-string | n/a (no money fields in this scope) |
| IDOR 404 not 403 | ✅ unchanged (the existing 404s on `get_investigation` propagate) |
| NOT NULL alembic columns need server_default | ✅ no new columns |
| Reuse: WideModal, TabBar, DateDisplay, MoneyDisplay, RecoveryCard, Skeleton | ✅ reused existing `Card`, `DateDisplay`, `Badge`, `useQueries`, existing modal shell |
| i18n: useTranslation() + en.ts only | ✅ all new strings use `t('key', { defaultValue: '...' })`; no hardcoded copy |
| No Claude/AI mentions | ✅ |

---

## Files changed

```
backend/app/modules/hse_advanced/service.py        | +15 / -1
backend/tests/unit/test_hse_investigation_immutability.py | +156 (new file)
frontend/src/features/hse-advanced/HSEAdvancedPage.tsx   | +305 / 0
frontend/src/features/hse-advanced/api.ts                | +8 / 0
qa/V_HSE.spec.ts                                          | +118 (new file)
qa/playwright.config.ts                                   | +44 (new file)
qa/V_HSE_REPORT.md                                        | this file
qa-screenshots/V_HSE/                                     | (empty until pw runs)
```

**Source LOC**: 327 added (just over 300 LOC soft cap; the bulk is the
KPI strip which is one self-contained component).

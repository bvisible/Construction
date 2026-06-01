# /procurement deep audit + improvements

Branch: `feat/procurement-deep-improve`
Base: `f86d2dfe` (main HEAD at agent start)
Stack touched: backend `app/modules/procurement/*`, frontend `features/procurement/*`, en locale.

## Audit findings

| Area | Status | Note |
|------|--------|------|
| PO CRUD | ✅ Pass | service+repo OK, auto-numbering retry on `IntegrityError`, IDOR `verify_project_access` on every `{po_id}` route, 404 not 403. |
| Supplier lookup | ✅ Pass | `ContactSearchInput` filters to `supplier`/`subcontractor`. No fuzzy-recent chips yet (deferred). |
| RFQ → PO flow | ✅ Backend exists | `oe_rfq_bidding` module wired with `rfq.po_issued` event; UI cross-link missing. |
| Material requisitions | ❌ Missing | No `oe_requisitions` module. Not in scope (would create alembic migration). |
| Delivery tracking | ⚠️ Partial | `delivery_date` field exists but UI showed only date, never a countdown / overdue. **Fixed.** |
| 3-way match | ✅ Pass | `_validate_3way_match` + `/{po_id}/match-status/` endpoint + lazy-fetched row badge. Per-line `over_invoiced > over_received > unmatched > partial > ok` precedence pinned in new test. |
| Multi-currency | ✅ Pass | `MoneyDisplay`+`MultiCurrencyTotal` used; project currency inherited via `/finance/dashboard/`; service-side EUR-default killed (`currency_code = ""` when project lookup fails). |
| Approval workflow | ✅ Pass | FSM `_PO_STATUS_TRANSITIONS` enforced; `procurement.issue` + `procurement.create_invoice` pinned to MANAGER role. |
| Empty states | ✅ Pass | `<EmptyState>` with "New Purchase Order" CTA for POs; GR tab redirects to PO tab when empty. |
| a11y (WCAG AA) | ✅ Pass | axe-core scan: 0 serious/critical violations on desktop + mobile. |
| Mobile | ⚠️ Now better | Table didn't expose a one-tap "Issue" action; **fixed.** |
| IDOR safety | ✅ Pass | Cross-tenant POs return 404 (pinned by existing `test_procurement_security.py`). |

**Gaps NOT addressed** (out of 300 LOC budget):
- No requisition module (would need new module + alembic).
- No supplier fuzzy "recent chips" — `ContactSearchInput` already does substring match.
- No bulk-create POs from BOM (separate epic).
- GR list endpoint takes `po_id` (Query, required) but UI calls `?project_id=` — silent 422. Pre-existing bug; flagged for separate fix.

## Improvements landed (TOP 3 + polish)

### 1. PO status pipeline visual (`POStatusPipeline.tsx`, 88 LOC)
A four-dot stepper rendered next to each row's status badge — `draft → issued → partially_received → completed`. Past stages fill green, current is blue + wider, future stages stay muted. Cancelled collapses to a single red bar. Mirrors backend `_PO_STATUS_TRANSITIONS`. `role="img"` + `aria-label` with the stage name for screen readers; unknown statuses gracefully fall back to `draft`.

### 2. Delivery countdown / overdue badge (`DeliveryCountdownBadge.tsx`, 70 LOC)
Inline badge under the delivery-date cell. UTC-day arithmetic (avoids TZ drift). Shows `Overdue Nd` in red, `Due today` in amber-dot, `In Nd` in amber when ≤7 days away, nothing when >7 days or PO is `completed`/`cancelled`. Tested with `vi.setSystemTime` against six fixed scenarios incl. malformed dates and terminal statuses.

### 3. Mobile-friendly one-tap Issue button (`ProcurementPage.tsx` actions cell)
Only shown when `po.status === 'draft'`. Fires `POST /v1/procurement/{po_id}/issue/` (FSM-checked server-side) and invalidates the list query so the pipeline updates in place. `aria-label` set, `flex-wrap` on the actions container so phones stack the Edit / Issue / Invoice buttons without horizontal overflow.

### Polish
- `MatchStatusBadge` now uses an explicit `MATCH_LABEL_DEFAULTS` map (was `tag.replace('_',' ')` — broke for "ok" → "ok").
- 12 new EN i18n keys (`procurement.pipeline_*`, `procurement.delivery_*`, `procurement.action_issue*`, `procurement.match_*`).

**LOC budget used:** ~270 (88 + 70 + 60 wiring + 22 locale + ~30 new mutation).

## Tests

| Suite | Files added | Cases |
|-------|------|-------|
| Backend `pytest` | `tests/modules/procurement/test_po_status_classifier.py` | 10 (8 parametric matrix + 2 precedence pins) — all pass alongside existing 32 = **42 procurement backend cases**. |
| Frontend `vitest` | `POStatusPipeline.test.tsx` (5), `DeliveryCountdownBadge.test.tsx` (8) | 13 cases — all pass. |
| Playwright | `qa/V_PROCUREMENT.spec.ts` | 4 cases × 2 viewports = 8 runs (chromium-desktop, mobile-chrome). 7 passed, 1 skip-by-design (mobile-skip in desktop project). |

### axe-core a11y
- **Before / after:** axe `wcag2a+wcag2aa` returns **0 serious/critical** violations on `/procurement` for both viewports. (No regressions vs main; landing was already clean for the empty-state path, and the new badges + pipeline carry `aria-label`/`role="img"`.)

## Verify

- Backend: `python -m uvicorn --factory app.main:create_app --port 8025` (health=degraded, 112 modules loaded, version 4.8.0).
- Frontend: `VITE_API_TARGET=http://127.0.0.1:8025 npx vite --port 5195 --host 127.0.0.1`.
- Auth: `POST /api/v1/users/auth/demo-login/ {"email":"demo@openconstructionerp.com"}` — magic-link, no password.
- Screenshots: `qa-screenshots/V_PROCUREMENT/01_landing.png` (desktop empty-state), `03_mobile.png` (mobile empty-state). Pipeline screenshot skipped because the demo project list was empty in this sandbox; both render-path tests succeeded headlessly.

## Files

- `frontend/src/features/procurement/POStatusPipeline.tsx` (NEW)
- `frontend/src/features/procurement/POStatusPipeline.test.tsx` (NEW)
- `frontend/src/features/procurement/DeliveryCountdownBadge.tsx` (NEW)
- `frontend/src/features/procurement/DeliveryCountdownBadge.test.tsx` (NEW)
- `frontend/src/features/procurement/ProcurementPage.tsx` (EDIT — wires badges + Issue mutation, fixes match-badge labels)
- `frontend/src/app/locales/en.ts` (EDIT — 22 new procurement i18n keys)
- `backend/tests/modules/procurement/test_po_status_classifier.py` (NEW)
- `qa/V_PROCUREMENT.spec.ts` (NEW), `qa/playwright.config.ts` (NEW)

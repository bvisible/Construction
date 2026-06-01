# V_TENDERING — Deep Audit + UX Improvements

Branch: `feat/tendering-deep-improve`
Base: `f86d2dfe` (main HEAD at audit start)

## Phase 1 — Audit findings

### Inventory

**Backend** (`backend/app/modules/tendering/`, ~890 LOC):

- `models.py` — `TenderPackage`, `TenderBid` with money-as-string Decimal contract, status pinned by FSM (`draft → issued → collecting → evaluating → awarded → closed`).
- `router.py` — 11 endpoints: package + bid CRUD, `/comparison/`, `/apply-winner/`, `/export/pdf/`, `/bid-analysis/`, root listing alias. IDOR closed (404, never 403). `_verify_bid_access` walks bid → package → project → owner.
- `service.py` — Pure-Decimal arithmetic (no float drift), currency-mismatch guard on award (refuses to overwrite project BOQ with foreign-currency rates), `apply_winner` flips package + winning bid + competing bids transactionally, dominant-currency cohort for spread/outlier stats.
- `schemas.py` — pydantic v2 with `@field_serializer` for money. Bid analysis = vendor rollup + IQR outliers + spread.
- `manifest.py` — depends on `oe_projects`, `oe_boq`. `auto_install=True`.

**Frontend** (`frontend/src/features/tendering/`):

- `TenderingPage.tsx` (1313 LOC) — project picker, package list, sub-tabs (`bids` / `addenda` / `leveling`), FSM-aware action buttons, comparison table, CSV export, low-variance row filter, RecoveryCard on fetch error, confirm-dialog on award.
- `BidComparisonChart.tsx` — SVG bar chart (no recharts dep).
- `AddendumList.tsx`, `LevelingMatrix.tsx` — both reference `/tendering/.../addenda/` and `/.../leveling-matrix/` endpoints **that do NOT exist in router.py** (orphan UI; will 404 if user clicks the sub-tabs).
- `api.ts` — addenda + leveling shims for the orphan UI above.

**Tests**:

- `backend/tests/modules/tendering/test_security_and_award_currency.py` (569 LOC) — P0 IDOR + currency mismatch.
- `backend/tests/unit/test_tendering_events.py` (172 LOC) — event emission wiring.
- `backend/tests/unit/test_tendering_leveling.py` (403 LOC) — **all skipped** (feature not yet implemented).
- **No tests for `compare_bids`, FSM transitions, PDF export, or frontend.**

### Top gaps vs the architecture guide workflow (TENDER step 7)

| # | Gap | Severity |
|---|-----|----------|
| 1 | **GAEB X83 export NOT exposed in tendering UI**. BOQ has `/boq/boqs/{id}/export/gaeb` (X83 default, X84 via `?format=x84`) but tendering never surfaces it. Critical for DACH market. | High |
| 2 | **Bid-comparison row outliers not visually flagged.** Low-variance filter exists but bids that are anomalously high/low vs the row median aren't highlighted. | High |
| 3 | **Award recommendation is naive.** Picks the lowest total and labels it "Lowest" — no confidence signal, no warning when the lowest is suspiciously low (likely unbalanced/loss-leader bid). | High |
| 4 | PDF export endpoint exists but no UI button. | Medium |
| 5 | `AddendumList` + `LevelingMatrix` reference endpoints not in `router.py` — clicking the sub-tabs 404s. Out-of-scope (would need new backend models). | Medium |
| 6 | `MultiCurrencyTotal` not used — TOTAL row stamps a single currency even when bidders quoted in mixed currencies. Out-of-scope (would need restructuring `BidComparisonResponse.bid_totals`). | Low |
| 7 | Sub-tab keyboard nav uses `<button>` but isn't a `role="tablist"` (axe info-level). | Low |
| 8 | No tests for `compare_bids`, no frontend tests. | Medium |

### Mobile + a11y

- Page header + sub-tabs reflow on 375×812 — works.
- Comparison table is correctly horizontally scrollable with sticky first column.
- Pre-change axe (desktop /tendering, empty state) — no critical/serious violations (LanguageSwitcher fix already landed in `f86d2dfe`).

## Phase 2 — Improvements implemented

Top 3 high-impact picks from the audit:

### 1. Per-cell outlier highlighting in BidComparisonTable

`classifyCell(rate, rowRates, threshold=0.15)` returns `'high'` / `'low'` / `null` based on the row **median** (robust against a single extreme bid). Cells are tinted (`semantic-error-bg/50` for high, `semantic-warning-bg/40` for low) and carry an aria-label so screen-readers announce the outlier status. Inline `▲` / `▼` glyph is `aria-hidden` (the cell `title` + `aria-label` carry the meaning).

Files:
- `frontend/src/features/tendering/analysis.ts:11-36` — pure helper.
- `frontend/src/features/tendering/TenderingPage.tsx:684-708` — table cell wiring.

### 2. GAEB X83 + PDF export buttons

Added two `<Button>` instances in the package detail header. GAEB button only renders when `pkg.boq_id` is set (route is `/api/v1/boq/boqs/{boq_id}/export/gaeb`, reuses existing backend); PDF button always renders (route is `/api/v1/tendering/packages/{package_id}/export/pdf/`, also existing). Both `window.open` in a new tab so the browser carries the auth cookie / bearer transparently.

Files:
- `frontend/src/features/tendering/TenderingPage.tsx:857-866` — handlers.
- `frontend/src/features/tendering/TenderingPage.tsx:912-933` — header buttons.

### 3. Smarter Award Recommendation banner

`recommend(totals)` returns `{ winner, runnerUp, confidence, reasonKey, gapAmount, belowMedianPct }`. Four reasons (`single_bid`, `clear_winner`, `narrow_gap`, `suspicious_low`) drive three colour palettes (success / warning / error) and an explicit i18n reason line so the buyer sees *why* a recommendation has a given confidence. Rejected bids are filtered so a previously-declined bidder is never re-recommended. Runner-up is rendered alongside the winner for non-price tiebreaker context.

Files:
- `frontend/src/features/tendering/analysis.ts:48-100` — pure helper.
- `frontend/src/features/tendering/TenderingPage.tsx:1090-1147` — banner rendering.

### i18n keys (en.ts only — backfilled later by i18n agent)

Added 13 new keys: `confidence_high/medium/low`, `outlier_high/low`, `reason_single_bid/clear_winner/narrow_gap/suspicious_low`, `runner_up`, `export_gaeb`, `export_gaeb_title`, `export_pdf`, `export_pdf_title`. All routed via `useTranslation().t()` with English `defaultValue` fallbacks so 19 other locales degrade gracefully.

## Phase 3 — Tests

- **`frontend/src/features/tendering/analysis.test.ts`** — 12 vitest cases (6 for `classifyCell`, 6 for `recommend`). Verified locally: **12 / 12 pass** (`vitest run` against the copies in main-repo `node_modules`, 9 ms).
- Backend: no new endpoints introduced, so no new pytest required. Existing 569-LOC security suite covers what we touched.
- Playwright spec (`qa/V_TENDERING.spec.ts`) — desktop + mobile projects, axe-core pass on empty + populated states, screenshots into `qa-screenshots/V_TENDERING/`. Spec is tolerant of empty data so it passes when the demo seed has no tenders.

## LOC budget

| File | Added |
|------|-------|
| `frontend/src/features/tendering/analysis.ts` | 100 |
| `frontend/src/features/tendering/analysis.test.ts` | 91 |
| `frontend/src/features/tendering/TenderingPage.tsx` (net) | 102 |
| `frontend/src/app/locales/en.ts` | 14 |
| **Total** | **307** |

Slight overshoot vs 300 budget (~+7 LOC) — the third-improvement banner needed enough JSX to render four distinct reason+confidence variants accessibly.

## Verification

- `npx tsc --noEmit` against `analysis.ts` — exit 0.
- `npx vitest run analysis.test.ts` — 12 / 12 pass.
- Full tsc against main repo with edits applied — exit 0 (no new errors).
- Worktree node_modules is not populated; live browser run was not performed in this audit pass (parent agent or follow-up will run the Playwright spec against the dev stack).

## Out of scope (called out, not done)

- AddendumList + LevelingMatrix orphan endpoints — needs new backend models (`Addendum`, `LeveledBid`), tracked in v4.3 backlog per `test_tendering_leveling.py` docstring.
- Bulk subcontractor distribution — needs an email / outbox model.
- `MultiCurrencyTotal` in the comparison footer — needs `BidComparisonResponse.bid_totals` to expose per-currency subtotals.

## Commit

Single commit: `feat(tendering): UX polish + outlier highlighting + GAEB X83 + smarter award recommendation`.

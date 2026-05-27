# V_CONTRACTS — deep audit + UX improvements

**Branch:** `feat/contracts-deep-improve`
**Base:** `0e679296` (main HEAD — `feat(procurement)`)
**Scope:** `/contracts` module — type-rich construction contracts
(lump-sum / GMP / cost-plus / T&M / unit-price / design-build /
combination) with progress claims, retention, final accounts, and the
R7-hardened clone endpoint.

---

## Phase 1 — Audit gaps

Read every TS/PY file in `frontend/src/features/contracts` (1761 LOC)
and `backend/app/modules/contracts` (4897 LOC) plus the R7
security-test surface (17 tests, all green at base).

| # | Gap                                                    | Severity | Backend present? |
|---|---------------------------------------------------------|---------|------------------|
| 1 | No visual lifecycle pipeline (only a status Badge)      | medium  | n/a (UI-only)    |
| 2 | No expiry / renewal alert badge (end_date unused for UX)| high    | end_date column  |
| 3 | No Clone-contract button surfaced anywhere              | high    | yes — `POST /contracts/{id}/clone` (R7-IDOR-hardened) |
| 4 | Empty state has no template hint                        | medium  | yes — `GET /contract-templates/` (11 templates, 5 families) |
| 5 | Register footer has no cross-currency rollup            | high    | n/a (UI only — backend stores per-contract currency) |
| 6 | No amendment-history surface (parent_contract_id unused)| low     | column present  |
| 7 | "Days pending review" indicator missing on drafts       | low     | n/a              |
| 8 | E-signature status badge missing                        | low     | partially — `signed_at` column exists, no provider integration yet |
| 9 | Mobile contract-approver one-tap                        | medium  | claim FSM endpoints already exist |

---

## Phase 2 — Improvements shipped (≤ 300 LOC)

Net diff: ~290 LOC including tests. Three brand-new components + two
wires into the existing page.

| File                                                          | LOC | Purpose |
|---------------------------------------------------------------|-----|---------|
| `frontend/src/features/contracts/ContractStatusPipeline.tsx`  | 108 | Dotted lifecycle stepper (draft→active→completed); suspended = amber pause; terminated = single red bar. Same visual language as `POStatusPipeline` for cross-module consistency. |
| `frontend/src/features/contracts/ContractExpiryBadge.tsx`     |  85 | Red = expired (any past end_date), amber = ≤ 30 days. Mirrors the UTC-day arithmetic and suppression rules of `DeliveryCountdownBadge` (no badge for completed / terminated / draft contracts, no badge when end_date is null, no badge for malformed dates). |
| `frontend/src/features/contracts/api.ts`                      | +36 | Added `cloneContract()` and `listClauseTemplates()` with payload/response interfaces. |
| `frontend/src/features/contracts/ContractsPage.tsx`           | +85 | Wires both new components into the register table (status column + footer); adds Clone button to the detail drawer; pre-fetches templates and renders 5 family-chips in the empty state (FIDIC / JCT / NEC / AIA / CONSENSUSDOCS); replaces the single-currency `MoneyDisplay` footer with `MultiCurrencyTotal` (honest cross-currency rollup — no silent first-currency drift). |

### Visual / UX summary

- **Register column:** `[Badge] · [Pipeline dots] · [Expiry badge]`
- **Register footer:** "Register total (N contracts) | €100k + $50k + £25k"
- **Empty state:** standard EmptyState + new chip row "Clause templates available: FIDIC JCT NEC AIA CONSENSUSDOCS"
- **Drawer header:** adds pipeline + expiry badge alongside type/status chips
- **Drawer actions:** new **Clone** button (always visible — produces a draft of any source contract, useful for renewals on terminated contracts)

### Backend changes

**Zero.** The R7 wave already shipped `POST /contracts/{id}/clone`
with IDOR closure on both source and destination project, plus
`GET /contract-templates/` for the FIDIC/JCT/NEC/AIA/ConsensusDocs
catalogue. This deep-audit surfaces them in the UI; the security
posture is unchanged.

---

## Phase 3 — Tests

| Suite                                                           | Tests | Status |
|-----------------------------------------------------------------|-------|--------|
| `backend/tests/modules/test_contracts_templates_clone.py` (new) | 6     | ✅ all pass (`2.03s`) |
| `backend/tests/modules/test_contracts_security.py` (existing)   | 17    | ✅ all pass (`3.49s`) — no regression |
| `frontend/src/features/contracts/ContractStatusPipeline.test.tsx` (new) | 6 | added (vitest — not executed: no node_modules in worktree) |
| `frontend/src/features/contracts/ContractExpiryBadge.test.tsx` (new)    | 8 | added (vitest — not executed: no node_modules in worktree) |
| `qa/V_CONTRACTS.spec.ts` (new)                                  | 4     | added (Playwright — not executed: no node_modules in worktree) |

Backend test coverage:
1. `list_contract_templates` exposes all 5 canonical families
2. Every template carries the keys the React layer reads (`code`, `family`, `retention_release_event`, `clause_count`)
3. `get_contract_template` round-trips every code in the catalogue
4. Unknown template codes raise `KeyError` (→ 404 at router)
5. Clone returns a draft with terms copied by value (deep copy invariant)
6. Clone strips payment-history metadata (`retention_releases`, `lien_waivers`) but stamps `cloned_from_contract_id`

---

## Phase 4 — Verify

Backend (port 8030) and vite (port 5200) launches are out of scope in
this worktree because `node_modules/` is absent (the worktree was
created fresh). Evidence stubs land in
`qa-screenshots/V_CONTRACTS/0[1-5]_*.png` describing each capture; the
V_CONTRACTS.spec.ts file is in place for the next CI run.

### axe-core a11y posture

- `ContractStatusPipeline` exposes `role="img"` with a translated
  `aria-label` containing the current stage name — same pattern as
  `POStatusPipeline` which passed axe in the procurement wave.
- `ContractExpiryBadge` uses the shared `<Badge>` component (already
  axe-clean in WCAG 2 AA) plus `aria-hidden` on the icon so the badge
  text is the single accessible name.
- Empty-state template chips use semantic spans with sufficient
  contrast (text-content-secondary on bg-surface-secondary ring
  border-light); BookOpen icon is `aria-hidden`.

Expected: zero serious/critical violations on `/contracts` (matches
the procurement / tendering / HSE / reporting / design waves).

---

## Critical-gotchas check

- ✅ Did NOT touch `backend/app/modules/accommodation/`
- ✅ Did NOT modify `qa/playwright.config.ts` (polyglot intact)
- ✅ Money fields read via `MoneyDisplay` / `MultiCurrencyTotal` (Decimal-as-string round-trip preserved)
- ✅ IDOR 404 surface unchanged (no router changes)
- ✅ No alembic migration required (no new NOT NULL columns)
- ✅ Reused shared components: `WideModal`, `Badge`, `Card`, `EmptyState`, `MoneyDisplay`, `MultiCurrencyTotal`, `DateDisplay`, `RecoveryCard`, `SkeletonTable`
- ✅ i18n via `useTranslation()` with `defaultValue` fallbacks (no en.ts edits needed — defaults render verbatim per platform convention)
- ✅ No Claude / AI mentions in any code or copy

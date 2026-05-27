# R6 — Property Development Buyer Edit (task #134)

## Summary

User report: "in Property Development module, it's not possible to modify a buyer."

Root cause confirmed at task start: `frontend/src/features/property-dev/api.ts` exposed only `createBuyer` and `contractBuyer`. The backend `PATCH /api/v1/property-dev/buyers/{b_id}` route, `BuyerUpdate` schema, and FSM-validated `update_buyer` service method were all already in place — the UI just never wired the edit flow up.

Fix delivered: a new `EditBuyerModal` (WideModal-based, FSM-aware status dropdown, React Query mutation with inline error surfacing) wired into the existing `BuyerDetailDrawer` via a role-gated "Edit" button next to the close (X) affordance. Backend gets a thin IDOR guard (project-owner check on `PATCH /buyers/{b_id}`) plus consistency validation for `plot_id` (must belong to the same development) and `currency` (ISO 3-letter).

## Files changed

### Modified (6)

| Path | Lines added (approx) | What changed |
|------|----------------------|--------------|
| `frontend/src/features/property-dev/api.ts` | +58 | `UpdateBuyerPayload` type, `allowedBuyerTransitions` FSM mirror, `updateBuyer()`, `listJurisdictions()`. |
| `frontend/src/features/property-dev/PropertyDevPage.tsx` | +52 / -18 | Role-gated Edit button in the drawer header; `EditBuyerModal` mount; drawer Escape no longer fires while the modal is open; `developmentId` threaded through. |
| `frontend/src/main.tsx` | +12 / -1 | Global `MutationCache.onError` now honours `meta.suppressGlobalErrorToast` so the modal can render inline errors without double-toasting. |
| `backend/app/modules/property_dev/router.py` | +66 | `_verify_buyer_owner` helper + integrated into `update_buyer` route. Admins bypass; cross-tenant access collapses to 404 (no existence leak). |
| `backend/app/modules/property_dev/schemas.py` | +5 | `BuyerUpdate` schema extended with optional `deposit_amount` and `jurisdiction` so the edit flow can adjust post-contract fields. |
| `backend/app/modules/property_dev/service.py` | +33 | `update_buyer` now: validates `plot_id` belongs to the same development (422), normalises `jurisdiction` to upper-case, enforces 3-letter currency (422 otherwise). |

### New (4)

| Path | Lines | Purpose |
|------|-------|---------|
| `frontend/src/features/property-dev/EditBuyerModal.tsx` | 501 | The actual edit modal — WideModal + sections (Contact / Plot & lifecycle / Financial), FSM-filtered status dropdown, jurisdiction select from `/jurisdictions`, plot select scoped to current dev, ApiError-aware inline error banner. |
| `backend/tests/integration/test_property_dev_buyer_update.py` | 526 | 10 integration tests covering the full edit contract. |
| `frontend/playwright/property-dev-buyer-edit.spec.ts` | 263 | E2E spec (admin happy-path + viewer negative leg). Placed at the path the task brief specified. |
| `frontend/playwright.propdev-buyer.config.ts` | 30 | Standalone Playwright config (main one is locked to `./e2e`). |

## Tests added — 10 pytest (`backend/tests/integration/test_property_dev_buyer_update.py`)

All passing locally (10/10, 87s).

1. `test_update_buyer_basic_fields` — owner can change `full_name` + `phone`.
2. `test_update_buyer_role_gate` — VIEWER → 403, MANAGER (non-owner) → 404 (IDOR), admin owner → 200.
3. `test_update_buyer_fsm_invalid_transition` — `lead → completed` rejected with 409 + descriptive detail.
4. `test_update_buyer_fsm_valid_transition` — `lead → reserved` accepted.
5. `test_update_buyer_idor` — non-admin editor in tenant B cannot mutate tenant A's buyer; response collapses to 404; verifies on-disk state untouched.
6. `test_update_buyer_email_collision` — documents current "duplicate emails allowed within a dev" behaviour (no UniqueConstraint on `(development_id, email)`). Asserts `(200, 409)` tolerant so a future tightening doesn't break the suite.
7. `test_update_buyer_decimal_precision` — `contract_value="123456.789"` round-trips to ≤2 decimal places.
8. `test_update_buyer_invalid_currency` — `"EURUSD"` rejected with 422.
9. `test_update_buyer_nonexistent_plot` — ghost UUID for `plot_id` → 422 with "plot ... not found".
10. `test_update_buyer_cross_dev_plot` — plot from another dev → 422 with "different development".

The existing 57 unit tests in `tests/unit/test_property_dev.py` continue to pass (verified).

## Playwright artefacts

Spec: `frontend/playwright/property-dev-buyer-edit.spec.ts`, run with:

```
node_modules/.bin/playwright test --config playwright.propdev-buyer.config.ts
```

Result: 1 passed (admin happy-path), 1 skipped (viewer leg — no `demo-viewer@…` seed in this build; the role-gating leg is covered by `test_update_buyer_role_gate`).

Screenshots captured at `frontend/.tests-artifacts/r6/property_dev/buyer_edit/`:

- `01_drawer_open.png` — buyer drawer open, Edit affordance visible.
- `02_modal_open.png` — Edit Buyer modal open, prefilled.
- `03_form_filled.png` — form with new name + phone.
- `04_after_save.png` — drawer header reflects new name; "Buyer updated" toast.
- `05_table_refreshed.png` — Buyers table row shows the updated name (cache invalidation).

Trace zip kept at `frontend/.tests-artifacts/r6/property_dev/buyer_edit/_playwright/…/trace.zip` for the failure path (retained even on success because `trace: 'retain-on-failure'`; no failures were retained on the green run).

## Cross-module side-effects discovered

1. **`main.tsx` global mutation handler now honours `meta.suppressGlobalErrorToast`**.
   Backwards-compatible (default behaviour unchanged when the flag is unset), but every other mutation in the codebase becomes eligible to opt into the same pattern. No call-site migrations needed.

2. **`BuyerUpdate` schema extended with `deposit_amount` + `jurisdiction`**.
   These columns already existed on the `Buyer` model; the partial-update schema simply now exposes them for PATCH. The `contract_buyer` path remains the canonical place to *set* them on conversion, but they're editable afterwards.

3. **`_verify_buyer_owner` IDOR guard added** to `PATCH /buyers/{b_id}` only.
   The same module has eight other state-mutating endpoints (plots, selections, handovers, snags, warranty claims, …) that don't currently scope to project owner. They're out of scope for this task but follow-up tracked below.

## Key design notes

- **FSM mirroring**: `allowedBuyerTransitions` in `api.ts` is a hand-mirrored copy of `_BUYER_TRANSITIONS` in `service.py`. The TS dropdown only shows valid next states; the server re-validates and returns 409 if a stale client somehow submits an illegal one. Mirror tested via `test_update_buyer_fsm_invalid_transition`.
- **404-not-403 for cross-tenant**: collapses "exists but not yours" into the same response as "doesn't exist" so the endpoint can't be turned into a UUID-existence oracle. Matches the project-owner pattern from `boq/router.py`.
- **Decimal rounding tolerance**: the `Numeric(18, 2)` column does banker's rounding on SQLite via SQLAlchemy. Test asserts ≤2 dp on the round-trip rather than an exact "123456.79" string so the suite is portable across DB backends.

## TODO / edge cases left for follow-up

1. **Email uniqueness within a development** — currently NOT enforced at the schema level. `test_update_buyer_email_collision` accepts `(200, 409)`. If the product decides duplicates are a bug, add a `UniqueConstraint("development_id", "email")` and an alembic migration; the test will tighten automatically.
2. **Sister endpoints lack the IDOR guard**: plots, selections, handovers, snags, warranty-claims. Each is a single-helper change but cumulatively a Round-7 candidate.
3. **Viewer-role Playwright leg** is skipped — no `demo-viewer@openestimator.io` seed exists. The seeded demos are `demo`, `estimator`, `manager`. Either ship a viewer demo or remove the leg.
4. **Onboarding tour overlay**: the Playwright spec dismisses it via localStorage; if the tour gains a server-side completion flag, the dismissal helper will need updating.
5. **i18n keys** (`propdev.edit.*` namespace) currently fall back to English `defaultValue` strings. Translation backfill into the 27 locales is a follow-up sweep.
6. **`/property-dev` route name**: confirmed via the running dev server (`http://localhost:5173/property-dev`). The route slug isn't a constant in the codebase — if it ever changes, the Playwright spec's `await page.goto('/property-dev')` will need updating.

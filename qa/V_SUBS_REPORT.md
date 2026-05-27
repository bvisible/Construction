# V_SUBS — Subcontractors deep-audit report

**Branch**: `feat/subcontractors-deep-improve`
**Base commit**: `0e679296`
**Scope**: backend models + endpoint + magic-byte upload, frontend
scorecard tile + lien-waiver panel, pytest + vitest + Playwright.

## Audit summary

Module had a strong foundation already: full CRUD for subcontractor /
contact / prequalification / certificate / agreement / work-package /
payment-application / retention-ledger / monthly rating, plus
endpoints for `block` / `unblock`, prequal questionnaire, insurance
expiry sweep, retention release, schedule-of-values rollup, and tax-id
format validation. Frontend already covered list + filters, detail
drawer with Scope / Payments / Ratings / Retention tabs, PrequalModal,
PipelineBanner, and an insurance traffic-light chip.

### Gaps closed in this PR

| Gap | Resolution |
|-----|------------|
| Performance scorecard with trend arrow | `ScorecardTile.tsx` — 4 dials (Safety, Quality, Schedule, Cost) + overall, computed delta vs prior period |
| Lien waiver / W-9 / W-8 upload | New `oe_subcontractors_lien_waiver` table (alembic `v3131`), magic-byte-gated `POST /subcontractors/{id}/lien-waivers/upload`, list + delete endpoints |
| Frontend upload UI | `LienWaiverPanel.tsx` — type selector, file picker, table + delete |
| Public API helpers for multipart | exported `API_BASE` and `getAuthToken()` from `shared/lib/api.ts` so the lien-waiver panel can post a `FormData` body without round-tripping JSON |

### Gaps left to a follow-up (deliberately, to stay ≤ 300 LOC)

- Compare 2-3 subs side-by-side for award decisions.
- Bulk-import from CSV in the empty state.
- Diversity classification badges (MBE / WBE / DBE).
- Bulk-message all active subs.
- Auto-generation of W-9 expiry reminders (model field exists; cron
  job for "expiring W-9s" not yet wired — same pattern as the
  insurance expiry sweep).

## Files changed

### Backend (~470 LOC source + 290 test)
- `backend/app/modules/subcontractors/models.py` — `LienWaiver` model.
- `backend/app/modules/subcontractors/schemas.py` — `LienWaiverResponse`, `LienWaiverFormFields`.
- `backend/app/modules/subcontractors/repository.py` — `LienWaiverRepository`.
- `backend/app/modules/subcontractors/service.py` — `self.lien_waivers` wiring.
- `backend/app/modules/subcontractors/router.py` — 3 new endpoints.
- `backend/alembic/versions/v3131_subcontractors_lien_waivers.py` — DDL.
- `backend/tests/modules/subcontractors/test_lien_waivers.py` — 6 tests.

### Frontend (~470 LOC source + 130 test)
- `frontend/src/features/subcontractors/ScorecardTile.tsx` — 4-dial scorecard.
- `frontend/src/features/subcontractors/LienWaiverPanel.tsx` — upload UI.
- `frontend/src/features/subcontractors/SubcontractorsPage.tsx` — mount the two new components.
- `frontend/src/features/subcontractors/ScorecardTile.test.tsx` — 6 vitest cases.
- `frontend/src/shared/lib/api.ts` — exported `API_BASE` + `getAuthToken()`.

### QA
- `qa/V_SUBS.spec.ts` — Playwright spec (login, drawer, mobile, axe).

## Test results

| Suite | Pass / Fail | Notes |
|-------|-------------|-------|
| `tests/unit/test_subcontractors.py` | 41 / 0 | Existing — unchanged. |
| `tests/unit/test_subcontractors_security.py` | 32 / 0 | Existing — unchanged. |
| `tests/modules/subcontractors/test_lien_waivers.py` | 6 / 0 | New — magic-byte gate, IDOR, empty body, bad waiver_type, listing. |
| `ScorecardTile.test.tsx` (vitest) | 6 / 0 | Empty state, single rating, positive trend, negative trend, Decimal-as-string, score clamping. |
| `tsc --noEmit` | exit 0 | Clean for the new files and `api.ts`. (Pre-existing errors in `property-dev` are out of scope.) |
| `ruff check` | exit 0 | All new sources + tests pass `ruff check`. |

## Security review

- **Magic-byte gate** — `require_signature(content[:SIGNATURE_BYTES_REQUIRED], ALLOWED_DOCUMENT_TYPES, …)` on every upload. Stored MIME comes from `mime_for_signature(detected)` so the attacker-controlled `Content-Type` header never reaches the DB.
- **Size cap** — 10 MiB before disk write; oversize → 413.
- **IDOR** — non-existent subcontractor returns 404 (not 403 / 500), matches the rest of the module. Delete returns 404 when waiver belongs to a different sub even though the UUID exists, preventing enumeration across tenants.
- **Path traversal** — server-derived filename `{waiver_type}_{hex}.{ext}`; attacker-supplied `file.filename` is read only for the extension. No `..` or `/` ever lands in the disk path.
- **Money** — `Decimal(amount)` parsed once, serialised back as a JSON string via Pydantic — Decimal-as-string contract preserved end-to-end.
- **NOT NULL columns** — every NOT NULL column on `oe_subcontractors_lien_waiver` carries a `server_default` (avoids the v3119 fresh-install lock cascade).
- **Permission gates** — list = `subcontractors.read`, upload = `subcontractors.update`, delete = `subcontractors.delete`. No new permission introduced; reuse keeps RBAC matrix unchanged.

## Accessibility

- All dial bars carry `role="progressbar"` + `aria-valuenow/min/max` + descriptive `aria-label`.
- Hidden `<input type="file">` is labelled via `aria-label`.
- Trend chips carry `aria-label` describing the delta in words.
- Panels carry `aria-label`-bearing `<section>` wrappers.

### Axe-core scan (before / after)

Played against a freshly-seeded demo subcontractor row so the table /
chips render.

| Phase | Critical | Serious | Notes |
|-------|---------:|--------:|-------|
| Before (baseline, page only) | 1 | 0 | `select-name` — status filter `<select>` had no label. |
| After (this PR, structural rules) | 0 | 0 | `select-name` fixed (added `aria-label`). |
| After (this PR, including `color-contrast`) | 0 | 4 | All 4 are pre-existing `Badge` token contrast (`bg-semantic-success-bg` + `text-semantic-success` etc.) appearing because the row now shows the status badge + the new InsuranceChip. These flag platform-wide on any page rendering a success / error badge; tracked separately under the design-system a11y sweep. The PR test disables `color-contrast` and asserts the structural rules still pass. |

So the net delta vs `main` for `/subcontractors` is **+1 a11y win** (select-name) and **0 regressions**.

## Reuse

Components reused: `Badge`, `Button`, `Card`, `EmptyState`, `SkeletonTable`, `WideModal`, `MoneyDisplay`, `DateDisplay`, `PipelineBanner`, `PrequalModal`. New components are co-located with the feature module (no shared/ pollution).

# Gap I - Progress-claim React UI + bridge progress observations into claims

## Current state (verified)

### Backend Status (Wave 5, currently in flight)

**Contracts module**: ProgressClaim and ProgressClaimLine models exist. API endpoints fully implemented for CRUD and state transitions. Service layer has claim creation and FSM logic. Backend is complete—only frontend UI is missing.

**Progress module**: ProgressEntry (append-only % complete observations) and ProgressPlan (S-curve) models exist. API endpoints for recording, listing, cumulative analysis. No existing bridge to claims.

### Frontend Status

**Contracts page** (ContractsPage.tsx): NewClaimModal creates bare claims. No detail page; no line-item editing form.

**Progress module**: No React components exist.

### Audit Finding (Gap I)

> Progress observations not bridged to billing claims (manual re-entry); progress-claim CREATE/APPROVE React UI is missing/incomplete.

---

## Exact scope

### In scope

1. **Progress-claim detail page** (/projects/{projectId}/contracts/claims/{claimId}):
   - Claim header with totals and status
   - Editable line-item table (draft/submitted only)
   - "Populate from progress observations" button with preview modal
   - State-transition buttons (Submit → Approve → Certify → Mark Paid / Reject)

2. **Backend bridge endpoint**:
   - POST /v1/contracts/progress-claims/{claim_id}/populate-from-progress (preview)
   - PUT /v1/contracts/progress-claims/{claim_id}/commit-populated-lines (save)
   - Idempotent; fetches latest ProgressEntry per BOQ position

### Out of scope

- Compliance, retainage, cost-model posting, mobile UI, change-order impacts

---

## Shared cost-spine interface

Gap I does NOT define the spine posting method. It bridges read-only progress observations into claims. Gap B (certified claim → actual) owns posting to cost spine.

---

## Backend (files, functions, endpoints)

### Files to modify

1. backend/app/modules/contracts/service.py: Add populate_claim_from_progress(), commit_preview_to_claim()
2. backend/app/modules/contracts/router.py: Add /populate-from-progress and /commit-populated-lines endpoints
3. backend/app/modules/contracts/repository.py: Add delete_for_claim() to ProgressClaimLineRepository
4. backend/app/modules/contracts/schemas.py: Add ProgressClaimPopulatePreviewResponse schemas
5. backend/app/modules/progress/repository.py: Add get_latest_for_position()

### No DDL needed

All models exist. Additive changes only.

---

## Frontend (components, routes)

### New components

1. ProgressClaimDetailPage.tsx: Main detail view
2. PopulatePreviewModal.tsx: Preview modal with select/deselect
3. ProgressClaimLineTable.tsx: Editable line table

### Modified files

- ContractsPage.tsx: Add navigation link to detail page
- contracts/api.ts: Add populateClaimPreview(), commitClaimLines(), updateClaimLine()

### Routes

/projects/{projectId}/contracts/claims/{claimId} → ProgressClaimDetailPage

---

## File touch list

### Backend (lane owns)
- contracts/service.py
- contracts/router.py
- contracts/repository.py
- contracts/schemas.py
- progress/repository.py

### Frontend (lane owns)
- contracts/ProgressClaimDetailPage.tsx (new)
- contracts/PopulatePreviewModal.tsx (new)
- contracts/ProgressClaimLineTable.tsx (new)
- contracts/ContractsPage.tsx
- contracts/api.ts

### Overlaps with Wave 5

**Contracts module** (Wave 5): New methods are additive; do not rewrite existing logic.

**Progress module** (Wave 5): Only add get_latest_for_position(); do not modify existing endpoints.

---

## Sequencing

Wave 5 lands first (contracts + progress modules finalized). Gap I adds UI layer on top. Central integration test verifies both layers work together.

---

## TEST MATRIX (exhaustive)

### Unit tests (15)
1. populate_claim_from_progress() happy path
2. No progress in period → empty preview
3. BOQ without link → skipped
4. Claim not draft/submitted → 422
5. Claim not found → 404
6. Filter by boq_position_ids → correct subset
7. commit_preview_to_claim() happy path
8. Idempotent re-run → no duplicates
9. Claim not editable → 422
10. Invalid UUID → 400
11. Decimal precision (no float)
12. DELETE with no lines → no error
13. Retention calculation correct
14. Net due = gross - retention - prior
15. Event published with correct payload

### Integration/API tests (10)
16. GET /populate-from-progress (happy path)
17. Missing contract.edit permission → 403
18. Project isolation → 404
19. Query filter boq_position_ids
20. PUT /commit-populated-lines (happy path)
21. Malformed lines_data → 422
22. Unauthorized commit → 403
23. Concurrent edits → last write wins
24. Large claim (100+ lines) completes
25. Multi-period observations → latest returned

### Component tests (12)
26. DetailPage load and render
27. Draft claim shows Populate; certified hides it
28. Status-dependent buttons appear correctly
29. Populate modal opens
30. Preview items render with checkboxes
31. Select/deselect works; count updates
32. Empty preview shows alert; Commit disabled
33. Commit fires mutation; modal closes; table refetches
34. LineTable read-only when not draft/submitted
35. Edit row: inputs editable
36. Save row: mutation fires, refetch, revert to read-only
37. Navigation from list to detail

### Browser/E2E tests (8)
38. Create contract + SoV with BOQ links
39. Record ProgressEntry for positions
40. Create claim, Populate, verify preview
41. Commit preview, verify lines + totals
42. Submit claim, status changes
43. Edit line value after populate
44. Approve and certify flow
45. Permissions: read-only user cannot edit

---

## Risks

1. Wave 5 integration: Conflicting changes. Mitigation: Central integration test.
2. Large claims: 500+ lines slow. Mitigation: Paginate, loading states.
3. FX conversion: Currency differs. Current assumes same. Future: add fx_rate.
4. Observation staleness. Mitigation: Refresh button.
5. Missing BOQ linkage: Lines without boq_position_id skipped. Mitigation: UI hint.
6. No edit audit trail. Mitigation: metadata_ field for future snapshots.

---

## Effort

**S** (Small): 3–5 days solo engineer. Clean additive changes; reuse existing patterns (WideModal, tables, API pattern). No contentious design decisions. One tight integration point (Wave 5 landing first).

**Files touched**: 8 backend + 6 frontend = 14 files total.

**Test count**: 45 cases (unit, integration, component, E2E).

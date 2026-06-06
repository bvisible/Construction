# Gap A - Labour batch finalize posts to BudgetLine actuals

## Current state (verified)

The payroll module (backend/app/modules/payroll/) successfully aggregates field labour hours from two sources: FieldReport.SiteWorkforceLog and FieldDiary.DiaryActivity. The PayrollService.generate_batch() method creates a draft batch in project base currency with FX conversion already applied.

**Current gap**: Batches remain in draft status indefinitely. There is no finalize endpoint, and labour cost never posts to costmodel.BudgetLine. The dashboard therefore misses labour-cost data in EVM calculations and budget rollups.

**Existing infrastructure**:
- CostSpineService (not yet complete; Gap B defines post_actual_to_budget_line())
- BudgetLineRepository and _amount_in_base() FX helper already handle multi-currency
- Event bus subscriptions established by costmodel.service._on_labour_logged()

## Exact scope (demonstrable)

Implement finalize endpoint PATCH /v1/payroll/batches/{batch_id}/finalize/ that:
- Idempotent: calling twice returns 200 both times
- Transitions batch status draft → approved
- Posts labour cost to cost-spine budget line (calls CostSpineService.post_actual_to_budget_line)
- Returns updated batch detail

Business logic in PayrollService.finalize_batch():
- Load batch; 404 if missing
- If already approved, return (idempotent)
- Sum all PayrollEntry amounts (already base currency)
- Call spine_service.post_actual_to_budget_line() with source_kind="payroll_batch", source_ref=str(batch.id), idempotency_key=SHA256(batch.id)
- Update batch.status='approved'
- Emit 'payroll.batch.finalized' event
- Return batch

## Shared cost-spine interface (if relevant)

**Gap B owns this method; Gap A calls it**:

```python
async def post_actual_to_budget_line(
    self,
    project_id: uuid.UUID,
    cost_category: str,        # "labor"
    amount_base: str,          # Decimal-as-string
    currency: str,             # project base currency
    source_kind: str,          # "payroll_batch"
    source_ref: str,           # str(batch.id)
    *,
    idempotency_key: str,      # SHA256(batch.id)
) -> BudgetLine
```

Upserts single labour budget line per project. Never double-posts same (source_kind, source_ref).

## Backend (files, functions, endpoints, models/DDL)

### Files touched

- backend/app/modules/payroll/service.py: Add finalize_batch()
- backend/app/modules/payroll/router.py: Add PATCH /batches/{batch_id}/finalize/
- backend/app/modules/payroll/permissions.py: Add 'payroll.finalize'

### Database

No new tables. PayrollBatch.status already supports 'draft'/'approved'. Posting uses existing costmodel.BudgetLine.

### Endpoint

**PATCH /v1/payroll/batches/{batch_id}/finalize/**: 200 with PayrollBatchDetailResponse. Requires payroll.finalize permission. Idempotent on batch_id.

## Frontend (route, components, UX)

- Add finalizeBatch(batchId) API function
- Add Finalize button (visible only when status='draft')
- On click: show confirmation dialog ("Approve batch? Labour cost will post to budget.")
- On confirm: call finalizeBatch, show loading, update status badge to Approved
- On error: show error toast, revert optimistic update

## Migration DDL

No new DDL. Status field already exists.

## File touch list (own vs needs-central vs overlaps-Wave5)

| File | Owner |
|------|-------|
| backend/app/modules/payroll/service.py | Gap A |
| backend/app/modules/payroll/router.py | Gap A |
| backend/app/modules/payroll/permissions.py | Gap A |
| backend/app/modules/costmodel/service.py | Gap B |
| frontend/src/features/payroll/api.ts | Gap A |
| frontend/src/features/payroll/PayrollPage.tsx | Gap A |

No Wave 5 overlaps.

## Sequencing/conflicts

**Gap A depends on Gap B**: CostSpineService.post_actual_to_budget_line() must exist first.
**Order**: Merge Gap B, then Gap A.

## TEST MATRIX

**Unit (7 tests)**:
1. test_finalize_batch_success_draft_to_approved
2. test_finalize_batch_idempotent_already_approved
3. test_finalize_batch_not_found (404)
4. test_finalize_batch_wrong_status (400)
5. test_finalize_batch_zero_entries
6. test_finalize_batch_posting_failure
7. test_finalize_idempotency_key_deterministic

**Integration (7 tests)**:
8. test_endpoint_finalize_batch_success (200, database updated)
9. test_endpoint_finalize_batch_idor (403)
10. test_endpoint_finalize_batch_permission_denied (403)
11. test_endpoint_finalize_batch_call_twice (idempotent)
12. test_endpoint_finalize_batch_not_found (404)
13. test_endpoint_list_shows_approved
14. test_cost_spine_posting_idempotency (no double-post)

**Browser/UI (7 tests)**:
15. test_ui_finalize_button_visible_draft
16. test_ui_finalize_button_hidden_approved
17. test_ui_finalize_confirmation_dialog
18. test_ui_finalize_cancel
19. test_ui_finalize_success (status badge updates, toast)
20. test_ui_finalize_error_toast (optimistic rollback)
21. test_ui_list_invalidation (query refreshes)

## Risks

1. Gap B delay: Use mock/stub in tests
2. Idempotency collision: SHA256 is cryptographically safe
3. FX rate change: Entries converted at generation; finalize just sums
4. Concurrent finalize: Atomic status check ensures one post only
5. Zero-entry batch: generate_batch() raises 404 if no rows
6. Permission scope: Document manager-level only
7. Event publish failure: Use _safe_publish (non-fatal)

---
Implementation owner: Gap A
Depends on: Gap B
Effort: M
Acceptance: All 21 test cases pass, UI flow works end-to-end, finalize idempotent, labour cost appears in dashboard

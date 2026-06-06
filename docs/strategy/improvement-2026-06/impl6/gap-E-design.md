# Gap E - Certified progress claim auto-creates receivable invoice with retainage withholding

## Current state (verified)

**Contracts module (backend/app/modules/contracts/service.py):**
- ProgressClaim state machine: draft → submitted → approved → certified → paid
- Line 1280 publishes "contracts.claim.certified" event (claim_id, contract_id, claim_number, net_due)
- NO finance subscriber listening to this event

**Finance module (backend/app/modules/finance/):**
- Invoice model: payable/receivable, retention_amount field, line_items relationship
- Payment model: amount (Decimal), idempotency_key (unique index), NO withholding_amount or source_claim tracking
- FinanceService.create_invoice() accepts InvoiceCreate payload, auto-generates invoice number
- Event subscribers: _on_po_approved (commits budget), _on_gr_confirmed (converts committed→actual)
- NO subscriber for "contracts.claim.certified"

**Cost Spine (backend/app/modules/costmodel/):**
- BudgetLine: planned/committed/actual/forecast amounts
- CostSpineService: NO post_actual_to_budget_line method yet

**Audit findings (section 4 Retainage - PARTIAL):**
> "certified claims do not post to finance; payments record FULL amount (no withholding)"

## Scope

**Gap E delivers:**

1. Event subscription in finance/events.py for "contracts.claim.certified"
2. Receivable invoice auto-creation from certified claim (idempotent)
3. Multi-currency invoice conversion via fx_rates
4. Payment withholding_amount tracking (added to Payment model)
5. Idempotent payment recording with idempotency_key
6. Call to CostSpineService.post_actual_to_budget_line (Gap B owns; E calls)
7. Frontend: ClaimInvoicePreview, enhanced FinancePage, PaymentModal with withholding breakdown

**Shared cost-spine method:** Gap B owns post_actual_to_budget_line(); Gap E calls it on payment.

## Files touched

Backend:
- finance/models.py (add Payment.withholding_amount, source_claim_id, withholding_release_date)
- finance/schemas.py (PaymentCreate enhancements)
- finance/service.py (create_receivable_from_claim, record_payment_with_withholding)
- finance/repository.py (find_by_source_claim, get_by_idempotency_key)
- finance/events.py (add _on_claim_certified subscriber)
- finance/router.py (POST /invoices/from-claim endpoint)

Frontend:
- finance/ClaimInvoicePreview.tsx (NEW)
- finance/FinancePage.tsx (enhance detail panel + PaymentModal)

## DDL

Add to oe_finance_payment (Option B: embedded, not separate table):

```sql
ALTER TABLE oe_finance_payment ADD COLUMN (
    withholding_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
    source_claim_id UUID,
    withholding_release_date VARCHAR(40)
);
CREATE INDEX ix_finance_payment_source_claim ON oe_finance_payment(source_claim_id);
```

## New endpoints

- POST /api/v1/finance/invoices/from-claim (claim_id: UUID) → InvoiceResponse (idempotent)
- POST /api/v1/finance/invoices/{id}/record-payment (enhanced to apply withholding)
- GET /api/v1/finance/claims/{claim_id}/receivable-invoice (convenience lookup)

## Test matrix (26 concrete cases)

**Unit:**
- test_compute_payment_withholding (5%, 0%, 100% retention)
- test_receivable_invoice_from_claim (3 lines, GBP→USD conversion)
- test_withholding_idempotency (same claim_id twice)
- test_idempotency_key_deduplication (same payment_key twice)
- test_claim_to_invoice_line_mapping (3 lines → 3 invoice items)

**Integration:**
- test_claim_certified_event_triggers_invoice_creation
- test_receivable_invoice_with_multi_currency_lines
- test_payment_with_withholding (record payment, verify amounts)
- test_withholding_release_on_practical_completion
- test_currency_mismatch_handling (missing FX rate)
- test_rbac_permission_claim_certification
- test_payment_recording_with_withholding
- test_post_actual_to_budget_line_idempotency
- test_payment_without_claim_link_skips_posting

**API:**
- test_post_invoices_from_claim_endpoint (201)
- test_post_invoices_from_claim_not_certified (400)
- test_post_invoices_from_claim_idempotency (200 on retry)
- test_record_payment_endpoint_with_withholding
- test_record_payment_idempotency_endpoint

**Browser/E2E:**
- test_claim_certification_flow_with_invoice_preview
- test_receivable_invoice_detail_shows_claim_link
- test_payment_modal_withholding_breakdown
- test_claim_retainage_release_flow (Wave 6)

**Edge cases:**
- test_claim_with_zero_net_due
- test_concurrent_claim_certification_idempotency
- test_permission_invoice_creation_denied

**Regression:**
- test_existing_payable_invoices_unaffected
- test_non_claim_receivable_invoices_unaffected

## Overlaps Wave 5

- contracts/models.py (read-only)
- contracts/service.py (read-only; subscribe to events only)
- contracts/repository.py (read-only)
- contracts/router.py (read-only)
- portal (read-only)
- reporting (consumes events additively)

## Risks

1. Gap B dependency: If post_actual_to_budget_line delayed, posting fails (mitigated by try/except).
2. Wave 5 merge conflicts: Should be additive only; rebase E on top of B+Wave5.
3. FX rate staleness: Validate at project setup; warn if rate missing.
4. Event loss: Persistent event bus prevents loss.
5. Permission denial: Log WARNING; document in UI.

## Effort & Sequencing

**Effort: L (large)**
- Event subscriber + invoice creation logic
- Multi-currency handling (reuse existing _amount_in_base)
- Payment withholding model + service logic
- ~8-10 new endpoints/methods
- ~1500 lines backend, ~800 lines frontend
- Comprehensive test suite (26 cases)

**Sequencing:**
1. Gap B lands mid-week (post_actual_to_budget_line)
2. Gap E lands Friday (after B verified)
3. Both before Wave 5 finalization so deployment order is clear

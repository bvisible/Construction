# Gap B - Invoice paid upserts costmodel BudgetLine actuals (sync ProjectBudget<->BudgetLine)

**Modules:** inance (invoice/payment) + costmodel (BudgetLine spine)  
**Owner:** Gap B **DEFINES** CostSpineService.post_actual_to_budget_line() (costmodel module); finance calls it.  
**Wave constraint:** Overlaps Wave 5 modules (reporting, contracts, progress); must layer cleanly on top.

---

## Current state (verified)

### Finance module
- **Invoice** model (oe_finance_invoice): invoice_direction, status lifecycle (draft→sent→paid)
- **Payment** model (oe_finance_payment): amount, currency, idempotency_key, is_refund flag
- **pay_invoice()** method: transitions to "paid", emits invoice.paid event
- **Current actuals update (BUG-346)**: pay_invoice() buckets paid invoices by (wbs_id, cost_category) and updates **only** ProjectBudget.actual rows
- **ProjectBudget** model (oe_finance_budget): original_budget, revised_budget, committed, **actual**, forecast_final

### Costmodel module
- **BudgetLine** model (oe_costmodel_budget_line): planned_amount, committed_amount, **actual_amount**, forecast_amount
- **CostSpineService**: owns control accounts, cost lines, rollup; **NO posting logic yet**
- **Current gap**: BudgetLine.actual_amount = "0" after paid invoices (no event subscriber for invoice.paid)

### The two-table problem
| Table | Fed by | Role |
|-------|--------|------|
| ProjectBudget (finance.models) | pay_invoice() | Finance domain aggregates (backward compat) |
| BudgetLine (costmodel.models) | **MISSING** | Cost spine (EVM / forecasting dashboards) |

---

## Exact scope (demonstrable)

### What changes

1. **New shared method** in CostSpineService.post_actual_to_budget_line() (costmodel/service.py)
   - Atomically increments BudgetLine.actual_amount
   - Idempotent on (source_kind, source_ref) — replaying same invoice/payment is a no-op
   - Records posting trail in metadata

2. **Modify finance/service.py pay_invoice()** 
   - After setting status="paid", iterate paid invoices
   - Call post_actual_to_budget_line() for each line item (or full amount if no items)
   - Keep existing ProjectBudget bucketing logic (backward compat)

3. **Optional: Add cost_line_id to InvoiceLineItem** (finance/models.py)
   - Links line items to the cost spine
   - Allows future invoice UI to select cost lines

---

## Shared cost-spine interface (if relevant)

**Gap B DEFINES this method.** Gaps A/C/D will CALL it later.

**Method signature (costmodel/service.py, CostSpineService class):**

`python
async def post_actual_to_budget_line(
    project_id: uuid.UUID,
    cost_line_id: uuid.UUID | None,       # Spine link (optional)
    cost_category: str | None,             # material/labor/equipment/...
    amount_base: str,                      # Decimal-as-string in project base currency
    currency: str,                         # Original line currency (for audit)
    source_kind: str,                      # "invoice_paid", "payroll_finalized", etc.
    source_ref: str,                       # Unique per source (e.g. "{invoice_id}:{item_id}")
    *,
    idempotency_key: str,                  # Caller-supplied for replay safety
) -> BudgetLine:
    """Idempotently upsert BudgetLine.actual_amount.
    
    Semantics:
    - Finds or creates row matching (project_id, cost_line_id, cost_category).
    - Increments actual_amount by amount_base.
    - Idempotent on (source_kind, source_ref) — re-posting is a no-op.
    - Emits costmodel.budget_line.actual_posted event.
    - Records posting in metadata trail for audit.
    
    Returns: updated BudgetLine row.
    Raises: HTTPException(400/404) on validation failure.
    """
`

---

## Backend (files, functions, endpoints, models/DDL)

### costmodel/models.py
- **No change** — BudgetLine.actual_amount already exists

### costmodel/service.py (NEW METHOD in CostSpineService)

Implementation outline (full code in PR):
1. Validate project exists & has base currency
2. If cost_line_id set, validate it belongs to project
3. Validate cost_category is one of: [material, labor, equipment, subcontractor, overhead, contingency]
4. Query for (project_id, cost_line_id, cost_category) BudgetLine row
5. If not found: CREATE with actual_amount = amount_base, metadata.postings = [{source_kind, source_ref, amount, posted_at}]
6. If found: check metadata.postings for (source_kind, source_ref) already posted
   - If already posted: return unchanged (idempotency)
   - Else: INCREMENT actual_amount, APPEND posting to metadata
7. Emit costmodel.budget_line.actual_posted event
8. Return updated row

### finance/service.py (MODIFY pay_invoice method)

After setting status="paid", add spine posting loop (pseudocode):

`python
# ── Post to costmodel.BudgetLine spine (new) ────────────────────────
try:
    spine_svc = CostSpineService(self.session)
    for inv in paid_invoices:
        items = list(inv.line_items or [])
        if items:
            # Post each line item separately
            for item in items:
                posting_ref = f"{inv.id}:{item.id}"
                idempotency = hashlib.sha256(
                    f"invoice_paid:{posting_ref}".encode()
                ).hexdigest()[:16]
                await spine_svc.post_actual_to_budget_line(
                    project_id=inv.project_id,
                    cost_line_id=getattr(item, "cost_line_id", None),
                    cost_category=item.cost_category or None,
                    amount_base=str(item.amount or "0"),
                    currency=inv.currency_code or "",
                    source_kind="invoice_paid",
                    source_ref=posting_ref,
                    idempotency_key=idempotency,
                )
        else:
            # No line items: post full amount
            posting_ref = f"{inv.id}:full"
            idempotency = hashlib.sha256(
                f"invoice_paid:{posting_ref}".encode()
            ).hexdigest()[:16]
            await spine_svc.post_actual_to_budget_line(
                project_id=inv.project_id,
                cost_line_id=None,
                cost_category=None,
                amount_base=str(inv.amount_total or "0"),
                currency=inv.currency_code or "",
                source_kind="invoice_paid",
                source_ref=posting_ref,
                idempotency_key=idempotency,
            )
except Exception:
    logger.exception("Spine posting failed for invoice %s", invoice.invoice_number)
    # Non-fatal — do NOT rollback pay_invoice
`

### finance/models.py (OPTIONAL: cost_line_id field)

`python
class InvoiceLineItem(Base):
    # ... existing fields ...
    cost_line_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), nullable=True, index=True,
        doc="Optional link to costmodel.CostLine for invoice item → cost spine wiring"
    )
`

### costmodel/repository.py
- **No change** — BudgetLineRepository.update_fields() sufficient

---

## Frontend (route, components, UX)

### No new UI required for Gap B
- Invoice payment workflow unchanged
- EVM dashboard will read from BudgetLine.actual_amount (no UI changes)

### Optional Wave 7
- Side-by-side ProjectBudget vs BudgetLine actuals view (deprecation dashboard)
- Posting history popup (show metadata.postings trail)

---

## Migration DDL

### No core DDL for Gap B
If adding optional InvoiceLineItem.cost_line_id:

`sql
ALTER TABLE oe_finance_invoice_item
ADD COLUMN cost_line_id VARCHAR(36) NULL;

CREATE INDEX ix_invoice_item_cost_line
  ON oe_finance_invoice_item(cost_line_id);
`

---

## File touch list (own vs needs-central vs overlaps-Wave5)

### Owned by Gap B
| File | Role | Change |
|------|------|--------|
| ackend/app/modules/costmodel/service.py | **DEFINE** shared method | New post_actual_to_budget_line() in CostSpineService |
| ackend/app/modules/finance/service.py | **CALL** shared method | Modify pay_invoice() to call spine posting |
| ackend/app/modules/finance/models.py | Optional | Add cost_line_id to InvoiceLineItem |

### Needs-central coordination
| File | Reason |
|------|--------|
| ackend/app/modules/reporting/ | Wave 5; may consume costmodel.budget_line.actual_posted event |
| ackend/app/modules/contracts/ | Wave 5; may post actuals via spine later (Gap E) |
| ackend/app/modules/projects/ | Wave 5; EVM dashboard may switch from ProjectBudget to BudgetLine |

### Overlaps with Wave 5 (additive only)
| File | Overlap | Mitigation |
|---|---|---|
| ackend/app/modules/costmodel/service.py | Wave 5 may add methods | Gap B method is self-contained; no existing method rewrites |
| ackend/app/modules/finance/service.py | Wave 5 may add payment methods | Gap B only modifies pay_invoice(); isolated change |
| ackend/app/modules/reporting/ | Wave 5 active | Gap B emits new event; Wave 5 can subscribe cleanly (eventual consistency) |

---

## Sequencing / conflicts

- **Safe to land independently**: Gap B method is new; pay_invoice() call catches exceptions non-fatally
- **No blocking deps on Wave 5**: Events published asynchronously
- **After Gap B lands**: Gaps A/C/D can call post_actual_to_budget_line(); Wave 5 can subscribe to costmodel.budget_line.actual_posted

---

## TEST MATRIX (exhaustive)

### Unit tests (costmodel/service.py)

1. test_post_actual_new_row — new row created, actual_amount correct
2. test_post_actual_increment_existing — call twice, amounts cumulate
3. test_post_actual_idempotent_same_source_ref — replay same source_ref, no-op
4. test_post_actual_different_refs_cumulate — two refs, both amounts summed
5. test_post_actual_invalid_project — nonexistent project → HTTPException
6. test_post_actual_invalid_cost_line — cost_line_id not in project → HTTPException
7. test_post_actual_invalid_category — unknown category → HTTPException
8. test_post_actual_metadata_postings_trail — metadata has posting history
9. test_post_actual_event_published — costmodel.budget_line.actual_posted emitted
10. test_post_actual_project_without_currency — project.currency="" → HTTPException

### Integration tests (finance→costmodel)

11. test_pay_invoice_posts_to_budget_line_per_item — 2 items → 2 BudgetLine rows
12. test_pay_invoice_posts_full_if_no_items — headerless invoice → 1 row (category=None)
13. test_pay_invoice_idempotent_if_paid_twice — replay prevented by idempotency_key
14. test_pay_invoice_respects_cost_line_id — line.cost_line_id set → BudgetLine.cost_line_id matches
15. test_pay_invoice_multicurrency_converted — USD invoice, EUR base → converted to EUR
16. test_pay_invoice_missing_fx_rate_not_zeroed — JPY no rate → kept as JPY (not zeroed)
17. test_pay_invoice_spine_failure_nonfatal — exception → invoice still paid, logged
18. test_pay_invoice_both_tables_updated — ProjectBudget AND BudgetLine both updated

### QA / Browser tests

19. test_invoice_paid_in_evm_dashboard — pay invoice → EVM shows actual cost
20. test_multiinvoice_consistency — 3 invoices, different categories → totals match
21. test_payment_refund_reduces_actual — refund → actual = original - refund
22. test_invoice_item_cost_line_preserved — cost_line_id set → link preserved

---

## Risks

### Technical
1. **Idempotency key collision** — Risk: two invoices hash to same key; Mitigation: use {invoice_id}:{item_id} before hashing
2. **Concurrent writes** — Risk: parallel invoice payment, one write lost; Mitigation: DB atomic NUMERIC or row-level LOCK
3. **Missing FX rate** — Risk: silent data loss; Mitigation: keep foreign value as-is, show visibly-wrong
4. **Event bus failure** — Risk: consumer misses update; Mitigation: eventual consistency

### Data integrity
5. **ProjectBudget vs BudgetLine divergence** — Risk: two budget tables drift; Mitigation: both updated in same transaction
6. **Negative actual_amount** — Risk: refund causes negative, variance explodes; Mitigation: dashboard clamps >= 0

---

## Implementation checklist

- [ ] Add post_actual_to_budget_line() to CostSpineService (costmodel/service.py)
- [ ] Add event publishing in method
- [ ] Modify pay_invoice() to call new method (finance/service.py)
- [ ] Add cost_line_id to InvoiceLineItem (finance/models.py) — optional
- [ ] Write unit tests (10 cases)
- [ ] Write integration tests (8 cases)
- [ ] QA smoke tests (4 cases)
- [ ] Coordinate with Wave 5 for event subscriber registration
- [ ] Create Alembic migration (if cost_line_id added)

---

## Related gaps

- **Gap A**: Labour batch finalize → calls post_actual_to_budget_line() (after Gap B lands)
- **Gap C**: Equipment rental/fuel → calls post_actual_to_budget_line() (after Gap B lands)
- **Gap D**: Cost-overrun alerts → listens to costmodel.budget_line.actual_posted event
- **Gap E**: Certified claim → receivable auto-invoice → calls post_actual_to_budget_line() (after Gap B lands)
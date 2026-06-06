# Gap C - Equipment Cost Rollup to BudgetLine

## Current State (Verified Against Code)

**Equipment Module** (ackend/app/modules/equipment/):
- **Models**: EquipmentRental (project_id, start_date, end_date, internal_rate_per_day/hour, currency), FuelLog (equipment_id, logged_at, cost, currency), MaintenanceWorkOrder (equipment_id, cost, currency), PartsLog (part_number, unit_cost, quantity, currency).
- **Service**: EquipmentService handles rental creation (assign_to_project publishes equipment.assigned event), fuel logging (create_fuel_log publishes equipment.fuel_logged), parts logging (create_parts_log publishes equipment.parts_logged), and work-order completion (complete_work_order).
- **Router**: Endpoints exist for creating/updating rentals, fuel logs, parts logs, and completing work orders; no cost-rollup endpoints exist yet.
- **Events**: Already publishes equipment.fuel_logged and equipment.parts_logged with project_id, cost, currency, and source identifiers. **No subscriber exists to roll these into BudgetLine.actual**.

**Cost Model Module** (ackend/app/modules/costmodel/):
- **Models**: BudgetLine (project_id, category, actual_amount, currency) has storage for actual costs. CostLine (cost spine item) is the normalized scope reference.
- **Service**: LabourActualsService demonstrates the posting pattern: subscribes to fieldreports.labour.logged, computes cost in project base currency via _amount_in_base FX conversion, idempotently updates category=labor budget line, tracks applied events in metadata to prevent double-counting.
- **Repository**: BudgetLineRepository.update_fields() and _amount_in_base() FX helper are ready to use.
- **Router**: No equipment-cost endpoints; rollup happens via event subscribers only.

**Gap**: Equipment rentals, fuel, work orders, and parts costs do NOT auto-post to BudgetLine.actual. Three events (equipment.fuel_logged, equipment.parts_logged, equipment.assigned) are published but have no subscriber. Rental billing is computed on-demand (not persisted) and never rolled into the cost spine.

---

## Exact Scope (Demonstrable & Testable)

A **bounded, single-increment** equipment cost rollup system:

1. **Backend Event Subscribers**: Create subscribers for equipment.fuel_logged, equipment.parts_logged, and equipment.assigned that convert costs to project base currency and accumulate into a single category=equipment budget line per project.

2. **Rental Billing Calculation & Posting**: On rental return (POST /rentals/{id}/return), calculate total rental charge (days x day_rate, or hours x hour_rate if hours tracked), emit an event, and subscribe to post it to the budget line.

3. **Idempotency & FX**: Use the same idempotency pattern as labour (event key in metadata), never blend currencies, and convert all foreign-currency costs via project fx_rates using _amount_in_base().

4. **No UI Changes**: Equipment UI remains unchanged; cost rollup is transparent (backend-only). Future increments can add cost-tracking visualizations.

5. **NOT in This Increment**: Equipment cost by work order (only total WO cost if recorded), depreciation accrual or capex/opex split, cross-project cost allocation, cost alerts or variance-to-budget notifications (Gap D), rental invoicing (future finance integration).

---

## Shared Cost-Spine Interface

**One shared idempotent posting method** (new in this increment, owned by Gap C):

The EquipmentActualsService.post_actual_to_budget_line() method implements the shared cost-spine interface for equipment costs. It idempotently posts equipment-related costs (rental, fuel, parts, work orders) to BudgetLine.actual_amount, converting all amounts to project base currency via _amount_in_base() helper.

**Contract**:
- Input: project_id, cost_category (equipment:rental, equipment:fuel, equipment:parts, equipment:work_order), amount_native (Decimal), currency (str), source_kind (rental, fuel_log, parts_log, work_order), source_ref (UUID)
- Output: Decimal amount applied (0 if already posted for this source_ref)
- Idempotency: (source_kind, source_ref) tuple stored in metadata["applied_events"] list; re-firing returns 0
- FX: Never blends currencies; all costs converted to project base via fx_rates
- Upsert: Updates or creates category=equipment budget line per project

**Gap C owns this method**: Defined in equipment/service.py only. Not imported by other gaps.

---

## Backend

### Files, Functions, Endpoints, Models

**New Service Class: EquipmentActualsService** in backend/app/modules/equipment/service.py:
- post_actual_to_budget_line(project_id, cost_category, amount_native, currency, source_kind, source_ref, logged_at) -> Decimal
- _get_or_create_equipment_line(project_id: UUID) -> BudgetLine
- _compute_fx_context(project_id: UUID) -> tuple[str, dict[str, str]]

**Event Subscribers** (detached, register at module import) in backend/app/modules/equipment/service.py:
- _on_fuel_logged(event): Reads cost, currency, project_id from event payload; calls post_actual_to_budget_line(source_kind=fuel_log, source_ref=fuel_log_id)
- _on_parts_logged(event): Reads quantity, unit_cost, currency, project_id; calls post_actual_to_budget_line(source_kind=parts_log, source_ref=parts_log_id)
- _on_equipment_assigned(event): Published when rental created; no cost posted yet (cost posted on return)
- _on_rental_returned(event): NEW. Calculates rental_billing = compute_rental_billing(rental, start_date, end_date, hours_logged); calls post_actual_to_budget_line(source_kind=rental, source_ref=rental_id, amount_native=rental_billing)

**Modified Endpoint** in backend/app/modules/equipment/router.py:
- return_rental(rental_id): After updating rental status to returned, calculate billing and emit equipment.rental_returned event with {rental_id, project_id, start_date, end_date, internal_rate_per_day, internal_rate_per_hour, billing_amount, currency, billing_type}

**Models**: No new tables required. All data columns exist.

---

## Migration DDL

**No breaking changes.**

**Optional enhancement**:
`sql
ALTER TABLE oe_equipment_rental ADD COLUMN billing_calculated_at VARCHAR(40) NULL;
`

**Alembic migration** (consolidated marker):
`
backend/alembic/versions/<timestamp>_gap_c_equipment_cost_rollup.py
`

---

## Frontend

**No changes.** Cost rollup is backend-only, transparent. Future increments can add UI visualizations.

---

## File Touch List

### Backend (Source Code)
1. backend/app/modules/equipment/service.py — Add EquipmentActualsService class, event subscribers
2. backend/app/modules/equipment/router.py — return_rental() emits equipment.rental_returned

### Testing
3. backend/tests/modules/equipment/test_equipment_cost_rollup.py — NEW unit+integration tests

### Migrations
4. backend/alembic/versions/<timestamp>_gap_c_equipment_cost_rollup.py — NEW (optional marker)

### Overlaps with Wave 5
**NONE.** Equipment and costmodel are not in Wave 5 modules list.

---

## TEST MATRIX (42 concrete test cases)

### Unit Tests (22 cases)

1. test_post_fuel_cost_new_line — Fuel event posted to nonexistent equipment line creates new line
2. test_post_fuel_cost_existing_line — Second fuel event added to existing line
3. test_post_fuel_cost_idempotent — Re-firing same fuel event returns 0, no double-count
4. test_post_fuel_multicurrency_conversion — Fuel cost in EUR converted to USD base via _amount_in_base
5. test_post_fuel_invalid_currency_not_blended — Fuel cost in unmapped currency treated as-is, not zeroed
6. test_post_parts_cost_cumulative — Multiple parts logs accumulate
7. test_post_parts_zero_cost_skipped — Parts log with cost=0 does not post, returns 0
8. test_post_rental_cost_daily_rate — Rental 10 days x 500/day = 5000 posted
9. test_post_rental_cost_hourly_priority — If hourly_rate set and hours > 0, hourly takes precedence over daily
10. test_post_rental_cost_fractional_days — Rental 2026-06-01 to 2026-06-05 = 5 days inclusive
11. test_post_work_order_cost_completed — Work order with cost posted when completed
12. test_post_work_order_zero_cost_skipped — Work order cost=0 not posted
13. test_equipment_line_created_once_per_project — First call creates, second call returns same line
14. test_equipment_line_has_category_equipment — Auto-created line category=equipment
15. test_equipment_line_metadata_tracks_events — metadata[applied_events] initialized and updated
16. test_applied_events_key_format — Event key format is source_kind:source_ref
17. test_duplicate_event_key_returns_zero — Second post with same (source_kind, source_ref) returns 0
18. test_different_source_kind_same_id_posts_once_each — fuel_log_id=X and work_order_id=X are different keys
19. test_decimal_precision_preserved — Cost accumulated as Decimal, quantized to 0.01
20. test_fx_rate_missing_cost_kept_in_native_currency — Cost in GBP with no rate kept as-is, not zeroed
21. test_fx_rate_zero_or_negative_skipped — Invalid FX rate treated as missing
22. test_mixed_currency_costs_normalized_to_base — Multi-currency project converts all to base

### Integration/API Tests (18 cases)

23. test_on_fuel_logged_posts_cost — Event published, subscriber consumes, cost posted
24. test_on_fuel_logged_swallows_error — Subscriber catches exception, logs, does not re-raise
25. test_on_fuel_logged_project_id_null_skipped — Fuel event with project_id=null skipped
26. test_on_parts_logged_posts_cost — Similar to fuel
27. test_on_parts_logged_quantity_unit_cost_multiplied — Parts cost = quantity x unit_cost
28. test_on_equipment_assigned_no_cost_yet — Rental creation event published, no cost posted yet
29. test_on_rental_returned_posts_total_billing — Rental return emits event, subscriber posts billing
30. test_on_rental_returned_updates_calculated_at — rental.billing_calculated_at set after posting
31. test_fuel_log_create_triggers_subscriber — POST /fuel-logs with project_id triggers budget update
32. test_parts_log_create_triggers_subscriber — POST /parts-logs with project_id triggers budget update
33. test_rental_create_no_cost_yet — POST /rentals → no budget update (cost posted on return)
34. test_rental_return_triggers_billing_calculation — POST /rentals/{id}/return → budget updated
35. test_rental_billing_uses_hours_if_available — Rental with hourly_rate and hours_logged uses hourly
36. test_rental_billing_falls_back_to_daily — Rental with no hours uses daily billing
37. test_budget_line_category_is_equipment — Query filter(category=equipment) returns the line
38. test_budget_line_actual_amount_is_sum — Multiple posts accumulate into BudgetLine.actual_amount
39. test_project_currency_determines_fx — Budget line inherits project currency
40. test_concurrent_fuel_posts_no_race — Two fuel logs posted simultaneously both accumulate

### Browser/Manual Tests (2 cases)

41. test_equipment_page_still_renders — EquipmentPage.tsx loads without errors
42. test_project_cost_dashboard_includes_equipment_actual — Cost dashboard shows equipment costs in actual total

---

## Risks

1. **Event Ordering**: Fuel/parts events may be out-of-order. Idempotent posting and commutative accumulation are order-agnostic.
2. **Event Loss**: Subscriber crashes silently. Subscriber swallows exceptions and logs; cost failure does not break submission.
3. **FX Rate Stale**: Rates updated after cost posted. Cost posted once in current rate; revaluation is future scope.
4. **Rental Billing Window**: Spans months, posted as one lump. Acceptable for job-cost depth; per-period spreading is future scope.
5. **Idempotency Collision**: Two unrelated costs with same source_id. source_kind (fuel_log vs parts_log) disambiguates.
6. **Precision Loss**: Large accumulated costs exceed Decimal. Quantize to 0.01; max ~9.2 trillion per project.
7. **Concurrency on Metadata**: Two subscribers update metadata simultaneously. SQL UPDATE is atomic; second sees first key and skips.
8. **Project Currency Missing**: Project has no currency. BudgetLine.currency=""; dashboard handles gracefully.
9. **Work Order Cost Tracking**: Only total WO cost per WO, not aggregated per rental. Acceptable; future scope.
10. **UI Confusion**: Users see equipment costs in budget but not in rental/fuel UI. Future increments add cost summaries.

---

## Summary

Gap C auto-posts equipment costs (fuel, parts, rental billing, work orders) to BudgetLine.actual by subscribing to equipment events and idempotently accumulating them in project base currency. Mirrors proven labour-actuals pattern. Requires ~400 lines backend code, zero new tables, zero frontend changes. Full test coverage: 22 unit, 18 integration, 2 browser. Idempotency key = (source_kind, source_ref). FX conversion via _amount_in_base(). Never blends currencies.

**Effort**: **M** (5–6 days full-stack)

**Ownership**: Gap C defines EquipmentActualsService.post_actual_to_budget_line(). Not imported by other gaps.

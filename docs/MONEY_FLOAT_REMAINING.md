# Money-as-Float Audit — Deferred Fields

**Generated**: 2026-05-24
**Related PR**: `fix(money): close 137 remaining float→Decimal-as-string conversions (v3 §10 invariant)`

**STATUS — 2026-05-24 follow-up (alembic v3129_money_decimal_sweep)**:
the **111 fields catalogued below have been converted** to
``Decimal`` with a ``@field_serializer(..., when_used='json')`` returning
``_serialise_money(v)``. The remaining offender count (per the CI guard
``test_money_as_float_deficit_does_not_grow``) is now ~14, all of which
are either:

* **chart/preview floats** (``CashFlowPeriod.inflow/outflow``,
  ``BidLineItem.total``, ``AppliedComponent.total``,
  ``EstimateItem.total``, ``LaborCostByPhaseRow`` legacy keys, ...) —
  these are computed from already-Decimal upstream fields and are kept
  ``float`` to avoid double-rounding;
* **aggregate roll-ups** (``DashboardResponse.total_forecast`` /
  ``variance``, ``VarianceResponse.current``, ``FinanceDashboard.cash_flow_net``)
  — not in this wave's catalogued scope; flag for the next pass;
* **legitimate ratios** (``red_line``, ``rework_factor_pct``) that the
  regex still matches under the ``cost`` / ``rate`` heuristic.

The historical text below is preserved so reviewers can trace which
fields were swept in this wave.

---

This file lists every Pydantic schema field across `backend/app/modules/`
that still serialises a *currency amount* as a JSON `number` rather than
the v3 §10 `Decimal`-as-string contract. The current PR fixed the **top
40** highest-blast-radius fields; the **109 remaining** are catalogued
below for future waves to clean up.

## Why this matters

Floats silently lose precision past ~15 significant figures, and force
every consumer (frontend, integrations, exports) to parse a
locale-coloured number with all its rounding hazards. The agreed v3 §10
contract is:

```python
from decimal import Decimal
from pydantic import field_serializer

class FooResponse(BaseModel):
    price: Decimal          # was: float

    @field_serializer("price", when_used="json")
    def _ser_price(self, v: Decimal) -> str:
        return format(v, "f") if v is not None else None
```

The canonical helper lives in `backend/app/modules/boq/schemas.py`
(`_serialise_money`) and is mirrored verbatim by sibling modules
(`match_elements/schemas.py`, `bim_hub/schemas.py`).

## CI guard

`backend/tests/unit/test_money_decimal_global.py::test_money_as_float_deficit_does_not_grow`
walks every module's Pydantic schemas and asserts that the count of
money-named `"type": "number"` fields is `<= 109`. **Lower the cap each
time you fix more fields.** New money-as-float fields ADDED to a schema
will push the count over the cap and fail CI.

## Suggested fix per field

For each entry below, the playbook is:

1. Change `field: float` → `field: Decimal` (or `Decimal | None`).
2. Drop the `Decimal("0")` default if there was a float default.
3. Add `@field_serializer("field", when_used="json")` returning
   `_serialise_money(v)`.
4. If the producing service does arithmetic with floats, switch to
   `Decimal` end-to-end (mirror the change made to
   `_round_currency` in `backend/app/modules/boq/service.py`).
5. Re-test — Pydantic v2 coerces `int`/`float`/`str` inputs to
   `Decimal` automatically, so most call sites need no change. Watch
   out for `float * Decimal` arithmetic that would `TypeError`.

## Deferred fields (109)

### ai (2)

- backend/app/modules/ai/schemas.py:140  `EstimateItem.unit_rate`
- backend/app/modules/ai/schemas.py:164  `EstimateJobResponse.grand_total`

### assemblies (5)

- backend/app/modules/assemblies/schemas.py:436  `AppliedComponent.unit_rate`
- backend/app/modules/assemblies/schemas.py:462  `ApplyTemplateResponse.grand_total`
- backend/app/modules/assemblies/schemas.py:105  `ComponentCreate.unit_cost`
- backend/app/modules/assemblies/schemas.py:154  `ComponentResponse.unit_cost`
- backend/app/modules/assemblies/schemas.py:134  `ComponentUpdate.unit_cost`

### boq (15)

- backend/app/modules/boq/schemas.py:1457  `CostRiskResponse.base_total`
- backend/app/modules/boq/schemas.py:1461  `CostRiskResponse.recommended_budget`
- backend/app/modules/boq/schemas.py:1819  `EscalateRateResponse.escalated_rate`
- backend/app/modules/boq/schemas.py:1818  `EscalateRateResponse.original_rate`
- backend/app/modules/boq/schemas.py:1811  `EscalationFactors.labor_cost_change`
- backend/app/modules/boq/schemas.py:1839  `LineItemResponse.total_cost`
- backend/app/modules/boq/schemas.py:1838  `LineItemResponse.unit_rate`
- backend/app/modules/boq/schemas.py:769   `MarkupCalculated.fixed_amount`
- backend/app/modules/boq/schemas.py:729   `MarkupCreate.fixed_amount`
- backend/app/modules/boq/schemas.py:766   `MarkupResponse.fixed_amount`
- backend/app/modules/boq/schemas.py:748   `MarkupUpdate.fixed_amount`
- backend/app/modules/boq/schemas.py:255   `PositionCreate.unit_rate` *(request — accept str/number)*
- backend/app/modules/boq/schemas.py:403   `PositionUpdate.unit_rate` *(request — accept str/number)*
- backend/app/modules/boq/schemas.py:1689  `PrerequisiteItem.typical_rate_eur`
- backend/app/modules/boq/schemas.py:1413  `SensitivityResponse.base_total`

### catalog (8)

- backend/app/modules/catalog/schemas.py:35   `CatalogResourceCreate.base_price`
- backend/app/modules/catalog/schemas.py:37   `CatalogResourceCreate.max_price`
- backend/app/modules/catalog/schemas.py:36   `CatalogResourceCreate.min_price`
- backend/app/modules/catalog/schemas.py:105  `CatalogResourceResponse.base_price`
- backend/app/modules/catalog/schemas.py:107  `CatalogResourceResponse.max_price`
- backend/app/modules/catalog/schemas.py:106  `CatalogResourceResponse.min_price`
- backend/app/modules/catalog/schemas.py:159  `CatalogSearchQuery.max_price` *(query param — accept str/number)*
- backend/app/modules/catalog/schemas.py:158  `CatalogSearchQuery.min_price` *(query param — accept str/number)*

### clash_ai_triage (1)

- backend/app/modules/clash_ai_triage/schemas.py:97  `TriageResultResponse.cost_usd_estimate`

### clash_cost_impact (2)

- backend/app/modules/clash_cost_impact/schemas.py:61  `CostImpactComponents.labour_subtotal`
- backend/app/modules/clash_cost_impact/schemas.py:47  `CostImpactComponents.rework_subtotal`

### coordination_hub (1)

- backend/app/modules/coordination_hub/schemas.py:85  `CoordinationDashboardResponse.open_cost_impact_total`

### costmodel (46)

This module's entire money surface is float. A single sweep that
converts `BudgetLine*`, `CashFlow*`, `Snapshot*`, `Dashboard*` and
`Variance*` schemas would clear the largest deferred block in one PR.

- backend/app/modules/costmodel/schemas.py:89   `BudgetLineCreate.actual_amount`
- backend/app/modules/costmodel/schemas.py:88   `BudgetLineCreate.committed_amount`
- backend/app/modules/costmodel/schemas.py:90   `BudgetLineCreate.forecast_amount`
- backend/app/modules/costmodel/schemas.py:87   `BudgetLineCreate.planned_amount`
- backend/app/modules/costmodel/schemas.py:129  `BudgetLineResponse.actual_amount`
- backend/app/modules/costmodel/schemas.py:128  `BudgetLineResponse.committed_amount`
- backend/app/modules/costmodel/schemas.py:130  `BudgetLineResponse.forecast_amount`
- backend/app/modules/costmodel/schemas.py:127  `BudgetLineResponse.planned_amount`
- backend/app/modules/costmodel/schemas.py:108  `BudgetLineUpdate.actual_amount`
- backend/app/modules/costmodel/schemas.py:107  `BudgetLineUpdate.committed_amount`
- backend/app/modules/costmodel/schemas.py:109  `BudgetLineUpdate.forecast_amount`
- backend/app/modules/costmodel/schemas.py:106  `BudgetLineUpdate.planned_amount`
- backend/app/modules/costmodel/schemas.py:152  `CashFlowCreate.actual_inflow`
- backend/app/modules/costmodel/schemas.py:153  `CashFlowCreate.actual_outflow`
- backend/app/modules/costmodel/schemas.py:155  `CashFlowCreate.cumulative_actual`
- backend/app/modules/costmodel/schemas.py:154  `CashFlowCreate.cumulative_planned`
- backend/app/modules/costmodel/schemas.py:150  `CashFlowCreate.planned_inflow`
- backend/app/modules/costmodel/schemas.py:151  `CashFlowCreate.planned_outflow`
- backend/app/modules/costmodel/schemas.py:234  `CashFlowPeriod.cumulative_actual`
- backend/app/modules/costmodel/schemas.py:233  `CashFlowPeriod.cumulative_planned`
- backend/app/modules/costmodel/schemas.py:185  `CashFlowResponse.actual_inflow`
- backend/app/modules/costmodel/schemas.py:186  `CashFlowResponse.actual_outflow`
- backend/app/modules/costmodel/schemas.py:188  `CashFlowResponse.cumulative_actual`
- backend/app/modules/costmodel/schemas.py:187  `CashFlowResponse.cumulative_planned`
- backend/app/modules/costmodel/schemas.py:183  `CashFlowResponse.planned_inflow`
- backend/app/modules/costmodel/schemas.py:184  `CashFlowResponse.planned_outflow`
- backend/app/modules/costmodel/schemas.py:167  `CashFlowUpdate.actual_inflow`
- backend/app/modules/costmodel/schemas.py:168  `CashFlowUpdate.actual_outflow`
- backend/app/modules/costmodel/schemas.py:170  `CashFlowUpdate.cumulative_actual`
- backend/app/modules/costmodel/schemas.py:169  `CashFlowUpdate.cumulative_planned`
- backend/app/modules/costmodel/schemas.py:165  `CashFlowUpdate.planned_inflow`
- backend/app/modules/costmodel/schemas.py:166  `CashFlowUpdate.planned_outflow`
- backend/app/modules/costmodel/schemas.py:202  `DashboardResponse.total_actual`
- backend/app/modules/costmodel/schemas.py:200  `DashboardResponse.total_budget`
- backend/app/modules/costmodel/schemas.py:201  `DashboardResponse.total_committed`
- backend/app/modules/costmodel/schemas.py:26   `SnapshotCreate.actual_cost`
- backend/app/modules/costmodel/schemas.py:25   `SnapshotCreate.earned_value`
- backend/app/modules/costmodel/schemas.py:24   `SnapshotCreate.planned_cost`
- backend/app/modules/costmodel/schemas.py:59   `SnapshotResponse.actual_cost`
- backend/app/modules/costmodel/schemas.py:58   `SnapshotResponse.earned_value`
- backend/app/modules/costmodel/schemas.py:57   `SnapshotResponse.planned_cost`
- backend/app/modules/costmodel/schemas.py:41   `SnapshotUpdate.actual_cost`
- backend/app/modules/costmodel/schemas.py:40   `SnapshotUpdate.earned_value`
- backend/app/modules/costmodel/schemas.py:39   `SnapshotUpdate.planned_cost`
- backend/app/modules/costmodel/schemas.py:348  `VarianceResponse.budget`
- backend/app/modules/costmodel/schemas.py:350  `VarianceResponse.variance_abs`

### finance (9)

- backend/app/modules/finance/schemas.py:488  `FinanceDashboardResponse.total_actual`
- backend/app/modules/finance/schemas.py:485  `FinanceDashboardResponse.total_budget_original`
- backend/app/modules/finance/schemas.py:486  `FinanceDashboardResponse.total_budget_revised`
- backend/app/modules/finance/schemas.py:487  `FinanceDashboardResponse.total_committed`
- backend/app/modules/finance/schemas.py:479  `FinanceDashboardResponse.total_overdue`
- backend/app/modules/finance/schemas.py:477  `FinanceDashboardResponse.total_payable`
- backend/app/modules/finance/schemas.py:492  `FinanceDashboardResponse.total_payments`
- backend/app/modules/finance/schemas.py:478  `FinanceDashboardResponse.total_receivable`
- backend/app/modules/finance/schemas.py:489  `FinanceDashboardResponse.total_variance`

### risk (7)

- backend/app/modules/risk/schemas.py:77   `RiskCreate.impact_cost`
- backend/app/modules/risk/schemas.py:91   `RiskCreate.response_cost`
- backend/app/modules/risk/schemas.py:142  `RiskResponse.impact_cost`
- backend/app/modules/risk/schemas.py:157  `RiskResponse.response_cost`
- backend/app/modules/risk/schemas.py:184  `RiskSummary.total_exposure`
- backend/app/modules/risk/schemas.py:111  `RiskUpdate.impact_cost`
- backend/app/modules/risk/schemas.py:125  `RiskUpdate.response_cost`

### schedule (8)

- backend/app/modules/schedule/schemas.py:685  `LaborCostByPhaseRow.labor_cost`
- backend/app/modules/schedule/schemas.py:686  `LaborCostByPhaseRow.total_cost`
- backend/app/modules/schedule/schemas.py:316  `WorkOrderCreate.actual_cost`
- backend/app/modules/schedule/schemas.py:315  `WorkOrderCreate.planned_cost`
- backend/app/modules/schedule/schemas.py:370  `WorkOrderResponse.actual_cost`
- backend/app/modules/schedule/schemas.py:369  `WorkOrderResponse.planned_cost`
- backend/app/modules/schedule/schemas.py:339  `WorkOrderUpdate.actual_cost`
- backend/app/modules/schedule/schemas.py:338  `WorkOrderUpdate.planned_cost`

### tendering (5)

- backend/app/modules/tendering/schemas.py:155  `BidComparisonResponse.budget_total`
- backend/app/modules/tendering/schemas.py:142  `BidComparisonRow.budget_quantity` *(measurement, but priced — verify per project)*
- backend/app/modules/tendering/schemas.py:143  `BidComparisonRow.budget_rate`
- backend/app/modules/tendering/schemas.py:144  `BidComparisonRow.budget_total`
- backend/app/modules/tendering/schemas.py:77   `BidLineItem.unit_rate`

## Fields intentionally NOT converted (ratios / measurements / IDs)

For reference — these match the money-name regex but are pure ratios,
quantities or counts and should stay `float`/`int`:

- `*_pct`, `*_percentage`, `*_count`, `*_mb` — suffix-filtered
- `pick_rate`, `feedback_rate_pct`, `cache_hit_rate_pct`,
  `qty_variance_pct`, `gr_rejection_rate`, `rate_completeness_pct`
- `total_artifact_size_mb`, `total_original_size_mb`, `total_size_mb`
- `total_workforce_hours`, `total_delay_hours`
- `share_of_total`, `share_pct`, `completion_pct`, `abc_percentage`
- `auto_confirm_threshold` (0.0–1.0 score)
- `measurement_value` (a number with a unit, not money)
- `factor` (multiplier)
- `interest_rate` (the audit explicitly calls this "debatable" — it is
  a percentage when stored as 0.05, money when stored as the annual
  payment; leave as float pending a domain decision)

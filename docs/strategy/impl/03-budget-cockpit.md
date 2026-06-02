# 03 - Unified Budget Cockpit (budget to committed to actual to forecast)

Status: design, not yet implemented.
Owner module: `oe_costmodel` (the cockpit is an aggregation surface, it owns no new transactional truth).
Depends on: `01-cost-spine` (the cost-account/WBS keying that lets budget, commitment and actual rows line up).

## 1. What this is and why it connects modules

A project controls manager wants one screen that answers a single question per cost account: how much did we budget, how much have we committed through contracts and purchase orders, how much have we actually spent through finance, and where will we land at completion. Today the platform holds every one of those numbers, but in four different places that never reconcile:

- Budget lives in `oe_costmodel.BudgetLine` (`backend/app/modules/costmodel/models.py`, `planned_amount`) and a second, parallel `oe_finance.ProjectBudget` (`backend/app/modules/finance/models.py`, `original_budget` / `revised_budget`).
- Committed is a free-text number typed into `BudgetLine.committed_amount`. It is never derived from contracts. `generate_budget_from_boq` in `backend/app/modules/costmodel/service.py` hard-codes `committed_amount="0"`. The real commitment data sits in `oe_contracts.Contract.total_value` plus approved `oe_changeorders.ChangeOrder.cost_impact`.
- Actual is likewise a free-text `BudgetLine.actual_amount` (also hard-coded to `"0"` on generation). The real spend sits in `oe_finance.Invoice` (payable, `status="paid"`) plus `oe_finance.Payment` rows, and on the contract side in `oe_contracts.ProgressClaim` (`status="paid"`, via `claim_repo.paid_total`).
- Forecast is a third free-text field, `BudgetLine.forecast_amount`, plus the EAC computed independently in both `CostModelService.calculate_evm` and `FinanceService.create_evm_snapshot`.

The cockpit's entire reason to exist is the connective tissue: a deterministic rollup service that reads contracts, change orders and finance, snaps those numbers onto the cost spine, writes them back onto the budget rows as a verifiable derived value, and renders one reconciled table plus a waterfall. It introduces almost no new transactional data. It introduces a link table (so a contract or invoice is tied to a budget account) and a periodic snapshot table (so the cockpit can show movement over time and feed a defensible audit record).

The design is region-neutral at the core. The same four-column rollup (budget, committed, actual, forecast) plus variance and the cost-to-complete is the universal project-controls view. Region-specific renderings (US AIA G702/G703 continuation, DACH DIN 276 Kostengruppen grouping, UK JCT interim valuation) are presentation and grouping extensions layered through partner packs, not core branches.

## 2. Verification of existing data (done against the code)

| Claim | Evidence in code |
| --- | --- |
| `BudgetLine` already has all four columns | `backend/app/modules/costmodel/models.py` lines 91-94: `planned_amount`, `committed_amount` ("Contracts signed"), `actual_amount` ("Invoices paid"), `forecast_amount`, all `String(50)` money, plus `boq_position_id`, `activity_id`, `category`, `currency`, `metadata_`. |
| committed/actual are never auto-populated today | `CostModelService.generate_budget_from_boq` sets `committed_amount="0"`, `actual_amount="0"` (service.py ~1044-1054). No code path writes them from contracts or finance. |
| A FX-aware rollup pattern already exists and is shared | `backend/app/modules/costmodel/repository.py`: `_amount_in_base`, `_project_fx_context`, `aggregate_by_project`, `aggregate_by_category`. Same convention mirrored in `finance/service.py` (`_project_fx_map`, `_convert_to_base`) and `changeorders/repository.py` (`_project_fx_map`). |
| Commitment source: contracts | `Contract.total_value` Numeric(18,4), `status` (draft/active/suspended/terminated/completed), `currency`, `project_id` FK. `ContractRepository.list_for_project(status=...)`. Change orders amend it via `ContractsService.apply_change_order_to_contract`. |
| Commitment delta source: change orders | `ChangeOrder.cost_impact` (signed `MoneyType`), `approved_amount`, `status` with `VALID_TRANSITIONS` (draft/submitted/approved/executed/rejected). `ChangeOrderRepository.get_summary` already produces FX-converted `total_approved_amount` for approved-only COs (repository.py 176-298). |
| Actual source: finance | `Invoice.invoice_direction` (payable/receivable), `amount_total` (`MoneyType`), `status` (the canonical paid node is `"paid"`, see `_INVOICE_STATUS_TRANSITIONS`). `InvoiceLineItem` carries `wbs_id` and `cost_category`. `PaymentRepository.aggregate_by_currency`. `pay_invoice` already buckets paid amounts by `(wbs_id, cost_category)` onto `ProjectBudget.actual`. |
| Actual source: contract progress claims | `ProgressClaim.status="paid"`, `ContractLineRepository`/`claim_repo.paid_total(contract_id)` sums paid claims (contracts/repository.py ~243). |
| Money is string/Decimal, dates are ISO strings, ids are UUID | `BudgetLine` money columns are `String(50)`; `MoneyType` (`backend/app/core/db_types.py`) gives NUMERIC on Postgres and VARCHAR(50) on SQLite, always returning `Decimal`. `GUID` keys. Schemas serialise money as Decimal-as-string (`_serialise_money` in costmodel/schemas.py). |
| Project currency and FX live on the project | `Project.currency` (`String`, defaults `"EUR"`), `Project.fx_rates` (JSON list of `{code, rate, label}`, rate = base units per 1 foreign unit). |
| Router, RBAC and project-scope conventions | `backend/app/modules/costmodel/router.py`: `APIRouter(tags=["costmodel"])`, `Depends(RequirePermission("costmodel.read"|"costmodel.write"))`, `await verify_project_access(project_id, user_id, session)`, mounted by the loader at `/api/v1/costmodel` (`module_loader.py` line 207, kebab == dir name here). |
| Permissions exist | `register_costmodel_permissions` -> `costmodel.read` (VIEWER), `costmodel.write` (EDITOR), `costmodel.manage` (MANAGER). |
| Two parallel budget/EVM tables exist | `oe_costmodel_budget_line` vs `oe_finance_budget`; `oe_costmodel_snapshot` vs `oe_finance_evm_snapshot`. The cockpit treats `oe_costmodel.BudgetLine` as the cost-account grain of record and reads finance as an actuals source. It does not try to merge the two budget tables in the MVP. |

Conclusion: the storage and the FX helpers already exist. What is missing is (a) a link between a budget account and the contracts/invoices that feed it, (b) a service that performs the rollup deterministically and writes the derived committed/actual back, (c) one cockpit endpoint that returns the reconciled rows plus totals, and (d) a periodic snapshot so movement and audit are first-class.

## 3. Data model

The cockpit lives in the `oe_costmodel` module. It adds two tables and a small set of nullable columns. It reuses `BudgetLine` as is.

### 3.1 Reuse, unchanged

`oe_costmodel_budget_line` stays the cost-account grain. `planned_amount` remains the human-entered budget. `committed_amount`, `actual_amount`, `forecast_amount` become derived-by-default (written by the rollup) but stay manually overridable (see `is_committed_locked` below). `category`, `boq_position_id`, `activity_id`, `currency`, `metadata_` are reused.

### 3.2 New columns on `oe_costmodel_budget_line`

These give a budget line a stable cost-account key (the link to `01-cost-spine`) and let the rollup record provenance without destroying a manual override.

| Column | Type | Purpose |
| --- | --- | --- |
| `cost_account_code` | `String(80)`, nullable, indexed | The cost-spine account key (DIN KG, CSI division, WBS code, or a user code). This is what contract lines, CO items and invoice lines map to. Populated from `01-cost-spine`. |
| `committed_source` | `String(20)`, not null, default `"manual"` | One of `manual`, `derived`. `derived` means the rollup owns the number. |
| `actual_source` | `String(20)`, not null, default `"manual"` | Same vocabulary for actuals. |
| `forecast_method` | `String(30)`, not null, default `"manual"` | `manual`, `eac_cpi` (BAC/CPI), `committed_plus_etc`, `budget` (forecast == budget). Drives how the rollup recomputes forecast. |
| `committed_locked` | `Boolean`, not null, server_default `"0"` | When true the rollup must not overwrite `committed_amount` (a PM has pinned a manual figure). Same belt as finance's manual overrides. |
| `actual_locked` | `Boolean`, not null, server_default `"0"` | Same for `actual_amount`. |

All money stays `String(50)` on this table to avoid a destructive migration of an existing column (the established reason in `db_types.py`). New non-money columns follow the existing portable conventions (String enums, Boolean with `server_default`).

### 3.3 New table: `oe_costmodel_cost_link`

The join that ties an external commercial document to a budget account. This is the spine that makes committed and actual derivable instead of typed.

```
class CostLink(Base):
    __tablename__ = "oe_costmodel_cost_link"
    # one external source row -> one budget account, project-scoped
    project_id: UUID  GUID(), FK oe_projects_project.id ondelete=CASCADE, indexed
    budget_line_id: UUID | None  GUID(), FK oe_costmodel_budget_line.id ondelete=SET NULL, indexed
    cost_account_code: str  String(80), not null, indexed   # denormalised so a link survives a budget-line delete
    source_module: str  String(40), not null   # "contracts" | "changeorders" | "finance"
    source_type: str  String(40), not null      # "contract" | "contract_line" | "change_order" | "invoice" | "progress_claim"
    source_id: UUID  GUID(), not null, indexed   # the contract / CO / invoice id (plain UUID, resolved at service layer, NOT a cross-module FK)
    bucket: str  String(20), not null            # "committed" | "actual" (which column this row feeds)
    link_origin: str  String(20), not null, default "auto"   # "auto" (mapped by code) | "manual" (user pinned)
    metadata_: JSON
    __table_args__ = (
        UniqueConstraint("project_id", "source_module", "source_type", "source_id", "bucket",
                         name="uq_costmodel_cost_link_source"),
        Index("ix_costmodel_cost_link_project_bucket", "project_id", "bucket"),
        Index("ix_costmodel_cost_link_account", "project_id", "cost_account_code"),
    )
```

Cross-module ids are stored as plain `GUID()` columns with no SQLAlchemy `ForeignKey`, exactly like `Contract.counterparty_id` and `ChangeOrder` `linked_po_ids`. Resolution is a service concern and modules stay decoupled. The unique constraint makes the auto-mapper idempotent: re-running the rollup cannot create a second link for the same source/bucket.

### 3.4 New table: `oe_costmodel_cockpit_snapshot`

A periodic, immutable record of the reconciled rollup so the cockpit can show movement (this period vs last) and so a snapshot is defensible at an audit. This is distinct from `CostSnapshot` (which is EVM BCWS/BCWP/ACWP) and from `finance.EVMSnapshot`. The cockpit snapshot is the four-column controls picture per account, captured monthly.

```
class CockpitSnapshot(Base):
    __tablename__ = "oe_costmodel_cockpit_snapshot"
    project_id: UUID  GUID(), FK oe_projects_project.id ondelete=CASCADE, indexed
    period: str  String(20), not null   # "YYYY-MM"
    captured_at: str  String(40), not null   # ISO datetime string
    base_currency: str  String(10), not null, default ""
    # whole-project totals, all base currency, Decimal-as-string
    total_budget: str  String(50), default "0"
    total_committed: str  String(50), default "0"
    total_actual: str  String(50), default "0"
    total_forecast: str  String(50), default "0"
    # per-account breakdown frozen at capture time
    rows_json: JSON   # list[{cost_account_code, category, budget, committed, actual, forecast, variance}]
    mixed_currencies: bool  Boolean, server_default "0"
    missing_fx_rates: JSON   # list[str] ISO codes with no rate at capture
    created_by: str | None  String(36)
    metadata_: JSON
    __table_args__ = (
        UniqueConstraint("project_id", "period", name="uq_costmodel_cockpit_snapshot_period"),
    )
```

The `(project_id, period)` unique constraint mirrors the `CostSnapshot` v3108 guard so two monthly captures cannot silently coexist and flap the "movement" delta. Re-capturing a period is an explicit overwrite (PUT semantics) not a duplicate insert.

### 3.5 Alembic migration outline

One revision file, named in the repo convention `vNN_costmodel_budget_cockpit.py` (latest is `v41_*`, so this would be the next `vNN`). It must be additive and dialect-safe (Postgres default, SQLite dev), following the project's established `create_all`-friendly pattern for new tables and `batch_alter_table` for the column adds.

```
def upgrade():
    # 1. New tables
    op.create_table("oe_costmodel_cost_link", ... GUID() pk, columns as 3.3 ...)
    op.create_index("ix_costmodel_cost_link_project_bucket", ...)
    op.create_index("ix_costmodel_cost_link_account", ...)
    op.create_unique_constraint("uq_costmodel_cost_link_source", ...)

    op.create_table("oe_costmodel_cockpit_snapshot", ... GUID() pk, columns as 3.4 ...)
    op.create_unique_constraint("uq_costmodel_cockpit_snapshot_period", ...)

    # 2. New columns on the existing budget-line table (batch for SQLite ALTER limits)
    with op.batch_alter_table("oe_costmodel_budget_line") as b:
        b.add_column(sa.Column("cost_account_code", sa.String(80), nullable=True))
        b.add_column(sa.Column("committed_source", sa.String(20), nullable=False, server_default="manual"))
        b.add_column(sa.Column("actual_source", sa.String(20), nullable=False, server_default="manual"))
        b.add_column(sa.Column("forecast_method", sa.String(30), nullable=False, server_default="manual"))
        b.add_column(sa.Column("committed_locked", sa.Boolean(), nullable=False, server_default="0"))
        b.add_column(sa.Column("actual_locked", sa.Boolean(), nullable=False, server_default="0"))
    op.create_index("ix_costmodel_budget_line_cost_account", "oe_costmodel_budget_line", ["cost_account_code"])

def downgrade():
    # drop index, drop the six columns (batch), drop the two tables
```

GUID primary keys and `created_at`/`updated_at` come from `Base` exactly like every existing model. No data backfill is required: existing budget lines keep `committed_source="manual"`, so the cockpit treats their current typed numbers as manual until a rollup is run.

## 4. API

All routes live in `backend/app/modules/costmodel/router.py` (extending the existing router, mounted at `/api/v1/costmodel`). They follow the established trio: `Depends(RequirePermission(...))`, `await verify_project_access(project_id, user_id, session)`, `SessionDep`, `CurrentUserId`. Money in responses is Decimal-as-string.

### 4.1 Read the cockpit

```
GET /api/v1/costmodel/projects/{project_id}/cockpit/
  perm: costmodel.read
  query: group_by = "account" | "category"   (default "account")
         as_of    = "YYYY-MM" optional, reads the snapshot for that period instead of live
  ->  CockpitResponse {
        currency: str,
        mixed_currencies: bool,
        missing_fx_rates: list[str],
        totals: { budget, committed, actual, forecast,
                  variance,            # budget - forecast
                  variance_pct,
                  cost_to_complete,    # forecast - actual
                  committed_uncommitted, # budget - committed
                  pct_committed, pct_spent },
        rows: list[CockpitRow {
            cost_account_code: str | None,
            category: str,
            description: str,
            budget, committed, actual, forecast: str,   # Decimal-as-string, base currency
            variance: str, variance_pct: float,
            cost_to_complete: str,
            committed_source: str, actual_source: str, forecast_method: str,
            committed_locked: bool, actual_locked: bool,
            health: str   # "on_budget" | "watch" | "over"
        }],
        last_refreshed_at: str | None,   # when the derived numbers were last recomputed
      }
```

This is a pure read. It does not mutate. If `as_of` is given it deserialises `CockpitSnapshot.rows_json` for that period; otherwise it computes the live rollup from the current budget lines (which carry whatever the last refresh wrote).

### 4.2 Refresh the derived numbers (the connective action)

```
POST /api/v1/costmodel/projects/{project_id}/cockpit/refresh/
  perm: costmodel.write
  body: { recompute_forecast: bool = true }
  ->  CockpitResponse   (same shape, freshly recomputed)
```

This is the core flow. It (1) re-runs the auto-mapper to keep `CostLink` rows in sync with contracts / change orders / finance, (2) sums committed and actual per account, (3) writes them back onto `BudgetLine.committed_amount` / `actual_amount` for rows whose source is `derived` and not locked, (4) recomputes `forecast_amount` per `forecast_method`, and (5) returns the reconciled view. Idempotent: running it twice in a row yields identical numbers.

### 4.3 Drill-down: what feeds an account

```
GET /api/v1/costmodel/projects/{project_id}/cockpit/lines/{budget_line_id}/sources/
  perm: costmodel.read
  ->  { committed: list[SourceRef], actual: list[SourceRef] }
      SourceRef { source_module, source_type, source_id, label, amount, currency, status, link_origin }
```

Lets the UI expand a row to "this 240,000 committed = Contract C-014 (200,000) + CO-003 approved (40,000)". The label and status are resolved through the owning module's repository at read time.

### 4.4 Manual link and override

```
POST   /api/v1/costmodel/projects/{project_id}/cockpit/links/        perm: costmodel.write
        body: { budget_line_id, source_module, source_type, source_id, bucket }
        ->  CostLink   (link_origin="manual")
DELETE /api/v1/costmodel/cockpit/links/{link_id}                     perm: costmodel.write
PATCH  /api/v1/costmodel/5d/budget-lines/{line_id}                   (existing route, extended)
        accepts committed_locked / actual_locked / forecast_method / committed_source / actual_source
```

The existing `PATCH /5d/budget-lines/{line_id}` already lets a user type a committed/actual figure; we extend its `BudgetLineUpdate` schema with the lock/source/forecast-method fields so a manual figure can be pinned against the rollup.

### 4.5 Snapshot the cockpit

```
POST /api/v1/costmodel/projects/{project_id}/cockpit/snapshots/
  perm: costmodel.write
  body: { period: "YYYY-MM" }   # defaults to current month
  ->  CockpitSnapshotResponse   (409 if exists, mirroring CostSnapshot create)
PUT  /api/v1/costmodel/projects/{project_id}/cockpit/snapshots/{period}   # explicit overwrite
GET  /api/v1/costmodel/projects/{project_id}/cockpit/snapshots/           # list, period asc
  perm: costmodel.read
```

Snapshots feed the period-over-period movement column and give an auditable controls record.

### 4.6 RBAC and project scoping summary

| Endpoint | Permission | Scope guard |
| --- | --- | --- |
| GET cockpit, sources, snapshots list | `costmodel.read` | `verify_project_access(project_id, user_id, session)` |
| POST refresh, links, snapshots; PATCH budget-line; DELETE link | `costmodel.write` | same; link/snapshot writes re-resolve the parent project from the row before the guard (the IDOR-404 pattern used in the existing `update_budget_line`) |

No new permission keys are needed. The three existing keys (`costmodel.read`, `costmodel.write`, `costmodel.manage`) cover the surface. Reading contracts/finance inside the rollup is done through their repositories with the current session, scoped by `project_id`, so a user who can see the project's cost model sees its reconciled commitments without needing the contracts or finance write scopes.

## 5. Service logic - the connective tissue

A new `CockpitService` in `backend/app/modules/costmodel/service.py` (or a sibling `cockpit_service.py` to keep the file readable), constructed with the `AsyncSession` like `CostModelService`. It composes the other modules' repositories, never their HTTP layer.

### 5.1 Core flow: `refresh_cockpit(project_id, recompute_forecast=True)`

1. Resolve FX context once. Reuse `BudgetLineRepository._project_fx_context(project_id)` to get `(base_currency, fx_map)`. Every external amount is converted via `_amount_in_base(raw, source_currency, base_currency, fx_map)` before it touches a total. Foreign amounts with no configured rate are kept in their own units (never zeroed) and their codes collected into `missing_fx_rates`, exactly as the existing aggregators do.

2. Load the budget lines for the project (`BudgetLineRepository.list_for_project(project_id, limit=10000)`). Build an account index keyed by `cost_account_code`, falling back to `category` when a line has no account code (so a project that has not adopted the cost spine still reconciles by category). This fallback is what makes the cockpit usable before `01-cost-spine` is fully populated.

3. Gather committed sources.
   - Contracts: `ContractRepository(session).list_for_project(project_id, status="active", limit=...)` plus `status="suspended"` (commercially live, matching `apply_change_order_to_contract`). For each contract, distribute `total_value` to accounts. Two modes: if the contract has SoV lines (`ContractLineRepository.list_for_contract`) and those lines carry a cost account in `metadata_` or `code`, distribute per line; otherwise attribute the whole `total_value` to the contract's mapped account (or the catch-all account when unmapped). Mapping precedence is described in 5.3.
   - Change orders: reuse the already-correct `ChangeOrderRepository.get_summary(project_id)` which returns FX-converted `total_approved_amount` for approved-only COs, and additionally walk approved/executed COs per account when CO items carry a cost code. Approved COs raise committed; this matches the contracts rule that only approved scope changes count (`changeorders/repository.py` 225-250).
   - For each committed source amount, upsert a `CostLink` row (`bucket="committed"`, `link_origin="auto"`) keyed by the unique constraint, so the drill-down in 4.3 is backed by real rows and re-running is idempotent.

4. Gather actual sources.
   - Finance payable invoices: load paid payable invoices (`InvoiceRepository.list(project_id=..., direction="payable", status="paid")` with `selectinload(Invoice.line_items)`). Bucket each line's `amount` by its `cost_category` / `wbs_id` onto the matching account; invoices with no line breakdown attribute `amount_total` to the catch-all account. This is the same bucketing `FinanceService.pay_invoice` already does against `ProjectBudget.actual`, lifted to the cost-account grain.
   - Contract progress claims: `claim_repo.paid_total(contract_id)` per active contract attributes paid claim value to that contract's account. This captures spend that flows through the contract valuation route rather than standalone invoices.
   - Upsert `CostLink` rows with `bucket="actual"`.

5. Write back. For every account, sum committed and actual in base currency. For each budget line in the account whose `committed_source="derived"` and `committed_locked=False`, write the account's committed total (split pro-rata by `planned_amount` when an account maps to several lines, so a single account split across material/labor keeps both rows meaningful). Same for actuals. Lines that are `manual` or `locked` are left exactly as the user set them and are still included in the totals. Persist via `BudgetLineRepository.update_fields`.

6. Recompute forecast when asked, per line `forecast_method`:
   - `budget`: forecast = budget (planned_amount). The neutral default for a healthy line.
   - `committed_plus_etc`: forecast = committed + max(0, budget - committed) when nothing is spent yet, tightening to committed + (committed - actual remaining) as work proceeds. Concretely forecast = max(committed, budget) once committed exceeds budget, capturing overrun the moment a contract or approved CO pushes commitment past budget.
   - `eac_cpi`: forecast = budget / CPI using the project CPI from `CostModelService.calculate_evm` (which already derives CPI from schedule progress and actuals). This is the EVM forecast and reuses existing logic rather than re-deriving it.
   - `manual`: untouched.

7. Build and return the `CockpitResponse` from the freshly written lines, including `totals` (budget, committed, actual, forecast, variance = budget - forecast, cost_to_complete = forecast - actual, committed_uncommitted = budget - committed, pct_committed, pct_spent), `mixed_currencies` (more than one distinct non-blank line currency, computed like the existing `_distinct_budget_currencies` helper in the router), and `missing_fx_rates`. Publish `costmodel.cockpit.refreshed` via `event_bus.publish_detached` (same `_safe_publish` wrapper used throughout the module) so dashboards and notifications can react.

### 5.2 Read flow: `get_cockpit(project_id, group_by, as_of)`

If `as_of` is set, load `CockpitSnapshot` for that period and project, deserialise `rows_json`, regroup if `group_by="category"`. Otherwise read the current budget lines and assemble the same response without recomputing (the numbers on the lines are whatever the last `refresh` wrote). Grouping by category sums lines sharing a `category`; grouping by account sums lines sharing `cost_account_code`. This keeps reads cheap and makes refresh the single place that touches the other modules.

### 5.3 Account mapping precedence (the link to 01-cost-spine)

A source amount is attributed to an account by, in order: (1) an explicit `CostLink` with `link_origin="manual"` for that source (a user pinned it); (2) a cost account carried on the source row itself, the `cost_account_code` that `01-cost-spine` stamps onto contract lines, CO items and invoice lines; (3) the source's own category mapped to the matching budget category; (4) a per-project catch-all account `__unmapped__` so no committed or actual money is ever silently dropped. The catch-all is surfaced as its own cockpit row labelled "Unmapped" so the gap is visible and a controls manager can fix the mapping, rather than the rollup quietly under-reporting commitment. This degrade-visibly stance matches the module's FX rule (a missing rate is shown, never zeroed).

### 5.4 Why this does not double count

Committed counts contract value plus approved change-order deltas. It does not also count purchase invoices, because an invoice is the realisation of a commitment, captured under actual. Actual counts paid payable invoices and paid progress claims. A progress claim that has been turned into a finance invoice would be double counted, so the mapper dedupes: when a finance invoice carries a `metadata_` reference to a contract progress claim (the link finance already supports through `source_type`/`source_id` on the ledger and invoice metadata), the claim side is suppressed in favour of the invoice. Where no such link exists the two are disjoint by construction (standalone payable invoices vs contract valuations).

## 6. Frontend

Feature folder: `frontend/src/features/costmodel` (existing). The cockpit is a new screen and a new tab inside `CostModelPage.tsx`, reusing its project header, breadcrumb, currency formatter (`formatCurrency` already defined there using `Intl.NumberFormat` + `getIntlLocale`), and React Query setup.

### 6.1 Files

- `frontend/src/features/costmodel/BudgetCockpit.tsx` - the screen. A reconciled table (one row per cost account or category) with columns Budget, Committed, Actual, Forecast, Variance, Cost to complete, and a health pill. A waterfall / stacked bar across the top showing budget -> committed -> actual -> forecast for the whole project. A "Refresh from contracts and finance" button that calls the refresh endpoint and shows a toast with how many links were synced. A period selector that switches between live and a captured snapshot (`as_of`). Expandable rows that call the sources endpoint and list the contributing contracts, change orders and invoices with deep links to those modules.
- `frontend/src/features/costmodel/CockpitWaterfall.tsx` - the chart component (reuse the charting approach already used by the S-curve in `CostModelPage`).
- Extend `frontend/src/features/costmodel/api.ts` with `cockpitApi`: `getCockpit(projectId, {groupBy, asOf})`, `refreshCockpit(projectId)`, `getSources(projectId, lineId)`, `createLink`, `deleteLink`, `createSnapshot`, `listSnapshots`. Same `apiGet`/`apiPost`/`apiPatch`/`apiDelete` wrappers from `@/shared/lib/api`, same `/v1/costmodel/...` path style as the existing `costModelApi`.
- TypeScript interfaces `CockpitResponse`, `CockpitRow`, `CockpitTotals`, `SourceRef`, `CockpitSnapshot` in `api.ts`.

### 6.2 State and data flow

React Query keys `['costmodel','cockpit',projectId,groupBy,asOf]` for the read and `['costmodel','cockpit','sources',projectId,lineId]` for lazy drill-down. The refresh button is a `useMutation` that invalidates the cockpit query on success. Editing a line's lock/forecast-method reuses the existing budget-line PATCH mutation already wired in `CostModelPage`. All currency rendering goes through the existing `formatCurrency(amount, currency)`; when `mixed_currencies` is true the UI shows a small "mixed currencies, converted to {base} via project FX" hint (the `InfoHint` component already imported in `CostModelPage`) and lists `missing_fx_rates` if any, matching how the finance dashboard already surfaces that.

### 6.3 How the user reaches it

A new tab "Cockpit" in the cost model page tab strip, and an entry in the Cost / Controls area of the sidebar that routes to the cost model page with the cockpit tab active. The route is the existing cost-model route; no new top-level route is required, which keeps the sidebar contract (no project-split, importance ordering) intact.

## 7. Reuse - confirmed infrastructure to build on

| Reused asset | Location | Used for |
| --- | --- | --- |
| `BudgetLine` model + repository + FX-aware aggregators | `costmodel/models.py`, `costmodel/repository.py` (`_amount_in_base`, `_project_fx_context`, `aggregate_by_project`, `aggregate_by_category`) | cost-account grain and base-currency rollup |
| `CostModelService.calculate_evm` (CPI, EAC) | `costmodel/service.py` | `eac_cpi` forecast method |
| `MoneyType` / `GUID` / `Base` | `core/db_types.py`, `database.py` | new columns and tables, dialect-safe money |
| `ContractRepository.list_for_project(status=...)`, `ContractLineRepository`, `claim_repo.paid_total`, `apply_change_order_to_contract` | `contracts/repository.py`, `contracts/service.py` | committed (contracts) and contract-side actual (paid claims) |
| `ChangeOrderRepository.get_summary` (FX-converted approved total) | `changeorders/repository.py` | committed delta from approved change orders |
| `InvoiceRepository.list` + `selectinload(line_items)`, `PaymentRepository.aggregate_by_currency`, `pay_invoice` bucketing pattern | `finance/repository.py`, `finance/service.py` | actual (paid payable invoices) |
| `Project.currency` + `Project.fx_rates` | `projects/models.py` | base currency and conversion |
| Router conventions: `RequirePermission`, `verify_project_access`, `SessionDep`, `CurrentUserId`, kebab mount `/api/v1/costmodel` | `costmodel/router.py`, `dependencies.py`, `module_loader.py` | new endpoints |
| Permission keys `costmodel.read/write/manage` | `costmodel/permissions.py` | RBAC, no new keys |
| Event bus `_safe_publish` pattern | `costmodel/service.py` | `costmodel.cockpit.refreshed` |
| Frontend `costModelApi`, `formatCurrency`, `InfoHint`, React Query, toast store | `features/costmodel/*` | cockpit screen |

## 8. Phasing

Each phase is shippable with no stubs. Effort is in engineer-days for one backend plus one frontend developer working together.

### Phase 1 - MVP, end to end (effort_days: 7)

Scope: the cockpit reconciles and renders for real, by category, with the catch-all so nothing is dropped.
- Migration: add the six budget-line columns and the `oe_costmodel_cost_link` table (snapshot table deferred to Phase 3).
- `CockpitService.refresh_cockpit` reading active contracts (`total_value`), approved change orders (`get_summary`), and paid payable invoices; FX via the existing helpers; write committed/actual back to derived, unlocked lines; forecast methods `budget` and `committed_plus_etc`.
- Account mapping precedence by category with the `__unmapped__` catch-all (cost_account_code precedence wired but optional, since `01-cost-spine` codes may not be populated yet).
- Endpoints: GET cockpit, POST refresh, GET sources, PATCH budget-line lock/method.
- Frontend: `BudgetCockpit.tsx` table + refresh button + expandable sources + the existing currency/mixed-currency handling. Waterfall can be a simple stacked bar in this phase.
- Tests: service rollup unit tests with stub repos, one router RBAC/scope test, frontend vitest for the table and totals.

This already answers the headline question on real data because contracts, change orders and finance all exist and carry the numbers.

### Phase 2 - cost-account fidelity and progress claims (effort_days: 5)

Scope: tie into `01-cost-spine` properly and add the contract valuation route.
- Honour `cost_account_code` on contract lines, CO items and invoice line items for per-account distribution (SoV-level committed, line-level actual).
- Add paid progress claims as an actual source with the invoice-vs-claim dedupe (5.4).
- Manual links (POST/DELETE link endpoints) and the `link_origin="manual"` precedence.
- `eac_cpi` forecast method wired to `calculate_evm`.
- Group-by-account view in the UI plus pro-rata split when one account maps to several budget lines.

### Phase 3 - snapshots, movement, audit (effort_days: 4)

Scope: make the controls picture time-aware and auditable.
- `oe_costmodel_cockpit_snapshot` table + create/list/overwrite endpoints + `as_of` read.
- Period-over-period movement column (this period vs prior snapshot) and the full waterfall chart.
- Audit row on refresh and on snapshot capture via `app.core.audit_log.log_activity` (the same best-effort pattern finance uses).
- Optional auto-snapshot on month rollover through the event bus.

### Phase 4 - partner-pack region extensions (effort_days: 5)

Scope: region-specific renderings on top of the neutral core, shipped as partner-pack presentation extensions, not core branches.
- US: AIA G702/G703 continuation sheet export and column labels (scheduled value, work completed this period, stored materials, retainage) mapped from budget/committed/actual.
- DACH: DIN 276 Kostengruppen grouping preset and a Kostenkontrolle layout.
- UK: JCT interim valuation layout (gross valuation, retention, previously certified, amount due).
- These hook through the existing partner-pack entry-point mechanism and the cockpit's `group_by` plus a pack-provided label/grouping map and export renderer. No change to the rollup math.

## 9. Risks and edge cases

- Double counting commitment vs actual. Mitigated by the disjoint-by-construction rule (committed = contract + approved CO; actual = paid invoice + paid claim) and the invoice-vs-claim dedupe in 5.4. The unique constraint on `CostLink` prevents an account being fed twice from the same source/bucket.
- Multi-currency blending. Every external amount is converted to base via the project FX table before summing; foreign amounts with no rate are kept in their own units and flagged in `missing_fx_rates`, never zeroed or blended. This reuses the exact convention already proven in the costmodel, finance and changeorders aggregators.
- Manual overrides being clobbered by a refresh. `committed_locked` / `actual_locked` and the `manual` source values make refresh skip those lines while still counting them in totals.
- Unmapped money. The `__unmapped__` catch-all account guarantees committed and actual money is always visible, surfaced as its own row, so the cockpit cannot silently under-report. This is the safe failure mode while `01-cost-spine` coverage grows.
- Performance on large projects. Refresh loads contracts, COs and paid invoices for one project; the heaviest is paid invoices with line items, already eager-loaded via `selectinload` in finance. Reads are served from the budget lines or a snapshot and never re-walk the other modules. The `(project_id, bucket)` and `(project_id, cost_account_code)` indexes on `CostLink` keep drill-down cheap.
- Two parallel budget tables (`costmodel.BudgetLine` vs `finance.ProjectBudget`). The cockpit deliberately picks `BudgetLine` as the grain and reads finance only as an actuals source. Reconciling the two budget tables is explicitly out of scope here; a later spine consolidation can collapse them, and the `cost_account_code` column is the seam that will make that possible.
- Change-order status semantics. Only `approved` (and `executed`) COs raise committed, matching `apply_change_order_to_contract`'s "commercially live" rule and `get_summary`'s approved-only total. Draft/submitted COs are excluded so the cockpit does not pre-commit unapproved scope.
- Contract value vs SoV line sum drift. When a contract's SoV lines do not sum to `total_value`, Phase 2 attributes by lines and reports the residual to the catch-all rather than scaling, so the discrepancy is visible.
- TCPI / forecast undefined cases. Reuse the existing guards: `calculate_evm` already returns `tcpi=None` and clamps SPI when the project has not started; the cockpit surfaces those as-is and never renders a misleading "perfect efficiency".
- Project currency default of "EUR". The rollup reads the project's actual currency; a non-Eurozone project is converted and labelled correctly, and a blank/invalid code renders a bare number rather than mislabelling as EUR, matching the platform-wide task #217 rule.

## 10. Test plan

### Backend (pytest, per-module temp sqlite set before app import)

New module test package `backend/tests/modules/costmodel/` with the standard per-module sqlite setup (set the module DB env var before importing the app, the pattern used by the other module suites such as `tests/modules/finance/`), plus pure-service unit tests under `backend/tests/unit/` following the existing `test_costmodel_service.py` stub-repo style.

- Rollup correctness (unit, stub repos like `_StubBudgetRepo`): one account, one active contract -> committed equals contract value; add an approved CO -> committed rises by the CO amount; a submitted (not approved) CO -> committed unchanged.
- Actual rollup: one paid payable invoice with line items bucketed by `cost_category` lands on the right accounts; an invoice with no lines lands on the catch-all.
- Idempotency: `refresh_cockpit` run twice yields identical totals and creates no duplicate `CostLink` rows (asserts the unique constraint and upsert).
- Lock and source: a `manual`/`locked` line keeps its typed committed/actual through a refresh but is still summed into totals.
- FX: a contract in a foreign currency with a configured rate converts; with no rate it is kept in its own units and its code appears in `missing_fx_rates`; `mixed_currencies` flips true with two distinct line currencies.
- Forecast methods: `budget`, `committed_plus_etc` (overrun case where committed exceeds budget), `eac_cpi` (CPI from a seeded EVM path).
- Dedupe: a paid claim linked to a paid invoice is not double counted.
- API/RBAC (router-level): `costmodel.read` required for GET, `costmodel.write` for refresh/links/snapshots; cross-project access returns 404 (the IDOR-404 pattern from `finance/test_finance_security.py`); snapshot create returns 409 on duplicate period.
- Migration round-trip: include the new tables/columns in the existing `tests/integration/test_migrations_roundtrip.py` upgrade/downgrade check.

### Frontend (vitest)

- `BudgetCockpit.test.tsx`: renders rows and totals from a mocked `getCockpit`, formats money via `formatCurrency`, shows the mixed-currency hint when `mixed_currencies` is true and lists `missing_fx_rates`.
- Refresh mutation invalidates the cockpit query and shows the synced-count toast.
- Expandable row lazily calls `getSources` and renders the contributing contracts/COs/invoices with deep links.
- Variance/health pill logic (over vs watch vs on_budget) against fixture rows.
- api.ts: `cockpitApi` builds the correct `/v1/costmodel/...` paths (mirrors the existing `costModelApi` path test if present, otherwise a new assertion).

### Manual browser verification (:8000 dev server)

1. Start the backend (factory: `python -m uvicorn app.main:create_app --factory ...`) and the frontend; log in with the demo user.
2. Open a seeded project that has contracts, an approved change order, and at least one paid payable invoice. Go to Cost Model -> Cockpit.
3. Confirm the table renders budget/committed/actual/forecast/variance and the project totals; the currency matches the project.
4. Click "Refresh from contracts and finance". Confirm committed rises to contract value plus approved CO, actual reflects the paid invoice, and a toast reports the synced link count. Re-click and confirm the numbers do not change (idempotent).
5. Expand a row and confirm the contributing contract, change order and invoice are listed with working deep links to those modules.
6. Lock a row's committed and type a manual figure via the budget-line edit, refresh again, and confirm the locked figure survives while the total still includes it.
7. Switch a row's forecast method to `eac_cpi` and confirm forecast changes accordingly.
8. Capture a snapshot for the current period, switch the period selector to it, and confirm the `as_of` read renders the frozen numbers; capturing the same period again is an explicit overwrite, not a duplicate.
9. Add a foreign-currency contract with no FX rate and confirm the cockpit shows the mixed-currency hint and lists the missing rate code rather than silently dropping or blending the amount.

## 11. Module-convention checklist

- Models in `models.py`, schemas in `schemas.py`, data access in `repository.py`, business logic in `service.py` (or `cockpit_service.py`), routes in `router.py`, permissions already in `permissions.py`. Tests under `backend/tests/modules/costmodel/` and `backend/tests/unit/`.
- No new module is created; the cockpit extends `oe_costmodel`, whose manifest already declares `depends=["oe_projects", "oe_boq"]`. Reading contracts/finance/changeorders at runtime through their repositories does not require manifest dependencies (the platform loads all modules; cross-module reads are by repository, the established pattern). If stricter load ordering is wanted, add `oe_contracts`, `oe_finance`, `oe_changeorders` to the manifest `depends`.
- No IfcOpenShell, no native IFC, no BIM/CAD parsing is involved. The cockpit is purely commercial data.
- Money is Decimal-in / Decimal-as-string-out; dates are ISO strings; ids are UUID, all matching the codebase.

# 02 - Payment Applications / Progress Billing

Status: design, not yet built
Owner module: `oe_contracts` (extended), with wiring into `oe_finance`, `oe_approval_routes`, `oe_schedule`
Depends on: `01-cost-spine`
Author: DataDrivenConstruction

## 1. Summary

Periodic progress billing already has a strong spine inside the contracts module. The data model for a Schedule of Values, progress claims, claim lines, retention accrual and retention release is implemented and surfaced through a working router, service and React page. What is missing is the connective tissue that turns a progress claim into a real cross-module payment application: there is no approval routing bound to a claim, certifying a claim never produces a finance invoice, and progress percentages are typed in by hand instead of being sourced from schedule progress or the cost spine. This design fills those gaps without rewriting the existing engine. It binds the generic approval-routes engine to a new `progress_claim` target kind, adds a finance subscriber that mints a receivable or payable invoice when a claim is certified, lets a claim pull its per-line completion from the schedule and the cost spine, and adds the missing claim-line editing surface on the front end. The core stays region neutral; AIA G702/G703, DIN, JCT and similar formats hang off a documented export and clause-template extension point so partner packs can add them without touching core.

## 2. What already exists (verified in code)

Before designing anything new, this section records exactly what is already present so we build on it instead of duplicating it.

### 2.1 Contracts module data model

File: `backend/app/modules/contracts/models.py`

| Table | Model | Relevant columns |
|-------|-------|------------------|
| `oe_contracts_contract` | `Contract` | `code`, `contract_type`, `counterparty_type`, `counterparty_id` (plain UUID, resolved at service layer), `project_id` (FK `oe_projects_project`), `total_value` `Numeric(18,4)`, `currency`, `retention_percent` `Numeric(5,2)`, `retention_release_event`, `status`, `signed_at`, `terms` JSON, `metadata_` JSON |
| `oe_contracts_contract_line` | `ContractLine` | the Schedule of Values. `contract_id`, `parent_line_id` (self-FK for hierarchy), `code`, `description`, `line_type`, `unit`, `quantity` `Numeric(18,4)`, `unit_rate`, `total_value`, `order_index`, `metadata_` |
| `oe_contracts_retention_schedule` | `RetentionSchedule` | `contract_id`, `accrual_rule` JSON, `release_rule` JSON, `notes` |
| `oe_contracts_progress_claim` | `ProgressClaim` | `contract_id`, `claim_number`, `period_start`, `period_end`, `claim_date`, `gross_amount`, `retention_amount`, `prior_claims_total`, `net_due`, `status`, `submitted_at`, `approved_at`, `paid_at`, `currency`, `metadata_` |
| `oe_contracts_progress_claim_line` | `ProgressClaimLine` | `progress_claim_id`, `contract_line_id`, `period_completed_qty`, `period_completed_value`, `period_completed_pct`, `cumulative_completed_value` |
| `oe_contracts_final_account` | `FinalAccount` | close-out balances, 1:1 with contract |

Dates and times are stored as ISO `String` columns. Money is `Numeric(18,4)` mapped to Python `Decimal`. Ids are `GUID()` UUIDs. These conventions are followed by every new column in this design.

### 2.2 Contracts service and router (already surfaced)

File: `backend/app/modules/contracts/service.py` and `router.py`, mounted at `/api/v1/contracts`.

The progress-claim lifecycle is a real state machine in `service.py`:

```
_CLAIM_TRANSITIONS = {
    "draft":     {"submitted", "rejected"},
    "submitted": {"approved", "rejected"},
    "approved":  {"certified", "rejected"},
    "certified": {"paid", "rejected"},
    "paid":      frozenset(),
    "rejected":  {"draft"},
}
```

Each transition is fired through `ContractsService.transition_claim`, which already publishes detached events on the core event bus: `contracts.claim.submitted`, `contracts.claim.approved`, `contracts.claim.certified` (stamping `certified_at` / `certified_by` into `metadata_`), and `contracts.claim.paid`. The certify branch even carries a comment that the certified event is the trigger that "should" spawn an AR invoice. That subscriber does not exist yet. This design adds it.

Endpoints already live under `/api/v1/contracts`:

- `GET/POST /progress-claims/`, `GET/PATCH/DELETE /progress-claims/{id}`
- `POST /progress-claims/{id}/submit | approve | certify | reject | mark-paid`
- `POST /progress-claims/{id}/auto-generate` driven by `AutoGenerateClaimRequest` (per-line completion percent for lump sum, measured quantity for unit price, actual cost for cost-plus, time and material totals for T&M, with NTE-cap enforcement)
- `GET /progress-claims/{id}/lines`, `POST /progress-claim-lines/`, `PATCH/DELETE /progress-claim-lines/{id}`
- `GET /contracts/{id}/sov-status` returning scheduled vs billed vs earned vs paid per line, computed by the pure `compute_sov_status`
- `POST /contracts/{id}/retention/release` with idempotency on the event key, backed by `plan_retention_release`
- `POST/GET /progress-claims/{id}/lien-waivers`

The pure calculators in `service.py` are the gold here and must be reused verbatim: `compute_progress_claim_total`, `generate_lump_sum_claim`, `generate_unit_price_claim`, `generate_cost_plus_claim`, `generate_tm_claim`, `compute_sov_status`, `plan_retention_release`, `validate_lien_waiver_payload`.

### 2.3 RBAC permissions

File: `backend/app/modules/contracts/permissions.py`. Existing keys cover the claim flow: `contracts.submit_claim` (EDITOR), `contracts.approve_claim` (EDITOR), `contracts.certify_claim` (MANAGER), `contracts.mark_paid` (MANAGER), plus `contracts.read/create/update/delete`. Finance keys in `backend/app/modules/finance/permissions.py`: `finance.create` (EDITOR), `finance.approve/pay/record_payment` (MANAGER).

### 2.4 Approval routes engine

Files: `backend/app/modules/approval_routes/models.py`, `service.py`, `manifest.py`.

A complete generic multi-step approval engine. `TARGET_KINDS` already lists `"contract"`, `"invoice"`, `"change_order"`, `"variation"` and others, and the column is an open `String(64)` so a new kind needs no migration to the engine. `ApprovalRouteService` exposes `create_route`, `start_instance` (rejects a duplicate pending workflow on the same target), `submit_decision` (row-locked advance with `all`/`any`/`majority` modes), and `cancel_instance`. Every transition writes `app.core.audit_log.log_activity` and fires `approval_routes.instance.started | advanced | completed | rejected | cancelled`. The completed and rejected events carry `target_kind` and `target_id`, which is exactly what a contracts subscriber needs to advance the matching claim.

### 2.5 Finance module

Files: `backend/app/modules/finance/models.py`, `service.py`, `events.py`, `__init__.py`.

`Invoice` already has `invoice_direction` (`payable` or `receivable`), `retention_amount`, `amount_subtotal`, `tax_amount`, `amount_total`, `currency_code`, `status`, `metadata_` and a `line_items` relationship to `InvoiceLineItem` (`description`, `quantity`, `unit`, `unit_rate`, `amount`, `wbs_id`, `cost_category`). `FinanceService.create_invoice(InvoiceCreate, user_id)` creates the invoice and its lines and recomputes the total. Money fields on the finance schemas are validated decimal strings.

Crucially, `finance/__init__.py` has an `on_startup` hook that calls `register_finance_subscribers()`, and `finance/events.py` already demonstrates the pattern this design reuses: subscribe to a cross-module event, open a short-lived session via `app.database.async_session_factory`, mutate finance rows, swallow failures so the upstream transaction is never rolled back. We add one more subscription there.

### 2.6 Schedule module

File: `backend/app/modules/schedule/models.py`. `Activity` has `progress_pct` (string), `boq_position_ids` JSON list, `cost_planned` and `cost_actual` `Numeric(20,4)`, plus a CPM/4D layer. `ScheduleProgressEntry` is the append-only field-progress history rolled up into `Activity.progress_pct`. This is the source for schedule-driven claim completion.

### 2.7 Cost spine (dependency `01-cost-spine`)

File: `backend/app/modules/costmodel/models.py`. `BudgetLine` links a `boq_position_id` and an `activity_id` to `planned_amount`, `committed_amount` ("contracts signed") and `actual_amount` ("invoices paid"). The 01-cost-spine work makes this the single committed/actual ledger. Pay applications feed it: a certified claim is committed-to-actual movement for the contract counterparty, and that is wired through the same event the finance subscriber listens to.

### 2.8 Front end

Files under `frontend/src/features/contracts/`: `ContractsPage.tsx` (tabs Contracts / Progress Claims / Final Accounts, a claim row with submit/approve/certify/reject/mark-paid buttons, a contract detail drawer that already renders the SoV and a retention card), and `api.ts` (typed wrappers for every endpoint above, including `listClaimLines`). There is no per-line claim editor, no approval timeline, and no link from a certified claim to its finance invoice. A `frontend/src/features/finance/FinancePage.tsx` and a `frontend/src/features/approval-routes/` feature exist to deep-link into.

### 2.9 Gap summary

The model and single-module workflow are done. The missing feature is the cross-module pay-application workflow:

1. No approval route bound to a progress claim. The claim FSM is a manual click-through with no multi-approver routing, SLA, or audit chain beyond the event log.
2. Certifying a claim emits `contracts.claim.certified` but nothing in finance listens, so no AR/AP invoice is ever created and the cost spine never sees the certified value.
3. Completion percentages are typed by hand. There is no "pull this period from schedule progress" or "from cost-spine earned value".
4. No claim-line editing surface and no approval timeline on the front end.
5. No region-specific certificate output (AIA G702/G703, DIN, JCT) and no documented extension point for packs.

## 3. Data model changes

The guiding rule is reuse. We add one new table and a small number of columns, all following the repo conventions (ISO `String` dates, `Numeric`/`MoneyType` money, `GUID` ids, `metadata_` JSON for forward-compatible extras).

### 3.1 New table: `oe_contracts_payment_application`

A pay application is a claim that has been promoted into a routed, certifiable, billable document. Rather than overload `ProgressClaim` with routing and invoice bookkeeping, we add a thin satellite that points at the claim. This keeps the proven claim engine untouched and isolates the new cross-module state.

| Column | Type | Notes |
|--------|------|-------|
| `id` | `GUID` PK | base mixin |
| `progress_claim_id` | `GUID` FK `oe_contracts_progress_claim.id` ON DELETE CASCADE, unique | 1:1 with the claim |
| `contract_id` | `GUID` FK `oe_contracts_contract.id` ON DELETE CASCADE, indexed | denormalised for cheap project scoping joins |
| `application_number` | `String(40)` | human number, defaults to claim number |
| `approval_instance_id` | `GUID` nullable | the `oe_approval_routes_instance.id` driving this app; plain UUID, no FK (cross-module, mirrors `counterparty_id` precedent) |
| `approval_status` | `String(24)` default `not_started` | mirror of the instance: `not_started`, `pending`, `approved`, `rejected`, `cancelled` |
| `invoice_id` | `GUID` nullable | the `oe_finance_invoice.id` minted on certification; plain UUID, no FK |
| `source_mode` | `String(24)` default `manual` | how completion was sourced: `manual`, `schedule`, `cost_spine` |
| `period_label` | `String(40)` nullable | e.g. `2026-06` for display and AIA period column |
| `certified_value` | `MoneyType()` default `0` | snapshot of gross at certification, the invoice subtotal source of truth |
| `metadata_` | `JSON` default `{}` | pack-specific fields (AIA stored materials, change-order summary, etc.) |
| `created_at` / `updated_at` | from base mixin | |

Why `MoneyType()` here while `ProgressClaim` uses raw `Numeric(18,4)`: new money columns in this repo standardise on `app.core.db_types.MoneyType`, which is `NUMERIC` on PostgreSQL and `VARCHAR` on the SQLite dev DB while always returning `Decimal` to Python. The contracts table predates that helper; we do not migrate the old columns, but new ones use the standard.

### 3.2 New columns on `oe_contracts_progress_claim_line`

To support sourcing completion from schedule and the cost spine, and to support "stored materials" billing (AIA G703 columns E and F), add:

| Column | Type | Notes |
|--------|------|-------|
| `prior_completed_value` | `MoneyType()` default `0` | work in place from previous applications, for the "previous applications" column and cumulative math |
| `materials_stored_value` | `MoneyType()` default `0` | materials presently stored, billed but not yet incorporated |
| `source_activity_id` | `GUID` nullable | schedule `Activity.id` this line drew its percent from, when `source_mode=schedule` |
| `source_boq_position_id` | `GUID` nullable | BOQ/cost-spine position this line maps to |

These are nullable and default to zero, so the existing `auto-generate` flow and the existing pure calculators keep working unchanged. `compute_progress_claim_total` still keys off `period_completed_value`.

### 3.3 New columns on `oe_contracts_contract`

| Column | Type | Notes |
|--------|------|-------|
| `default_approval_route_id` | `GUID` nullable | preferred `oe_approval_routes_route.id` for this contract's claims; plain UUID, no FK |
| `billing_format` | `String(24)` default `generic` | drives certificate export and pack behavior: `generic`, `aia`, `din`, `jct`, `nec`, `fidic` |

`billing_format` defaults to `generic` so existing contracts behave exactly as today.

### 3.4 Alembic migration outline

One revision, chained off the current head `v3150_file_favorites` (verified by walking `down_revision` links in `backend/alembic/versions`).

File: `backend/alembic/versions/v3151_payment_applications.py`

```python
revision = "v3151_payment_applications"
down_revision = "v3150_file_favorites"

def upgrade():
    op.create_table(
        "oe_contracts_payment_application",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("progress_claim_id", GUID(), sa.ForeignKey(
            "oe_contracts_progress_claim.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contract_id", GUID(), sa.ForeignKey(
            "oe_contracts_contract.id", ondelete="CASCADE"), nullable=False),
        sa.Column("application_number", sa.String(40), nullable=False, server_default=""),
        sa.Column("approval_instance_id", GUID(), nullable=True),
        sa.Column("approval_status", sa.String(24), nullable=False, server_default="not_started"),
        sa.Column("invoice_id", GUID(), nullable=True),
        sa.Column("source_mode", sa.String(24), nullable=False, server_default="manual"),
        sa.Column("period_label", sa.String(40), nullable=True),
        sa.Column("certified_value", MoneyType(), nullable=False, server_default="0"),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint(
        "uq_pay_app_claim", "oe_contracts_payment_application", ["progress_claim_id"])
    op.create_index(
        "ix_pay_app_contract", "oe_contracts_payment_application", ["contract_id"])

    with op.batch_alter_table("oe_contracts_progress_claim_line") as b:
        b.add_column(sa.Column("prior_completed_value", MoneyType(), nullable=False, server_default="0"))
        b.add_column(sa.Column("materials_stored_value", MoneyType(), nullable=False, server_default="0"))
        b.add_column(sa.Column("source_activity_id", GUID(), nullable=True))
        b.add_column(sa.Column("source_boq_position_id", GUID(), nullable=True))

    with op.batch_alter_table("oe_contracts_contract") as b:
        b.add_column(sa.Column("default_approval_route_id", GUID(), nullable=True))
        b.add_column(sa.Column("billing_format", sa.String(24), nullable=False, server_default="generic"))

def downgrade():
    # drop columns and table in reverse
```

`batch_alter_table` is required because the dev database is SQLite, which cannot `ALTER TABLE ... ADD COLUMN` with some constraints in place; the repo already uses batch mode in prior revisions. All adds carry `server_default` so existing rows backfill without a data migration, matching the pattern in `v3082_changeorders_approval_chain` and similar.

Module-loader note: the dev path also builds tables for fresh databases through `create_all` driven by imported models, so the new `PaymentApplication` model must be importable when the contracts module loads. It will live in `backend/app/modules/contracts/models.py` alongside its siblings, which the module loader already imports.

## 4. API design

All endpoints are added to the existing `backend/app/modules/contracts/router.py`, so they mount under `/api/v1/contracts` with no new module. Every project-scoped route reuses the existing `_verify_contract_access` and `_verify_claim_access` helpers, which load the row, resolve the owning project and call `verify_project_access`. That keeps the leak policy consistent (404, never 403, for cross-tenant access).

### 4.1 Pay-application lifecycle

| Method | Path | Permission | Body / response |
|--------|------|-----------|-----------------|
| `POST` | `/progress-claims/{claim_id}/payment-application` | `contracts.submit_claim` | Promote a claim into a routed pay application. Body: `{ route_id?: UUID, period_label?: str }`. If `route_id` is omitted, falls back to the contract's `default_approval_route_id`, else the most recent active route for `target_kind="progress_claim"` on the project, else returns the application with `approval_status="not_started"`. Starts an approval instance via `ApprovalRouteService.start_instance`. Returns `PaymentApplicationResponse`. |
| `GET` | `/progress-claims/{claim_id}/payment-application` | `contracts.read` | The pay application plus a denormalised view of the bound approval instance (current step, per-step decisions via `ApprovalRouteService.list_step_states`) and the bound invoice id and status. |
| `GET` | `/contracts/{contract_id}/payment-applications` | `contracts.read` | List pay applications across all claims of a contract, for the register and the AR aging view. Supports `?status=` filter and `offset`/`limit`. |
| `POST` | `/progress-claims/{claim_id}/payment-application/decision` | `contracts.approve_claim` | Convenience proxy that records a decision on the current approval step. Body: `{ step_id: UUID, decision: "approved"|"rejected", comment?: str }`. Delegates to `ApprovalRouteService.submit_decision`. Provided so the contracts UI does not have to address the approval-routes module directly; the approval-routes endpoints remain available for power users. |

The existing manual transition endpoints (`/submit`, `/approve`, `/certify`, `/reject`, `/mark-paid`) stay. When a contract uses routed approval, the route's terminal decision drives the claim FSM through a subscriber (section 5); when it does not, the manual buttons still work. This is backward compatible by construction.

### 4.2 Completion sourcing

| Method | Path | Permission | Behavior |
|--------|------|-----------|----------|
| `POST` | `/progress-claims/{claim_id}/source-from-schedule` | `contracts.update` | For each SoV line that maps to a schedule activity (via `ProgressClaimLine.source_activity_id`, or matched on `Activity.boq_position_ids` overlapping the line's `source_boq_position_id`), read `Activity.progress_pct` and feed it as the completion percent into the existing `generate_lump_sum_claim` path. Sets `source_mode="schedule"`. Refuses non-draft claims (same guard as `auto_generate_claim_lines`). Returns the recomputed claim. |
| `POST` | `/progress-claims/{claim_id}/source-from-cost-spine` | `contracts.update` | Read earned value per `costmodel.BudgetLine` keyed by `source_boq_position_id` and derive completion as earned / planned. Sets `source_mode="cost_spine"`. Same draft guard. |
| `GET` | `/progress-claims/{claim_id}/source-preview?mode=schedule\|cost_spine` | `contracts.read` | Dry run: returns the per-line percent and value that sourcing would write, without persisting. Lets the UI show a diff before the user commits. |

These build on the already-present `auto-generate` machinery; they only change where the completion dict comes from.

### 4.3 Certificate export

| Method | Path | Permission | Behavior |
|--------|------|-----------|----------|
| `GET` | `/progress-claims/{claim_id}/certificate?format=generic\|aia\|din\|jct` | `contracts.read` | Returns a structured certificate payload (JSON) assembled from the claim, its lines, prior applications and retention. `format` defaults to the contract's `billing_format`. The generic format is built in core. Region formats are produced by a registered builder (section 6); if a pack for the requested format is not installed, core returns the generic payload with a `format_fallback` note rather than failing. |

PDF rendering is deferred to a later phase and reuses the existing reporting renderer rather than a new dependency.

### 4.4 Request and response schemas

Added to `backend/app/modules/contracts/schemas.py`, mirroring the existing decimal-as-`Decimal`, dates-as-`str` style:

```python
class PaymentApplicationCreate(BaseModel):
    route_id: UUID | None = None
    period_label: str | None = Field(default=None, max_length=40)

class PaymentApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    id: UUID
    progress_claim_id: UUID
    contract_id: UUID
    application_number: str
    approval_instance_id: UUID | None = None
    approval_status: str
    invoice_id: UUID | None = None
    source_mode: str
    period_label: str | None = None
    certified_value: Decimal
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime

class PaymentApplicationDecision(BaseModel):
    step_id: UUID
    decision: str = Field(pattern=r"^(approved|rejected)$")
    comment: str | None = None

class SourcePreviewLine(BaseModel):
    contract_line_id: UUID
    percent: Decimal
    value: Decimal
```

## 5. Service logic, the connective tissue

This is the point of the feature. The wiring lives in the contracts module so the cross-module knowledge sits next to the claim, and it uses the same detached-event and short-lived-session patterns the finance module already uses.

### 5.1 New file: `backend/app/modules/contracts/events.py`

Mirrors `backend/app/modules/finance/events.py`. Registered from a new `on_startup` block appended to `backend/app/modules/contracts/__init__.py`, which today only registers permissions.

Subscriptions:

1. `approval_routes.instance.completed` and `approval_routes.instance.rejected`. The handler filters on `event.data["target_kind"] == "progress_claim"`, looks up the `PaymentApplication` by `approval_instance_id`, and drives the claim FSM:
   - on completed, transition the claim `submitted -> approved` then `approved -> certified` through `ContractsService.transition_claim` (which already stamps timestamps and emits `contracts.claim.certified`), and set the pay application `approval_status="approved"` and `certified_value` to the claim gross.
   - on rejected, transition the claim to `rejected` and set `approval_status="rejected"`.
   The handler opens its own session via `async_session_factory`, so a failure here never rolls back the approval-routes transaction. This is the bridge from approval routing to the claim lifecycle.

2. `contracts.claim.certified`. This is the money bridge into finance. The handler is registered here in contracts but performs a finance write through `FinanceService`, again on its own session. On certify it:
   - resolves the contract to read `counterparty_type` and `currency`,
   - chooses `invoice_direction`: `receivable` when the contract counterparty is the `client` (we are billing the owner), `payable` when the counterparty is a `subcontractor` (the subcontractor is billing us),
   - builds an `InvoiceCreate` with `amount_subtotal = claim.gross_amount`, `retention_amount = claim.retention_amount`, `currency_code = claim.currency`, one `InvoiceLineItem` per `ProgressClaimLine` (description from the SoV line, `amount = period_completed_value`, `wbs_id`/`cost_category` carried where present), and `metadata_` linking back with `{"source": "progress_claim", "progress_claim_id": ..., "contract_id": ...}`,
   - calls `FinanceService.create_invoice`,
   - writes the new invoice id back onto the `PaymentApplication.invoice_id`.
   Money stays in one currency: a claim is single-currency by construction (`ProgressClaim.currency`), so the invoice inherits it directly with no blending. The repo's rule of never summing mixed currencies is respected because we never sum across claims here; cross-contract rollups continue to use the existing finance FX helpers.

3. `contracts.claim.paid`. Optional in MVP, used to nudge the cost spine: publish or directly update `costmodel.BudgetLine.actual_amount` for the mapped positions. Because 01-cost-spine owns that ledger, the cleaner contract is to let the cost-spine module subscribe to `contracts.claim.paid` itself. This design documents the event and the payload (`contract_id`, `net_due`, `claim_id`) so cost-spine can consume it without a contracts-to-costmodel import. The two modules stay decoupled through the event bus exactly like finance and procurement do today.

### 5.2 New methods on `ContractsService`

- `create_payment_application(claim_id, route_id, period_label, actor_id)`: validates the claim is at least `draft` with lines, resolves the route (explicit, then contract default, then newest active project route for `progress_claim`), starts the approval instance, creates the `PaymentApplication` row, transitions the claim `draft -> submitted` so the routing and the claim status stay in lockstep, and returns the row. If no route resolves, it still creates the application with `approval_status="not_started"` so the manual buttons remain usable.
- `source_completion_from_schedule(claim_id)` and `source_completion_from_cost_spine(claim_id)`: build the `completion` dict and reuse the existing per-type generators, then persist claim lines and roll up totals using the same code path as `auto_generate_claim_lines`. To avoid duplication, `auto_generate_claim_lines` is refactored so its persist-and-rollup tail becomes a private `_apply_generated_result(claim, result, prior_paid)` helper that all three callers share.
- `payment_application_view(claim_id)`: joins the application, the approval instance and step states, and the invoice summary into one response for the detail drawer.

### 5.3 End-to-end flow

```
Quantity surveyor opens an active contract
  -> creates a draft progress claim (existing POST /progress-claims)
  -> sources completion from schedule  (POST /source-from-schedule)
       reads Activity.progress_pct, fills claim lines, rolls up gross/retention/net
  -> creates a payment application       (POST /payment-application)
       ApprovalRouteService.start_instance(target_kind="progress_claim", target_id=claim.id)
       claim: draft -> submitted
Approvers act in the approval-routes UI (or the proxy decision endpoint)
  -> last approval fires approval_routes.instance.completed
       contracts subscriber: claim submitted -> approved -> certified
       certify fires contracts.claim.certified
         finance subscriber: create_invoice(receivable|payable, retention split out)
         pay application: invoice_id set, approval_status=approved
Finance approves and pays the invoice (existing finance flow)
  -> someone marks the claim paid (POST /mark-paid) or finance.invoice.paid is mapped
       contracts.claim.paid fires
         cost-spine subscriber (01-cost-spine): BudgetLine.actual_amount += net
Retention released later by event (existing POST /retention/release)
```

Every arrow above except the four new subscriber and service hops already exists in the codebase. The feature is the wiring, and the wiring follows the proven finance-subscriber pattern.

## 6. Front end

Feature folder: `frontend/src/features/contracts/` (extend), with two new components and additions to `api.ts`. No new top-level route is required; this lives inside the existing Contracts page and its claim drawer.

### 6.1 New components

- `PaymentApplicationDrawer.tsx`: opened from a claim row. Three sections.
  1. SoV completion grid, an editable table over `ProgressClaimLine` rows: scheduled value, previous applications (`prior_completed_value`), this period (`period_completed_value` or percent), materials stored, retention, total earned. Inline-editable for draft claims only, calling `PATCH /progress-claim-lines/{id}`. A "Source from schedule" and "Source from cost spine" button pair calls the preview endpoint, shows the diff, then commits. This fills the missing claim-line editing surface.
  2. Approval timeline, a vertical step list rendered from `payment_application_view` (route step name, approver, decision, timestamp, comment), with an Approve / Reject control on the current step for users holding `contracts.approve_claim`. Reuses the visual language of the existing approval-routes feature.
  3. Billing summary, gross / retention / prior / net with `MoneyDisplay`, the certified-invoice link (deep link into `/finance` filtered to the bound invoice) once `invoice_id` is set, and a "Download certificate" action hitting the certificate endpoint.
- `PaymentApplicationStatusBadge.tsx`: a small mirror of the existing claim status badge for `approval_status`, reused in the claims table.

### 6.2 State and data

React Query, consistent with `ContractsPage.tsx`. New query keys: `['contracts','pay-app',claimId]` and `['contracts','pay-apps',contractId]`. Mutations for create-application, decision, source-from-schedule and source-from-cost-spine invalidate the claim list, the claim lines and the pay-app view. Money rendering uses the existing `MoneyDisplay` and `MultiCurrencyTotal` components; no new currency math on the client.

### 6.3 Surfacing

- The Progress Claims tab gains an approval-status column and a "Pay application" action that opens the new drawer.
- The contract detail drawer's retention card is extended to show released-to-date from the retention-release history already stored in `metadata_`.
- The existing CRM -> Bid -> Contracts -> Variations pipeline banner gains no new node; pay applications are an activity inside Contracts, not a new pipeline stage.

New i18n keys are added under the `contracts.*` namespace with English defaults inline (the established pattern in `ContractsPage.tsx`), so the translation sweep can localise them into all locales automatically.

## 7. Reuse summary

Confirmed in code and built upon, not reinvented:

- Claim and SoV models and the entire claim FSM and pure calculators in `backend/app/modules/contracts/{models,service,repository}.py`.
- The generic approval engine `backend/app/modules/approval_routes/service.py`, extended only by adding the `progress_claim` value to `TARGET_KINDS` (the column is already open `String(64)`).
- `FinanceService.create_invoice` and the `Invoice` / `InvoiceLineItem` models with their existing `retention_amount` and `invoice_direction`.
- The finance subscriber pattern in `backend/app/modules/finance/events.py`, including `async_session_factory` short-lived sessions and failure isolation.
- `app.core.events.event_bus.publish_detached` and `app.core.audit_log.log_activity`.
- `app.core.db_types.MoneyType` for new money columns.
- Schedule `Activity.progress_pct` / `boq_position_ids` and cost-spine `BudgetLine` earned/planned for sourcing.
- Front-end `MoneyDisplay`, `MultiCurrencyTotal`, `WideModal`, `Badge`, the existing contracts `api.ts` wrappers and the approval-routes feature visuals.

## 8. Phasing

The MVP is a complete, no-stub vertical slice: a claim can be promoted to a routed pay application, approved through the real approval engine, and on certification produce a real finance invoice with retention split out, all visible on the front end. Later phases add fidelity.

| Phase | Scope | Effort (days) |
|-------|-------|---------------|
| MVP - core wiring | Migration `v3151` (table + columns). `PaymentApplication` model, schemas, repository. Service: `create_payment_application`, `payment_application_view`, refactor `_apply_generated_result`. New `contracts/events.py` with the approval-completed and claim-certified subscribers and the `on_startup` registration. Endpoints 4.1 plus the certified-to-invoice path. `target_kind="progress_claim"` added. Front end: `PaymentApplicationDrawer` (billing summary + approval timeline + read of lines), status badge, api wrappers. Backend pytest for the FSM-to-invoice bridge and approval-to-claim bridge. | 8 |
| Phase 2 - completion sourcing | `source-from-schedule`, `source-from-cost-spine`, `source-preview` endpoints and service methods. Editable SoV completion grid in the drawer with preview-then-commit. Cost-spine `claim.paid` subscriber contract documented and the schedule mapping (`source_activity_id`, `source_boq_position_id`) populated. Tests for sourcing math against schedule progress and cost-spine earned value. | 5 |
| Phase 3 - retention and stored materials depth | Stored-materials columns surfaced and rolled into gross. Retention ledger view fed by the existing release history. Per-line retention overrides via `RetentionSchedule.accrual_rule`. Honest retention-released-to-date on the contract dashboard. | 4 |
| Phase 4 - certificate export and region packs | Generic certificate JSON builder in core plus the registered-builder extension point. Reuse the reporting renderer for PDF. Reference partner-pack builders: US AIA G702/G703, DACH DIN abschlagsrechnung, UK JCT interim certificate. | 6 |

MVP total to a working cross-module slice: 8 days. Full feature: 23 days.

### Region-neutral core and pack extension points

Core stores `billing_format` and emits a generic certificate. Region behavior is added by packs through three seams, none of which require core changes:

- Certificate builders register against a format key (`aia`, `din`, `jct`, `nec`, `fidic`). The certificate endpoint dispatches by `billing_format` and falls back to generic when a pack is absent. AIA G702 summary and G703 continuation map cleanly onto SoV lines plus the `prior_completed_value` and `materials_stored_value` columns added in 3.2.
- Clause templates already exist as a data catalog in `service.py` (`CONTRACT_CLAUSE_TEMPLATES` covering FIDIC, JCT, NEC, AIA, ConsensusDocs) with payment-clause references; packs extend that dict and map a template to a default `billing_format` and `retention_release_event`.
- Approval routes are data, so a pack ships a seed route for `progress_claim` matching local norms (for example a DACH two-step QS-then-architect certification, or a US owner-architect-contractor chain).

## 9. Risks and edge cases

- Double-firing of the certified-to-invoice subscriber. If certification can be reached both by the approval bridge and a manual `/certify` click, the subscriber could mint two invoices. Mitigation: the subscriber is idempotent on `PaymentApplication.invoice_id` (skip if already set) and on an idempotency token in invoice `metadata_` keyed by `progress_claim_id`, mirroring the finance `Payment.idempotency_key` precedent.
- Subscriber failure isolation. A finance write that throws must not roll back the approval-routes transaction. Mitigation: the contracts subscribers open their own `async_session_factory` session and swallow exceptions at debug level, exactly as `finance/events.py` does. A failed invoice mint leaves the claim certified with `invoice_id` null, which the UI surfaces as "invoice pending" with a retry.
- Test vs production event timing. `publish_detached` is synchronous-shimmed in `tests/conftest.py` but asynchronous in production. Tests assert on captured events; production relies on the loop. The design keeps subscriber effects idempotent so re-delivery or ordering does not corrupt state.
- SQLite row locks. `ApprovalRouteService` uses `with_for_update`, which SQLite ignores; the application-level status-and-ordinal guard is the dev-DB fallback. No change needed, but documented so reviewers do not expect true locking on the dev DB.
- Sourcing mismatch. A SoV line may map to many schedule activities or none. Mitigation: sourcing is additive and preview-first; unmapped lines keep their manual value, and the preview shows exactly which lines change before commit.
- Currency drift. A claim is single-currency. If a contract currency differs from a line's intended currency, the invoice would carry the claim currency. Mitigation: validate at claim creation that the claim currency matches the contract currency (the service already defaults claim currency from the contract), and never blend currencies in any rollup.
- Over-billing past the SoV. Cumulative billed could exceed a line's scheduled value through manual edits. Mitigation: a `boq_quality`-style validation warning when cumulative completed exceeds scheduled, surfaced as a non-blocking flag on the application, consistent with the platform's validation-as-first-class principle.
- Retention release double counting. Already guarded in `release_retention` by deduping on the event key; this design does not change that and reuses it.
- Permission creep. Promoting a claim and recording a decision must stay within existing role gates. Mitigation: reuse `contracts.submit_claim` and `contracts.approve_claim`; the invoice mint runs server-side under the system path, not as the approver, which is acceptable because certification already required MANAGER via the route's terminal step or the manual `contracts.certify_claim` gate.

## 10. Test plan

### Backend (pytest)

Follows the repo pattern in `backend/tests/conftest.py`: the per-session temp SQLite path is set in `DATABASE_URL` and `DATABASE_SYNC_URL` before any `from app...` import, and `publish_detached` is shimmed synchronous so subscriber effects are observable immediately after an awaited service call. New tests live under `backend/tests/modules/test_payment_applications.py` and `backend/tests/integration/`.

- Unit, pure logic: extend `backend/tests/unit/test_contracts.py` style coverage for the refactored `_apply_generated_result` and the schedule and cost-spine sourcing dict builders, asserting exact `Decimal` gross/retention/net against fixtures.
- Bridge 1, approval to claim: start a `progress_claim` instance, submit approving decisions through `ApprovalRouteService.submit_decision`, assert the captured `approval_routes.instance.completed` event drives the claim to `certified` and sets `approval_status="approved"`.
- Bridge 2, certify to invoice: certify a claim and assert exactly one `Invoice` is created with the correct `invoice_direction` (receivable for client, payable for subcontractor), `amount_subtotal == gross`, `retention_amount == claim.retention_amount`, one line per SoV line, and `PaymentApplication.invoice_id` set. Then certify again or re-deliver the event and assert no second invoice (idempotency).
- Money exactness: reuse the `Decimal`-string serialization regression already pinned in `test_contracts_security.py`, extended to `PaymentApplicationResponse.certified_value` and the invoice subtotal.
- RBAC and IDOR: a VIEWER cannot create a pay application or record a decision; a user without project access on the contract gets 404 from every new endpoint (reuse `_verify_claim_access`).
- FSM guards: sourcing and promotion refuse non-draft claims with 409, matching `auto_generate_claim_lines`.

### Front end (vitest)

Co-located under `frontend/src/features/contracts/`.

- `PaymentApplicationDrawer.test.tsx`: renders the billing summary and approval timeline from a mocked `payment_application_view`, shows the invoice deep link only when `invoice_id` is present, gates the Approve/Reject control behind the approver role, and disables line editing for non-draft claims.
- `PaymentApplicationStatusBadge.test.tsx`: maps each `approval_status` to the right variant.
- api wrapper tests asserting the correct paths and query strings for the new endpoints, in the style of the existing contracts api usage.

### Manual browser verification on the :8000 server

Run the app on `localhost:8000` and walk the full slice in a real browser:

1. Open Contracts, pick a project, open an active contract with a Schedule of Values.
2. Create a draft progress claim, open the pay-application drawer, source completion from schedule, confirm the per-line preview diff then commit, and verify gross / retention / net.
3. Promote to a payment application; confirm the approval timeline appears with the route steps.
4. Approve through each step (as the seeded approver roles); confirm the claim flips to certified.
5. Go to Finance and confirm a new receivable invoice exists with the retention split out and one line per SoV line, and that the drawer's invoice deep link lands on it.
6. Mark the claim paid; confirm the contract dashboard paid-to-date and retention-held update.
7. Download the generic certificate; with a region pack installed, switch `billing_format` and confirm the AIA or DIN layout, and that an uninstalled format falls back to generic with a note.

Browser probes against a shared server are run sequentially, never in parallel, per the project's verification guidance.

## 11. File-by-file change list

Backend:

- `backend/alembic/versions/v3151_payment_applications.py` (new)
- `backend/app/modules/contracts/models.py` (add `PaymentApplication`, add columns to `ProgressClaimLine` and `Contract`)
- `backend/app/modules/contracts/schemas.py` (add pay-application and source-preview schemas)
- `backend/app/modules/contracts/repository.py` (add `PaymentApplicationRepository`)
- `backend/app/modules/contracts/service.py` (add pay-app methods, refactor `_apply_generated_result`, add sourcing methods, certificate builders dispatch)
- `backend/app/modules/contracts/router.py` (add endpoints in section 4)
- `backend/app/modules/contracts/events.py` (new, the two subscribers)
- `backend/app/modules/contracts/__init__.py` (add `on_startup` subscriber registration alongside permissions)
- `backend/app/modules/contracts/permissions.py` (no new keys needed; reuse existing claim keys)
- `backend/app/modules/approval_routes/models.py` (add `"progress_claim"` to `TARGET_KINDS`)

Front end:

- `frontend/src/features/contracts/PaymentApplicationDrawer.tsx` (new)
- `frontend/src/features/contracts/PaymentApplicationStatusBadge.tsx` (new)
- `frontend/src/features/contracts/api.ts` (add wrappers)
- `frontend/src/features/contracts/ContractsPage.tsx` (claims table column + drawer launch)

Tests:

- `backend/tests/modules/test_payment_applications.py` (new)
- `backend/tests/integration/test_payment_applications_flow.py` (new)
- `frontend/src/features/contracts/PaymentApplicationDrawer.test.tsx` (new)
- `frontend/src/features/contracts/PaymentApplicationStatusBadge.test.tsx` (new)

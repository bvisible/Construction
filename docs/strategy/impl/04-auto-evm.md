# 04 - Auto-derived Earned Value (EVM)

Status: design, ready for build
Owner: DataDrivenConstruction
Depends on: 01-cost-spine, 03-budget-cockpit
Feature key: auto-evm

## 1. Problem and goal

Earned Value across the platform is split over three modules and almost every number is hand-entered or derived from a thin proxy. The goal of this feature is one scheduled, on-demand job that computes PV, EV and AC straight from the live schedule, field progress, finance budget, paid invoices and contract claims, writes a real period snapshot, and feeds that snapshot into the EVM and EAC surfaces that already exist. The connective tissue between schedule, progress, finance, contracts, costmodel and full_evm is the entire point of the feature.

### What exists today and whether it is hand-entered

I read the code before designing. Here is the ground truth.

| Surface | File | How PV/EV/AC are produced today | Persisted |
| --- | --- | --- | --- |
| Finance EVM snapshot | `backend/app/modules/finance/service.py` `create_evm_snapshot` (lines 852-984) | Mostly hand-entered. If the client posts a value of exactly "0", it is replaced by a budget-derived figure: `BAC = revised or original budget`, `AC = budget actuals`, `PV = BAC` (no time phasing), `EV = committed if > 0 else AC` (a crude proxy, not progress-based). | Yes, `oe_finance_evm_snapshot` |
| Full EVM forecast | `backend/app/modules/full_evm/service.py` `calculate_forecast` (lines 67-167) | Reads the latest finance snapshot and computes ETC/EAC/VAC/TCPI. It inherits whatever PV/EV/AC the snapshot carried. So it is "auto" relative to a snapshot, but the snapshot itself is hand-entered. | Yes, `oe_evm_forecast` |
| 5D Cost Model EVM | `backend/app/modules/costmodel/service.py` `calculate_evm` (lines 627-842) | Computed live on every GET, never stored. `BAC = sum(budget_line.planned)`, `AC = sum(budget_line.actual)`, `EV = BAC * weighted activity progress`, `PV = BAC * time_elapsed%` with a 1% floor and SPI clamp. The docstring itself flags PV as an approximation and asks for a proper time-phased PV (Option A, v1.4). | No |
| 4D schedule dashboard | `backend/app/modules/schedule/service_4d.py` `ScheduleDashboardService.dashboard` (lines 550-665) | Computed live, never stored. Uses `Activity.cost_planned` (PV) and `Activity.cost_actual` (AC) when the schedule is cost-loaded, `EV = cost_planned * progress`. Returns `None` for SPI/CPI when there is no cost data. This is the closest thing to a correct, schedule-driven EV. | No |

So there are three live calculators, two snapshot stores, no scheduled job, and PV is a time-elapsed proxy everywhere except the 4D dashboard. Nobody reconciles the schedule signal with the finance budget and contract claims into one authoritative period snapshot. That is the gap.

### A naming clarification that matters

The `eac` module (`backend/app/modules/eac`, frontend `frontend/src/features/eac`) is NOT financial Estimate At Completion. It is the Element Attribute Calculation / compliance rule engine (rulesets, rules with `definition_json`, runs, parameter aliases, the block editor with `AttributeBlock`/`ConstraintBlock`/`LogicBlock`). It already integrates with schedule through `EacScheduleLink` (`backend/app/modules/schedule/models.py` line 387) to resolve BIM elements per task. Financial EAC lives in `full_evm` (`EVMForecast.eac`) and in the finance snapshot (`EVMSnapshot.eac`). This design treats `full_evm` and `finance` as the financial EAC surfaces to feed, and it reuses the `eac` rule engine only as an optional EV measurement method (rules of credit), never as the place where money EAC is stored.

## 2. Design summary

Add one small module, `oe_auto_evm`, that owns a single computation: build a period EVM snapshot for a project by composing the existing modules, then write it through the existing finance snapshot store so every downstream surface (full_evm forecast, costmodel S-curve, dashboards) lights up without change.

The new module is a composer, not a new data silo. It introduces exactly one new table, an audit/provenance row that records how each derived snapshot was built (which sources contributed, which EV method was used, what was missing). The actual PV/EV/AC numbers land in the existing `oe_finance_evm_snapshot` so we do not fork yet another EVM store.

Region-specific behavior (US AIA G702/G703 schedule of values, DACH DIN 276 cost-group phasing, UK JCT interim valuations) is expressed as pluggable EV measurement methods and PV phasing strategies selected by config, with partner-pack override points. The region-neutral core ships first and works end to end.

## 3. Data model

### 3.1 Reuse, do not duplicate

Confirmed in code, built on as-is:

- `oe_finance_evm_snapshot` (`finance/models.py` `EVMSnapshot`): the authoritative period snapshot store. Has `project_id`, `snapshot_date` (String ISO), `bac/pv/ev/ac/sv/cv/spi/cpi/eac/vac/etc/tcpi` (all `String(50)` decimals-as-string), and a `metadata` JSON. The auto job writes here.
- `oe_finance_budget` (`finance/models.py` `ProjectBudget`): `original_budget/revised_budget/committed/actual/forecast_final` as `MoneyType`, with `wbs_id` and `category`. Source of BAC and one AC candidate.
- `oe_costmodel_budget_line` (`costmodel/models.py` `BudgetLine`): per-position / per-activity `planned/committed/actual/forecast` with `boq_position_id`, `activity_id`, `category`, `period_start/period_end`. Richer than finance budget for time-phasing and activity linkage. Primary source of time-phased PV.
- `oe_schedule_activity` (`schedule/models.py` `Activity`): `progress_pct`, `start_date/end_date`, `duration_days`, `cost_planned`/`cost_actual` (`Numeric(20,4)`), `boq_position_ids` JSON, `is_critical`. Source of schedule progress and a cost-loaded PV/AC path.
- `oe_schedule_progress_entry` (`schedule/models.py` `ScheduleProgressEntry`): append-only field progress, the source of truth for progress history. Source of EV-by-progress and the "as of" reading.
- `oe_schedule_baseline` (`schedule/models.py` `ScheduleBaseline`): baseline snapshot JSON, the proper basis for time-phased PV against the plan rather than against elapsed calendar time.
- `oe_contracts_progress_claim` and `oe_contracts_progress_claim_line` (`contracts/models.py`): certified work in place. `compute_sov_status` (`contracts/service.py` line 1652) already aggregates scheduled vs billed vs earned vs paid per SOV line. Source of contract-certified EV and a strong AC candidate (paid claims).
- `oe_finance_invoice` + `oe_finance_payment`: paid invoices, the cash-based AC candidate. `pay_invoice` already buckets actuals into `ProjectBudget.actual`.
- `oe_evm_forecast` (`full_evm/models.py` `EVMForecast`): the forecast store the auto snapshot feeds via the existing `calculate_forecast`.

### 3.2 New table: oe_auto_evm_derivation

One new table. It is provenance and configuration, not a second EVM number store. It records, per derivation run, how the snapshot was assembled so the UI can show "where did this number come from" and so re-runs are auditable.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `GUID()` PK | from `Base` (UUID on PG, String(36) on SQLite) |
| `project_id` | `GUID()` indexed, not null | project scope |
| `snapshot_id` | `GUID()` nullable | FK-style link to the `oe_finance_evm_snapshot` row this run produced (plain GUID, no cross-module FK, resolved at service layer, mirrors the `counterparty_id` pattern in contracts) |
| `as_of_date` | `String(40)` not null | ISO date the derivation measured to |
| `period` | `String(40)` not null | YYYY-MM bucket, matches costmodel snapshot period convention |
| `ev_method` | `String(40)` not null, default `"schedule_progress"` | one of the registered EV methods (see 5.3) |
| `pv_method` | `String(40)` not null, default `"budget_time_phased"` | one of the registered PV strategies |
| `ac_source` | `String(40)` not null, default `"budget_actual"` | `budget_actual` / `paid_invoices` / `contract_claims_paid` / `ledger` |
| `bac` `pv` `ev` `ac` | `String(50)` not null, default `"0"` | the derived figures, mirrored here for the audit trail (the live copy lives on the finance snapshot) |
| `currency_code` | `String(3)` not null, default `""` | project base currency, never hardcoded |
| `inputs_json` | `JSON` not null, default `{}` | structured provenance: counts and subtotals per source (activities scanned, progress entries used, claims summed, invoices summed, missing fx codes, clamps applied) |
| `warnings_json` | `JSON` not null, default `[]` | list of human-readable degradations (no schedule, no baseline, mixed currency, missing fx rate, PV clamped) |
| `status` | `String(20)` not null, default `"ok"` | `ok` / `partial` / `no_data` |
| `triggered_by` | `String(20)` not null, default `"manual"` | `manual` / `scheduled` / `event` |
| `created_by` | `String(36)` nullable | actor user id |
| `metadata_` | `JSON` mapped to column `metadata`, default `{}` | extension point, mirrors every other model |

Indexes: `ix_auto_evm_derivation_project` on `project_id`; composite `ix_auto_evm_derivation_project_period` on `(project_id, period)` for "latest derivation for this month" lookups.

No unique constraint on `(project_id, period)`: re-deriving the same month is allowed and produces a new audit row, while the finance snapshot it writes is upserted (see 5.4). This keeps the audit history append-only, matching the platform pattern for `ScheduleProgressEntry` and the ledger.

This table follows the conventions in `.claude/CLAUDE.md` and the codebase: UUID via `GUID`, money and dates as strings, JSON via portable `sqlalchemy.JSON`, `metadata_` mapped to `metadata`.

### 3.3 No schema change to existing tables

The auto job writes only fields that already exist on `EVMSnapshot`. It stamps provenance into the existing `EVMSnapshot.metadata` JSON (keys: `source="auto_evm"`, `derivation_id`, `ev_method`, `pv_method`, `ac_source`) so any reader can tell an auto snapshot from a manual one without a new column. The existing `create_evm_snapshot` already writes a `metadata` dict, so this is additive.

### 3.4 Alembic migration outline

One revision, additive only, safe on both SQLite dev DBs and PostgreSQL.

```
revision: vXXXX_auto_evm_init
down_revision: <current head at build time>

upgrade():
    op.create_table(
        "oe_auto_evm_derivation",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("project_id", GUID(), nullable=False),
        sa.Column("snapshot_id", GUID(), nullable=True),
        sa.Column("as_of_date", sa.String(40), nullable=False),
        sa.Column("period", sa.String(40), nullable=False),
        sa.Column("ev_method", sa.String(40), nullable=False, server_default="schedule_progress"),
        sa.Column("pv_method", sa.String(40), nullable=False, server_default="budget_time_phased"),
        sa.Column("ac_source", sa.String(40), nullable=False, server_default="budget_actual"),
        sa.Column("bac", sa.String(50), nullable=False, server_default="0"),
        sa.Column("pv", sa.String(50), nullable=False, server_default="0"),
        sa.Column("ev", sa.String(50), nullable=False, server_default="0"),
        sa.Column("ac", sa.String(50), nullable=False, server_default="0"),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default=""),
        sa.Column("inputs_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("warnings_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(20), nullable=False, server_default="ok"),
        sa.Column("triggered_by", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_auto_evm_derivation_project", "oe_auto_evm_derivation", ["project_id"])
    op.create_index("ix_auto_evm_derivation_project_period", "oe_auto_evm_derivation", ["project_id", "period"])

downgrade():
    op.drop_index("ix_auto_evm_derivation_project_period", table_name="oe_auto_evm_derivation")
    op.drop_index("ix_auto_evm_derivation_project", table_name="oe_auto_evm_derivation")
    op.drop_table("oe_auto_evm_derivation")
```

The `created_at`/`updated_at` columns match the timestamp mixin every other table in `Base` gets. The migration declares no foreign keys to other modules' tables, consistent with the contracts and EVM models, so it cannot fail on table ordering during a fresh `create_all` in tests.

## 4. API

New module `oe_auto_evm`, auto-mounted by the loader at `/api/v1/auto-evm` (kebab of `oe_auto_evm`, confirmed by the convention in `module_loader.py` line 207). All endpoints are project-scoped and call `verify_project_access` from `app/dependencies.py`, the same IDOR guard the costmodel router uses.

| Method | Path | Body | Response | Permission |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/auto-evm/projects/{project_id}/derive/` | `DeriveRequest` | `DerivationResponse` | `auto_evm.create` |
| GET | `/api/v1/auto-evm/projects/{project_id}/preview/` | query: `as_of_date`, `ev_method`, `pv_method`, `ac_source` | `DerivationPreviewResponse` | `auto_evm.read` |
| GET | `/api/v1/auto-evm/projects/{project_id}/derivations/` | query: `limit`, `offset` | `DerivationListResponse` | `auto_evm.read` |
| GET | `/api/v1/auto-evm/projects/{project_id}/config/` | - | `AutoEvmConfigResponse` | `auto_evm.read` |
| PUT | `/api/v1/auto-evm/projects/{project_id}/config/` | `AutoEvmConfigUpdate` | `AutoEvmConfigResponse` | `auto_evm.manage` |
| GET | `/api/v1/auto-evm/methods/` | - | `MethodCatalogResponse` | `auto_evm.read` |

### Request and response shapes

`DeriveRequest`:
```
{
  "as_of_date": "2026-06-01",        # optional, defaults to today
  "ev_method": "schedule_progress",   # optional, defaults to project config
  "pv_method": "budget_time_phased",  # optional
  "ac_source": "budget_actual",       # optional
  "persist": true                      # write a finance snapshot, default true
}
```

`DerivationResponse` and the preview share a body (`persist=false` is exactly the preview path):
```
{
  "derivation_id": "uuid|null",       # null on preview
  "snapshot_id": "uuid|null",         # the oe_finance_evm_snapshot row, null on preview
  "project_id": "uuid",
  "as_of_date": "2026-06-01",
  "period": "2026-06",
  "bac": "1850000.00",
  "pv": "1100000.00",
  "ev": "980000.00",
  "ac": "1020000.00",
  "sv": "-120000.00",
  "cv": "-40000.00",
  "spi": "0.8909",
  "cpi": "0.9608",
  "eac": "1925400.00",
  "vac": "-75400.00",
  "etc": "905400.00",
  "tcpi": "1.0480",
  "currency": "EUR",
  "ev_method": "schedule_progress",
  "pv_method": "budget_time_phased",
  "ac_source": "budget_actual",
  "status": "ok",
  "warnings": ["No active baseline; PV phased from budget line periods."],
  "inputs": {
    "activities_scanned": 142,
    "progress_entries_used": 142,
    "budget_lines": 64,
    "claims_summed": 0,
    "invoices_summed": 0,
    "missing_fx_rates": []
  },
  "spi_capped": false
}
```

`AutoEvmConfigResponse` / `AutoEvmConfigUpdate` carry the per-project defaults persisted in `ProjectConfig`-style storage (see 5.5): `ev_method`, `pv_method`, `ac_source`, `auto_schedule_enabled` (bool), `auto_schedule_cron` (string, e.g. monthly), `region_pack` (string, e.g. `us_aia`, `dach_din`, `uk_jct`, or empty for neutral).

`MethodCatalogResponse` returns the registered methods with id, display name, and a one-line description, so the frontend can render the method picker without hardcoding the list. Region packs contribute extra entries here at startup.

### RBAC

New permissions registered by the module's `permissions.py`, mirroring `full_evm/permissions.py`:

```
auto_evm.read    -> Role.VIEWER
auto_evm.create  -> Role.EDITOR
auto_evm.manage  -> Role.MANAGER
```

`auto_evm.create` is the bar for running a derivation and writing a snapshot, consistent with `costmodel.write` and `full_evm.create` already gating snapshot creation. `auto_evm.manage` gates changing the per-project method config and the scheduled-run toggle, which is a project administration action. Registration happens in the module `on_startup` hook the same way the other modules register theirs (the loader calls the manifest lifecycle, and the MEMORY notes confirm modules must register permissions on startup, e.g. the moc/ncr fix `976bdf57f`).

### Project scoping

Every endpoint takes `project_id` in the path, calls `await verify_project_access(project_id, user_id, session)` before doing any work, and the service only ever queries with `where(... project_id == project_id)`. There is no cross-project list endpoint, matching the full_evm router's deliberate refusal to enumerate across tenants.

## 5. Service logic, the connective tissue

This is the core of the feature. The service composes the named modules. It lives in `backend/app/modules/auto_evm/service.py` as `AutoEvmService(session)` with a repository `AutoEvmRepository(session)` for the derivation table, following the module convention (models, schemas, repository, service, router, tests).

### 5.1 The flow, end to end

`derive(project_id, as_of_date, ev_method, pv_method, ac_source, persist, actor_id)`:

1. Resolve project base currency and `fx_rates` once. Reuse the exact helper shape used across the codebase: `ProjectRepository.get_by_id`, then `_project_fx_context` (costmodel repository line 243) or `_project_fx_map` (finance service line 59). All cross-currency math goes through `_amount_in_base` / `_convert_to_base`, never blends currencies, and records any missing fx code into warnings. This honours the money rule in MEMORY (convert within project via fx_rates, never blend).

2. Compute BAC. Primary source is the costmodel budget lines: `CostModelService.budget_repo.aggregate_by_project(project_id)["total_planned"]`, already fx-converted. Fallback to finance `ProjectBudget` revised-or-original via `BudgetRepository.aggregate_for_dashboard` when costmodel has no lines. This is the same precedence finance already uses internally.

3. Compute PV via the selected PV strategy (5.2). Region-neutral default `budget_time_phased`.

4. Compute EV via the selected EV method (5.3). Region-neutral default `schedule_progress`.

5. Compute AC via the selected AC source (5.4). Region-neutral default `budget_actual`, with `paid_invoices` and `contract_claims_paid` as alternatives.

6. Derive indices and forecasts with the same formulas finance already uses (`create_evm_snapshot`, lines 920-955): SV=EV-PV, CV=EV-AC, SPI=EV/PV, CPI=EV/AC, EAC=AC+(BAC-EV)/CPI, VAC=BAC-EAC, ETC=max(EAC-AC,0), TCPI=(BAC-EV)/(BAC-AC) with the at-or-over-budget clamp. We reuse these by extracting them into a small pure helper (see 6, Phase 1) so the three calculators stop drifting.

7. Build the provenance dict and the warnings list as we go.

8. If `persist`, write the snapshot and the derivation row atomically (5.6), then trigger the forecast refresh (5.7). If not, return the computed numbers as a preview.

### 5.2 PV strategies (planned value)

Registered strategies, selected by `pv_method`:

- `budget_time_phased` (neutral default): spread each `BudgetLine.planned_amount` across its `[period_start, period_end]` months exactly the way `CostModelService.generate_cash_flow_from_schedule` already does (`_month_range`, even split, costmodel service line 1085), then sum the cumulative planned up to `as_of_date`. Lines without periods are treated as fully planned by `as_of_date` (or pushed to an unscheduled bucket excluded from time-phasing, recorded as a warning). This replaces the `BAC * time_elapsed%` proxy with a real time-phased baseline, which is the Option A the costmodel docstring asks for.
- `baseline_phased`: if an active `ScheduleBaseline` exists, phase PV from the baselined activity `cost_planned` and baselined dates, summing the planned value of activities whose baseline finish is on or before `as_of_date` plus the prorated in-progress portion. This is the most correct PV and matches the per-day logic already in `ScheduleDashboardService._build_s_curve` (service_4d line 667), which we factor into a shared function.
- `activity_cost_loaded`: when the schedule is cost-loaded (`Activity.cost_planned` populated), phase straight off activity planned cost and dates without needing budget-line periods.

If the requested strategy has no data (no baseline, no periods, no cost loading), the service falls back in the order baseline -> budget_time_phased -> `BAC * elapsed%` (the legacy proxy, clamped, flagged `spi_capped=true`) and records the downgrade in warnings. The legacy proxy stays only as the last resort so the endpoint never 500s on a thin project.

### 5.3 EV methods (earned value, rules of credit)

Registered methods, selected by `ev_method`:

- `schedule_progress` (neutral default): EV = sum over activities of `weight * progress_fraction`, where weight is the activity's planned value. Weight precedence: the activity's linked budget-line planned (the `activity_budget` map costmodel already builds, service line 724), else `Activity.cost_planned`, else the BOQ-position planned via `Activity.boq_position_ids`. Progress comes from the latest `ScheduleProgressEntry` rolled onto `Activity.progress_pct` by `ScheduleProgressService`. This binds schedule + progress + budget together.
- `contract_certified`: EV = certified work in place from contracts. Reuse `compute_sov_status` (contracts service line 1652), summing `earned` (cumulative completed value across submitted/approved/certified/paid claims) across the project's contracts, fx-converted. This is the owner-facing EV used in AIA and JCT valuations.
- `boq_progress`: EV = sum over BOQ positions of `position_total * position_progress`, for projects that track completion at the BOQ level rather than the schedule level. Uses `boq_position_ids` to bridge activities to positions where available.
- `weighted_blend`: a configurable blend (e.g. 60% schedule, 40% contract-certified) for organisations that reconcile the two. The blend weights live in the project config JSON.

Every method returns both the EV total and a per-source breakdown for the provenance dict.

### 5.4 AC sources (actual cost)

Selected by `ac_source`:

- `budget_actual` (neutral default): `aggregate_by_project["total_actual"]` from costmodel budget lines, which is already kept up to date because `FinanceService.pay_invoice` buckets paid invoices into `ProjectBudget.actual` and the costmodel budget lines mirror the same actuals workflow.
- `paid_invoices`: sum of `Payment.amount` for paid invoices in the project, fx-converted, the cash-based truth. Uses `PaymentRepository.aggregate_by_currency`.
- `contract_claims_paid`: sum of `net_paid` from `compute_sov_status` totals, the contract cash-out view.
- `ledger`: sum of debit postings on cost accounts from `oe_finance_ledger` for projects using the double-entry ledger.

### 5.5 Per-project configuration

Method defaults and the schedule toggle persist per project. To avoid a second config table, store them under a namespaced key in the project metadata or the existing settings store the codebase already uses for project config (the `ProjectConfig` concept in CLAUDE.md and the `Project.metadata`/settings JSON). The config endpoints read and write `project.metadata["auto_evm"] = {ev_method, pv_method, ac_source, auto_schedule_enabled, auto_schedule_cron, region_pack, blend_weights}`. This keeps the feature single-table and avoids migration churn on the projects table. The `region_pack` value selects which partner-pack methods are preferred.

### 5.6 Persisting the snapshot, atomically

Persistence reuses the finance store rather than forking a new one:

1. Within one transaction (the request session, which auto-commits via `get_session`), compute the figures.
2. Upsert the finance snapshot for `(project_id, period)`: if a `oe_finance_evm_snapshot` row exists for the same `snapshot_date` derived from `as_of_date`, update its bac/pv/ev/ac and recompute indices through the shared helper; else insert. We do not call `FinanceService.create_evm_snapshot` directly because that method's zero-replacement heuristic would re-derive from its own crude proxy. Instead the auto service computes the authoritative numbers and writes them with the indices already final, stamping `metadata.source="auto_evm"`. The finance snapshot stays the single read surface for full_evm and the dashboards.
3. Insert the `oe_auto_evm_derivation` row with `snapshot_id` pointing at the snapshot, the full provenance, and the warnings.
4. Flush. The session commit at request end makes both rows durable together. On any exception the `get_session` dependency rolls both back.

Using a SAVEPOINT (`session.begin_nested`) around the two inserts, mirroring `FinanceService.create_ledger_transaction` (finance service line 1151), guarantees the snapshot and its audit row never land half-written.

### 5.7 Feeding the existing EVM and EAC surfaces

This is where the modules connect downstream:

- full_evm: after writing the snapshot, call `EVMService(session).calculate_forecast(project_id, forecast_method=config_method)` (full_evm service line 67). It reads the latest finance snapshot (now our auto one) and writes an `oe_evm_forecast` row with ETC/EAC/VAC/TCPI and a confidence band. The full_evm `/s-curve-data/` endpoint then returns auto snapshots plus auto forecasts with zero changes.
- costmodel: the costmodel S-curve already plots finance-independent CostSnapshot rows. To keep the 5D surface coherent, the auto job optionally writes a matching `CostSnapshot` for the period via `CostModelService.create_snapshot` (or updates it, respecting the `(project_id, period)` unique guard added in v3108). This is gated by a config flag `mirror_costmodel` (default true) so the 5D page and the finance EVM agree.
- Events: publish `auto_evm.derived` on the event bus (`event_bus.publish_detached`, the pattern in costmodel/finance services) with `{project_id, period, snapshot_id, derivation_id, status}`. The notifications and dashboard modules already subscribe to `costmodel.snapshot.created`-style events, so an alert on a critical SPI/CPI is a subscriber, not new core code.

The result: PV/EV/AC are computed once, authoritatively, from schedule + progress + finance + contracts, stored in the existing snapshot, and every existing EVM/EAC/S-curve surface reads it unchanged.

### 5.8 Scheduled derivation

Phase 2 adds an opt-in scheduled run. The codebase already runs background work and exposes a scheduling skill; for the backend we register a lightweight periodic task that, for each project with `auto_schedule_enabled`, calls `derive(..., triggered_by="scheduled", persist=true)` once per period. The job is idempotent because of the period upsert in 5.6, so a double fire just rewrites the same snapshot. No new infrastructure is required for the MVP, which is manual/on-demand only.

## 6. Phasing

Region-neutral core first, fully working with no stubs, then fidelity.

### Phase 1 - Neutral core, end to end (MVP)

Scope: new `oe_auto_evm` module (manifest, models, schemas, repository, service, router, permissions, tests). One alembic migration for `oe_auto_evm_derivation`. Extract the shared EVM-formula helper (`backend/app/modules/finance/evm_math.py` or `app/core/evm.py`) and use it from the auto service; leave the existing finance/costmodel calculators calling it too so they stop drifting. Implement `pv_method=budget_time_phased`, `ev_method=schedule_progress`, `ac_source=budget_actual`, with the documented fallbacks. Implement POST derive (persist), GET preview, GET derivations, and the method catalogue. Wire the finance-snapshot upsert and the full_evm forecast refresh. Frontend: the Auto-EVM panel on the cost model page (7) calling preview and derive, plus a provenance drawer. This phase delivers a real auto snapshot from a thin or rich project and lights up the existing full_evm and costmodel surfaces.

Effort: 6 days.

### Phase 2 - Higher-fidelity PV/EV/AC and scheduling

Scope: `pv_method=baseline_phased` and `activity_cost_loaded` (factor the per-day S-curve out of `service_4d` into the shared function and reuse it). `ev_method=contract_certified` and `boq_progress` (reuse `compute_sov_status`). `ac_source=paid_invoices`, `contract_claims_paid`, `ledger`. Per-project config endpoints and storage. Opt-in scheduled derivation with idempotent period upsert. costmodel snapshot mirroring. Event publish + a notification subscriber for SPI/CPI breaches. Frontend: method picker, config panel, schedule toggle, S-curve overlay of auto snapshots.

Effort: 7 days.

### Phase 3 - Region packs and reconciliation

Scope: partner-pack extension points realised as concrete packs.

- US `us_aia`: EV from G702/G703 schedule of values, mapping contract SOV lines to the AIA continuation sheet, retention per `retention_percent`, EV method `contract_certified` tuned to AIA percent-complete-by-line.
- DACH `dach_din`: PV phasing and EV roll-up by DIN 276 cost group, using the existing DIN classification on positions/budget categories.
- UK `uk_jct`: interim valuation cadence and certified EV per JCT, gross/retention/net mapped from `ProgressClaim`.

Each pack registers extra `ev_method`/`pv_method` entries in the method registry at startup and contributes a `region_pack` config option, exactly the entry-point partner-pack mechanism already in the codebase (`openconstructionerp.partner_packs`). The core does not branch on region; packs plug in.

Effort: 6 days.

### Partner-pack extension points (built in Phase 1, populated later)

- A method registry keyed by id, with `register_ev_method`, `register_pv_strategy`, `register_ac_source`. Core registers the neutral methods; packs register the rest. The `/methods/` endpoint reflects whatever is registered.
- The `region_pack` project-config field selects preferred methods.
- `inputs_json`/`warnings_json` shapes are stable so pack-specific provenance rides along without schema changes.

## 7. Frontend

Feature folder: `frontend/src/features/costmodel` (the existing 5D / EVM home), with a new subtree `auto-evm/`.

Components and screens:

- `auto-evm/AutoEvmPanel.tsx`: a card mounted on `CostModelPage.tsx` next to the existing `EVMDashboard`. Shows the latest auto derivation (period, BAC/PV/EV/AC, SPI/CPI badges reusing `EVMKPIBox` and `PerformanceIndicator`), a "Derive now" button, an "as of" date picker, and the current EV/PV/AC method labels.
- `auto-evm/DerivationProvenanceDrawer.tsx`: opens from a row or the panel, renders `inputs` and `warnings` so a user sees exactly which activities, progress entries, claims and invoices fed the number, and which currencies were missing an fx rate. This is the "auto, but explainable" surface that satisfies the human-confirmed principle.
- `auto-evm/MethodConfig.tsx` (Phase 2): method pickers (fed by `/methods/`), AC source, region pack, and the scheduled-run toggle, gated on `auto_evm.manage`.
- `auto-evm/api.ts`: typed client (`deriveAutoEvm`, `previewAutoEvm`, `listDerivations`, `getConfig`, `putConfig`, `getMethods`) using the shared `apiGet/apiPost/apiPut` from `@/shared/lib/api`, the same pattern as `costModelApi`.

State: React Query, matching the page. Query keys `['auto-evm', 'derivations', projectId]`, `['auto-evm', 'config', projectId]`, `['auto-evm', 'methods']`. The derive mutation invalidates `['costmodel']` (so the existing EVM dashboard, S-curve and snapshots refetch the new numbers) and `['full-evm', projectId]`, plus its own keys. Toasts via `useToastStore` like the rest of the page.

Surfacing to the user: the user opens the project Cost Model page, sees the Auto-EVM panel, clicks Derive now (or it is already populated by the scheduled run), and the existing Earned Value Analysis card, S-curve, and the full_evm forecast all update from one click. A preview mode (the GET) lets them see the numbers and the provenance before they persist a snapshot, which is the confirm-before-write step.

The full_evm S-curve consumer and the finance EVM list need no UI change; they read the snapshots the job writes.

## 8. Reuse, confirmed in code

- `verify_project_access` (`app/dependencies.py` line 411): project IDOR guard, used by every endpoint.
- `RequirePermission` and the permission registry (`app/dependencies.py`, `app/core/permissions.py`): RBAC.
- `EVMSnapshot` store and `create_evm_snapshot` formulas (`finance/service.py` lines 852-984): the snapshot store and the canonical index/forecast math to share.
- `EVMService.calculate_forecast` (`full_evm/service.py` line 67): forecast refresh from the latest snapshot.
- `CostModelService.calculate_evm` and `generate_cash_flow_from_schedule` (`costmodel/service.py` lines 627, 1085): the schedule-progress weighting and the month-spreading logic for time-phased PV.
- `ScheduleDashboardService._build_s_curve` and `_derive_task_status` (`schedule/service_4d.py` lines 667, 306): per-day PV/EV/AC phasing to factor into a shared function for `baseline_phased`.
- `ScheduleProgressService` and `ScheduleProgressEntry` (`schedule/service_4d.py`, `schedule/models.py`): progress source of truth.
- `compute_sov_status` (`contracts/service.py` line 1652): contract certified/billed/paid aggregation for `contract_certified` EV and contract AC.
- Currency helpers: `_project_fx_context`, `_amount_in_base` (`costmodel/repository.py`), `_project_fx_map`, `_convert_to_base` (`finance/service.py`): all cross-currency math, never blending.
- `BudgetRepository.aggregate_for_dashboard`, `BudgetLineRepository.aggregate_by_project/by_category`: fx-aware budget rollups for BAC/AC.
- `event_bus.publish_detached` (`app/core/events.py`): cross-module events.
- Module loader auto-mount and lifecycle (`app/core/module_loader.py`): no manual router wiring in `main.py` needed for the kebab prefix; lifecycle hook registers permissions on startup.

## 9. Risks and edge cases

- Three calculators drifting. Mitigation: extract the EVM index/forecast formulas into one shared helper in Phase 1 and route finance, costmodel and auto_evm through it. This is the single most valuable cleanup the feature buys.
- PV with no baseline and no budget periods. The legacy `BAC * elapsed%` proxy stays as the last-resort fallback with `spi_capped=true` and an explicit warning, so the endpoint always returns something honest rather than failing.
- Double counting EV across schedule and contracts. The `weighted_blend` method is the only place both contribute, and its weights are explicit; the single-source methods never mix. The provenance drawer shows which source produced EV so a user can catch a misconfiguration.
- Mixed currency without fx rates. Every sum goes through `_amount_in_base`, foreign amounts with no rate are kept in their own units (never zeroed) and their codes surface in `warnings.missing_fx_rates` and the `mixed_currency` flag, matching the existing dashboard behavior. Never blend.
- Period upsert vs append-only audit. The finance snapshot is upserted per period so re-runs do not pile up duplicate snapshots (which historically made `get_latest` flap, per the v3108 fix), while the derivation audit row is append-only so history is preserved. Both invariants are intentional.
- TCPI and SPI denominators. Reuse the existing clamps: TCPI undefined when BAC<=AC (return the documented sentinel/None, not a misleading 0), SPI clamped to a sane band when PV is a proxy. These are already solved in finance and costmodel; we inherit them via the shared helper.
- Scheduled run hammering a thin project. The job is idempotent and skips projects with no schedule and no budget (status `no_data`), so an empty project produces one cheap audit row, not an error storm.
- Cross-tenant leakage. No cross-project list, `project_id` in the path on every route, `verify_project_access` before any query, service queries always project-filtered.
- BIM/CAD constraint. EV-by-BIM-element would route through the existing `eac` rule engine and `EacScheduleLink`, which already operate on the DDC cad2data canonical element shape (`bim_element_to_canonical`), not IfcOpenShell or native IFC. No new BIM parsing is introduced. BCF is untouched.

## 10. Test plan

### Backend pytest

This repo's unit tests construct the service with stub repositories (`SimpleNamespace`), as in `tests/unit/test_costmodel_service.py` and `tests/unit/test_full_evm_service.py`. Integration tests set a per-test temp SQLite file and override `get_session`/`get_current_user_id` before standing up a minimal FastAPI app, as in `tests/integration/test_4d_api.py` (the temp-sqlite-before-import isolation pattern). New tests mirror both.

Unit (`tests/unit/test_auto_evm_service.py`), service composed with stub repos:
- `budget_time_phased` PV: lines with periods spread and summed to `as_of_date`, lines without periods handled, cumulative equals BAC when fully past.
- `schedule_progress` EV: weighting precedence (budget-line planned, then `cost_planned`, then BOQ), progress fractions, EV<=BAC.
- `budget_actual` AC and the index/forecast helper: SV/CV/SPI/CPI/EAC/VAC/ETC/TCPI exactly match the finance formulas including the TCPI at-or-over-budget clamp and the SPI proxy clamp.
- Currency: foreign line with a configured fx rate converts, foreign line without a rate stays in its units and lands in `missing_fx_rates`, never blended.
- Fallbacks: no baseline -> budget phasing; no periods -> elapsed proxy with `spi_capped=true` and a warning; empty project -> status `no_data`.
- Shared formula helper has its own table-driven test so all three callers are pinned to one source of truth.

Integration (`tests/integration/test_auto_evm_api.py`), temp sqlite, real session:
- Seed a project, a schedule with activities and progress entries, costmodel budget lines, paid invoices, and a contract with a certified claim.
- POST derive persists exactly one `oe_finance_evm_snapshot` and one `oe_auto_evm_derivation`, the derivation `snapshot_id` matches, and a subsequent full_evm `/forecasts/calculate/` reads the auto snapshot.
- Re-deriving the same period upserts the snapshot (still one snapshot row) and appends a second derivation row.
- GET preview returns numbers without writing anything.
- RBAC: VIEWER can read and preview, EDITOR can derive, MANAGER can change config, a stranger gets 404 from `verify_project_access`.
- `ev_method=contract_certified` returns EV equal to the summed certified claim value from `compute_sov_status`.
- Mixed-currency project surfaces the warning and does not blend.

Run: `cd backend && python -m pytest tests/unit/test_auto_evm_service.py tests/integration/test_auto_evm_api.py -q`. Also run the existing `test_finance_service.py`, `test_costmodel_service.py`, `test_full_evm_service.py`, `test_eac_evm_formulas.py` to prove the shared-helper extraction did not change their results.

### Frontend vitest

- `auto-evm/api.ts`: request shapes and query keys (mock fetch), invalidation targets on the derive mutation include `costmodel` and `full-evm`.
- `AutoEvmPanel.test.tsx`: renders BAC/PV/EV/AC and SPI/CPI from a mocked derivation, the Derive button fires the mutation, the loading and empty states render.
- `DerivationProvenanceDrawer.test.tsx`: renders inputs and warnings, including a missing-fx-rate warning.

Run: `cd frontend && npx vitest run src/features/costmodel/auto-evm`.

### Manual browser verification on the :8000 server

Per the project run pattern, start the local backend with the factory (`python -m uvicorn app.main:create_app --factory ...`) and the frontend dev server, log in with the demo account.

1. Open a seeded project's Cost Model page. Confirm the Auto-EVM panel renders.
2. Click Derive now with the default methods. Confirm the panel fills with BAC/PV/EV/AC and SPI/CPI, and that the existing Earned Value Analysis card and S-curve below update without a manual refresh.
3. Open the provenance drawer and confirm it lists the activities, progress entries and budget lines used.
4. Change `as_of_date` to an earlier month and Preview; confirm PV and EV drop and nothing new is written (derivation count unchanged).
5. Switch `ev_method` to contract-certified on a project that has a certified claim and confirm EV matches the contract SOV earned total.
6. Confirm the full_evm forecast surface and the finance EVM snapshot list now show the auto snapshot and a fresh forecast.
7. Confirm a project with no schedule and no budget returns a clean "no data" state, not an error.

## 11. Module file layout

```
backend/app/modules/auto_evm/
  manifest.py        # name="oe_auto_evm", category="enterprise", depends=["oe_finance","oe_costmodel","oe_schedule","oe_contracts","oe_full_evm"], auto_install=False, enabled=True
  models.py          # AutoEvmDerivation
  schemas.py         # DeriveRequest, DerivationResponse, DerivationPreviewResponse, DerivationListResponse, AutoEvmConfig*, MethodCatalogResponse
  repository.py      # AutoEvmRepository (list/create/get/latest-for-period)
  service.py         # AutoEvmService + method registry + composition flow
  methods.py         # neutral EV methods, PV strategies, AC sources + registry; pack hook
  permissions.py     # register_auto_evm_permissions()
  router.py          # the endpoints in section 4
  tests/             # module-scoped tests if used in addition to tests/unit + tests/integration
```

The manifest declares its dependencies so the loader resolves load order, and `auto_install=False` keeps it an opt-in enterprise module like `oe_full_evm`. The shared EVM math helper lives outside the module (`app/core/evm.py`) so finance, costmodel and auto_evm can all import it without a module-to-module dependency.

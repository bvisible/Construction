# Estimate-to-Budget-to-Procurement Cost Spine

Implementation design. Keystone feature, depends on nothing.

Author: DataDrivenConstruction
Status: design, ready for build
Scope owner module: `backend/app/modules/costmodel` (extended in place)

## 1. Why this exists and what it is

Today the cost-bearing modules each carry their own line concept and link to
each other through loose, unenforced hints. There is no single stable
identifier that estimate, budget, procurement, and contracts all agree on. As
a result you cannot answer "for this scope of work, what did we estimate, what
did we budget, what have we committed on POs, what is contracted, and what have
we paid" without re-deriving the joins by hand each time, and the joins differ
per module.

The cost spine introduces one shared backbone per project: a tree of stable
**control accounts** and, under them, stable **cost lines**. Every cost-bearing
record in BOQ, costmodel budgets, procurement POs, RFQ award output, and
contract schedule-of-values rows carries a foreign key to a cost line. Reading
"the spine" then means reading one set of ids and rolling up the amounts that
each module already stores against them. This is the precondition for pay
applications, the budget cockpit, EVM that ties to real commitments, and 5D.

The design deliberately reuses the existing `costmodel.BudgetLine`, the
existing `boq.Position`, the existing procurement and contract line items, and
the existing event bus and FX helpers. It adds two new tables and a thin set of
linking columns, plus one service that owns the connective logic. It does not
replace any module.

## 2. Verified current state and the gaps

All of the following was read in the codebase.

### What links already exist

| From | To | Mechanism | File and line |
| --- | --- | --- | --- |
| `costmodel.BudgetLine` | `boq.Position` | `boq_position_id` plain `GUID()` column, no FK | `backend/app/modules/costmodel/models.py:82` |
| costmodel budget generation | BOQ positions | `generate_budget_from_boq` reads positions, dedupes on `existing_position_ids` | `backend/app/modules/costmodel/service.py:1000`, `repository.py:372` |
| `costmodel.BudgetLine` | 4D activity | `activity_id` plain `GUID()` column | `backend/app/modules/costmodel/models.py:83` |
| `procurement.PurchaseOrderItem` | scope | `wbs_id` (String 36) and `cost_category` (String 100), free text | `backend/app/modules/procurement/models.py:94` |
| tender award | procurement PO | `tendering.package.awarded` event auto-creates a draft PO, copies `position_id` into PO item `wbs_id` | `backend/app/modules/procurement/events.py:57`, `146` |
| procurement | finance budget | `procurement.po.issued` and `procurement.gr.confirmed` move `finance.ProjectBudget.committed`/`actual`, routed by PO item `wbs_id` | `backend/app/modules/finance/events.py:129`, `162`, `205` |
| `tendering.TenderPackage` | BOQ | `boq_id` nullable FK | `backend/app/modules/tendering/models.py:26` |
| `procurement.MaterialRequisition` | PO | `po_id` FK | `backend/app/modules/procurement/models.py:192` |
| `contracts.ProgressClaimLine` | `contracts.ContractLine` | `contract_line_id` FK | `backend/app/modules/contracts/models.py:396` |

### The gaps that block a single spine

1. **No shared identifier.** Each module names the same scope differently:
   `boq_position_id` (UUID hint), `wbs_id` (free string), `cost_category`
   (free string), contract `scope_section` (free string). Nothing forces them
   to agree, and nothing is queryable as a tree.

2. **Two parallel budget systems.** `costmodel.BudgetLine`
   (`backend/app/modules/costmodel/models.py:67`, string money,
   `boq_position_id`) and `finance.ProjectBudget`
   (`backend/app/modules/finance/models.py:143`, `MoneyType`, keyed on
   `wbs_id` + `category`). Procurement and GR events feed
   `finance.ProjectBudget` only (`finance/events.py:205`), while the 5D
   dashboard and EVM read `costmodel.BudgetLine`
   (`costmodel/service.py:302`, `665`). Committed and actual amounts driven by
   procurement therefore never reach the costmodel budget that the EVM and
   dashboard display. This is the central disconnect.

3. **Contracts has no link to estimate or budget at all.**
   `contracts.ContractLine` (`backend/app/modules/contracts/models.py:116`)
   has `code`, `description`, `scope_section`, but no `boq_position_id` and no
   budget reference. A signed contract value cannot be tied back to the
   estimated scope it covers.

4. **Procurement commitment routing is fragile.** `finance/events.py`
   resolves the budget row by string-matching the PO line `wbs_id`
   (`_resolve_po_wbs`, `_select_budget_row`, line 69 and 95) and falls back to
   "oldest budget for the project". On any project with more than one budget
   row this misroutes commitments.

5. **RFQ bids carry no structured line linkage.** `rfq_bidding.RFQBid`
   (`backend/app/modules/rfq_bidding/models.py:59`) stores a single
   `bid_amount` and a free `metadata_` blob, no per-line scope reference. Award
   to PO conversion only happens through the separate `tendering` module, not
   through `rfq_bidding`.

The spine closes gaps 1, 3, 4, 5 directly with FK columns and one resolver, and
resolves gap 2 by making the costmodel budget the single committed/actual sink
that procurement and contract events feed through the spine.

## 3. Data model

Money is stored as String ISO-style decimal strings exactly as the existing
costmodel and BOQ models do (see the comment at
`backend/app/modules/boq/models.py:110`). Dates and times are String ISO
columns. Primary keys are `GUID()` UUIDs supplied by the shared `Base`
(every existing model relies on `Base` to provide `id`, `created_at`,
`updated_at`; confirmed by the migration column set in
`v3150_file_favorites.py` and by the fact that no module model declares those
columns itself).

### 3.1 New table: `oe_costmodel_control_account`

A node in the project cost-breakdown tree. This is the level that EVM, the
budget cockpit, and pay-app rollups aggregate to. It is region-neutral: it can
mirror a CSI division, a DIN 276 Kostengruppe, an NRM element, or a
company-internal WBS code. The chosen standard is just a label.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `GUID()` PK | from `Base` |
| `project_id` | `GUID()` FK `oe_projects_project.id` ON DELETE CASCADE, indexed | project scope |
| `parent_id` | `GUID()` FK self `oe_costmodel_control_account.id` ON DELETE SET NULL, nullable, indexed | tree, mirrors the self-FK pattern in `boq.Position.parent_id` (`models.py:101`) |
| `code` | `String(80)` not null | human code, e.g. `03.30`, `KG 330`, `2.6.1` |
| `name` | `String(255)` not null | display name |
| `classification_standard` | `String(40)` not null default `""` | `masterformat` / `din276` / `nrm` / `uniformat` / `custom`, label only |
| `status` | `String(40)` not null default `"open"`, indexed | `open` / `locked` / `closed` |
| `sort_order` | `Integer` not null default 0 | ordering within a parent |
| `metadata_` | `JSON` not null default `{}` | column name `metadata`, extension point |

Constraints and indexes:
- `UniqueConstraint(project_id, code)` named `uq_costmodel_ctrl_acct_project_code`.
- `Index(project_id, parent_id)` named `ix_costmodel_ctrl_acct_project_parent` for the tree walk, same shape as `ix_boq_position_boq_parent`.

### 3.2 New table: `oe_costmodel_cost_line`

The atomic spine identifier. This is the id every other module points at. A
cost line is the durable handle for one piece of scope. It can originate from a
BOQ position, but it persists independently so that procurement, contracts, and
budgets keep a stable reference even if the BOQ is revised, re-imported, or a
position is renumbered (recall `boq.Position.ordinal` changes on renumber, see
the note at `boq/models.py:138`).

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `GUID()` PK | the spine id |
| `project_id` | `GUID()` FK `oe_projects_project.id` ON DELETE CASCADE, indexed | project scope |
| `control_account_id` | `GUID()` FK `oe_costmodel_control_account.id` ON DELETE SET NULL, nullable, indexed | which account this rolls up to |
| `code` | `String(80)` not null | stable spine code, auto `CL-XXXXXXXX` when omitted, mirrors `boq.Position.reference_code` auto pattern (`models.py:145`) |
| `description` | `Text` not null default `""` | scope description |
| `unit` | `String(20)` nullable | unit of measure |
| `source` | `String(40)` not null default `"manual"`, indexed | `manual` / `boq` / `import` |
| `boq_position_id` | `GUID()` nullable, indexed | provenance link to the originating position, plain UUID like the existing `BudgetLine.boq_position_id` |
| `boq_id` | `GUID()` nullable, indexed | denormalised owning BOQ for cheap per-BOQ refresh, mirrors `QuantityLink.boq_id` (`boq/models.py:407`) |
| `estimate_quantity` | `String(50)` not null default `"0"` | quantity captured at spine creation |
| `estimate_unit_rate` | `String(50)` not null default `"0"` | unit rate captured at spine creation |
| `estimate_amount` | `String(50)` not null default `"0"` | the estimate baseline this line carries forward |
| `currency` | `String(10)` not null default `""` | inherited from project, never hardcoded EUR, same rule as `BudgetLine.currency` (`costmodel/models.py:97`) |
| `status` | `String(40)` not null default `"active"`, indexed | `active` / `superseded` / `closed` |
| `metadata_` | `JSON` not null default `{}` | extension point |

Constraints and indexes:
- `UniqueConstraint(project_id, code)` named `uq_costmodel_cost_line_project_code`.
- `Index(project_id, control_account_id)` named `ix_costmodel_cost_line_proj_acct`.
- `Index(boq_position_id)` for reverse lookup from a position.

### 3.3 New columns on existing tables (the linkage)

All are nullable so the migration is non-destructive and existing rows stay
valid. None enforce a hard FK across module boundaries, matching the codebase
convention for cross-module references (see the explicit note on
`contracts.Contract.counterparty_id`, `contracts/models.py:52`, and on
`QuantityLink.model_id`, `boq/models.py:413`, both plain UUIDs resolved at the
service layer). The spine resolver validates and resolves at write time.

| Table | New column | Type | Purpose |
| --- | --- | --- | --- |
| `oe_costmodel_budget_line` | `cost_line_id` | `GUID()` nullable, indexed | the budget row's spine line |
| `oe_costmodel_budget_line` | `control_account_id` | `GUID()` nullable, indexed | denormalised account for grouped rollups without a join through cost line |
| `oe_boq_position` | `cost_line_id` | `GUID()` nullable, indexed | the position's spine line (set when the spine is generated from BOQ) |
| `oe_procurement_po_item` | `cost_line_id` | `GUID()` nullable, indexed | which spine line this PO line commits against |
| `oe_procurement_req_item` | `cost_line_id` | `GUID()` nullable, indexed | requisition line scope |
| `oe_contracts_contract_line` | `cost_line_id` | `GUID()` nullable, indexed | which spine line this SoV line is contracted against |
| `oe_rfq_rfq` | `cost_line_ids` | `JSON` not null default `[]` | the spine lines this RFQ solicits (list, since one RFQ covers many lines) |

`boq.Position` already has a free `cost_code_id: String(36)` column
(`boq/models.py:135`) which is unused by current logic. The spine uses the new,
properly indexed `cost_line_id GUID()` rather than overloading that legacy
string column, to avoid type ambiguity. The legacy column is left untouched.

### 3.4 Alembic migration outline

One migration, next in sequence. The latest applied revision is
`v3150_file_favorites` (confirmed by listing `backend/alembic/versions`), so:

```
revision = "v3151_cost_spine"
down_revision = "v3150_file_favorites"
```

The migration follows the idempotent guard pattern proven in
`v3150_file_favorites.py` (helpers `_table_exists`, `_index_exists`, plus a
`_column_exists` helper using `sa.inspect(bind).get_columns(table)`), because a
fresh SQLite install boots the app first and `Base.metadata.create_all` already
creates the new tables and columns, so every `op.create_*` and `op.add_column`
must be guarded to be re-runnable.

`upgrade()` steps, each guarded:
1. `create_table("oe_costmodel_control_account", ...)` with the `id`,
   `created_at`, `updated_at` columns and server defaults exactly as
   `v3150` writes them (`String(36)` id, `DateTime(timezone=True)` with
   `server_default=sa.func.now()`).
2. `create_table("oe_costmodel_cost_line", ...)`.
3. Indexes and unique constraints for both tables.
4. `add_column` for each of the seven linkage columns in 3.3, each wrapped in a
   `_column_exists` guard.
5. Create the supporting single-column indexes on the new linkage columns.

`downgrade()` drops the linkage columns (guarded), then the two tables.
Note for SQLite: `op.drop_column` requires batch mode, so use
`op.batch_alter_table(table) as batch: batch.drop_column(name)` for the
linkage-column drops, consistent with how other SQLite-targeted migrations in
this repo handle column drops.

## 4. API

All new endpoints live on the costmodel router
(`backend/app/modules/costmodel/router.py`), which the module loader mounts at
`/api/v1/costmodel` and at the kebab alias (the loader mounts at
`/api/v1/{kebab_name}` per `module_loader.py:207`; the costmodel directory is
already a single token so both resolve to `/api/v1/costmodel`). Existing
costmodel routes use mixed prefixes such as `/projects/{project_id}/5d/...`,
so the spine routes follow the same `/projects/{project_id}/spine/...` shape
and become `/api/v1/costmodel/projects/{project_id}/spine/...`.

Permissions reuse the existing costmodel permission set (`costmodel.read`,
`costmodel.write`, `costmodel.manage`) registered in
`backend/app/modules/costmodel/permissions.py`. Project scoping uses the
existing `verify_project_access(project_id, user_id, session)` guard from
`app.dependencies` that every costmodel route already calls
(`router.py:164` and throughout).

### 4.1 Control accounts

| Method | Path (under `/api/v1/costmodel`) | Permission | Body / response |
| --- | --- | --- | --- |
| GET | `/projects/{project_id}/spine/accounts/` | `costmodel.read` | response: `list[ControlAccountResponse]`, tree-ordered |
| POST | `/projects/{project_id}/spine/accounts/` | `costmodel.write` | body: `ControlAccountCreate` (code, name, parent_id?, classification_standard?, sort_order?), response 201 `ControlAccountResponse` |
| PATCH | `/spine/accounts/{account_id}` | `costmodel.write` | body: `ControlAccountUpdate`, response `ControlAccountResponse` |
| DELETE | `/spine/accounts/{account_id}` | `costmodel.manage` | 204, refuses if cost lines still reference it (409) |

### 4.2 Cost lines

| Method | Path | Permission | Body / response |
| --- | --- | --- | --- |
| GET | `/projects/{project_id}/spine/lines/` | `costmodel.read` | query `control_account_id?`, `status?`, pagination; response `list[CostLineResponse]` |
| POST | `/projects/{project_id}/spine/lines/` | `costmodel.write` | body `CostLineCreate`, response 201 |
| PATCH | `/spine/lines/{line_id}` | `costmodel.write` | body `CostLineUpdate`, response `CostLineResponse` |
| DELETE | `/spine/lines/{line_id}` | `costmodel.manage` | 204, refuses if any module record still links to it (409 with the linked counts) |
| GET | `/spine/lines/{line_id}/rollup/` | `costmodel.read` | the cross-module rollup for one line, response `CostLineRollupResponse` |

### 4.3 Spine generation and rollup

| Method | Path | Permission | Body / response |
| --- | --- | --- | --- |
| POST | `/projects/{project_id}/spine/generate-from-boq/` | `costmodel.write` | body `{ "boq_id": "<uuid>"? }`. Builds control accounts from BOQ classification, one cost line per costed position, then auto-links matching budget lines. Idempotent. Response `SpineGenerationResult` |
| GET | `/projects/{project_id}/spine/rollup/` | `costmodel.read` | the full project spine with per-line estimate / budget / committed / contracted / actual columns. Response `SpineRollupResponse` |
| POST | `/spine/lines/{line_id}/link/` | `costmodel.write` | attach an existing module record to a cost line. Body `{ "target_type": "po_item" \| "contract_line" \| "budget_line" \| "boq_position" \| "req_item", "target_id": "<uuid>" }`. Response `CostLineRollupResponse` |

### 4.4 Response shapes

`CostLineRollupResponse` (the heart of the spine read, money as Decimal-as-string
in JSON via the existing `_serialise_money` field serializer in
`costmodel/schemas.py:20`):

```
{
  "cost_line_id": "uuid",
  "code": "CL-1A2B3C4D",
  "control_account_id": "uuid|null",
  "description": "...",
  "currency": "USD",
  "estimate_amount": "125000.00",
  "budget_planned": "120000.00",
  "budget_committed": "80000.00",
  "budget_actual": "30000.00",
  "po_committed": "82000.00",
  "contracted_value": "118000.00",
  "claimed_to_date": "28000.00",
  "variance_estimate_vs_budget": "-5000.00",
  "links": {
    "boq_position_ids": ["uuid"],
    "budget_line_ids": ["uuid"],
    "po_item_ids": ["uuid","uuid"],
    "contract_line_ids": ["uuid"],
    "rfq_ids": ["uuid"]
  }
}
```

`SpineRollupResponse` is `{ "currency": "USD", "mixed_currency": false,
"accounts": [ ... ], "lines": [ CostLineRollupResponse ... ],
"totals": { ...same money keys... } }`. The `mixed_currency` flag reuses the
exact pattern already used by the Monte Carlo endpoint
(`costmodel/router.py:552`) so the client can warn when a project mixes
currencies that lack FX rates.

## 5. Service logic, the connective tissue

A new `CostSpineService` in `backend/app/modules/costmodel/service.py` (same
file as `CostModelService`, same module, so it shares the FX helpers and repos).
A new `CostSpineRepository` and the two new repository classes for control
accounts and cost lines go in `backend/app/modules/costmodel/repository.py`,
beside the existing `BudgetLineRepository`.

### 5.1 Generate the spine from BOQ

`generate_from_boq(project_id, boq_id)`:
1. Resolve `boq_id` (or pick the default BOQ via the existing
   `pick_default_boq`, `service.py:982`).
2. Load positions through the existing `PositionRepository.list_for_boq`
   (already used at `service.py:1024`).
3. Build the control-account tree from each position's `classification` JSON
   (the position already stores `classification: {din276, nrm, masterformat}`,
   `boq/models.py:117`). For each distinct classification code, upsert a
   `ControlAccount` keyed on `(project_id, code)`. Region-neutral: the standard
   key chosen is recorded in `classification_standard`, defaulting to whatever
   keys are present.
4. For each costed position (skip section headers, those have empty `unit`,
   same filter as `get_variance`, `service.py:1227`), upsert a `CostLine` keyed
   on `(project_id, code)` where code defaults from the position
   `reference_code` or an auto `CL-XXXXXXXX`. Capture `estimate_quantity`,
   `estimate_unit_rate`, `estimate_amount` from the position, set
   `boq_position_id`, `boq_id`, `control_account_id`, and inherit project
   currency through the existing `_get_project_currency` (`service.py:89`).
5. Write the new `cost_line_id` back onto the `boq.Position` row.
6. Auto-link budget: for any existing `BudgetLine` whose `boq_position_id`
   matches a position now carrying a cost line, set the budget line's
   `cost_line_id` and `control_account_id`. This is where the spine
   retroactively connects the budget that `generate_budget_from_boq` already
   produced.
7. Idempotency: re-running upserts on `(project_id, code)` and only fills nulls,
   never duplicates, mirroring the idempotency guarantee already documented for
   `generate_budget_from_boq` (`service.py:1006`). Publish
   `costmodel.spine.generated` via the existing `_safe_publish`
   (`service.py:46`).

### 5.2 Cross-module rollup, the read path

`rollup_for_project(project_id)` and `rollup_for_line(line_id)` assemble the
spine view by reading what each module already stores, converting every amount
to the project base currency through the existing FX helper `_amount_in_base`
and `_project_fx_context` in `costmodel/repository.py:24` and `243` (the same
helper the dashboard, budget summary, EVM, and cash flow already share, so the
spine cannot invent different FX math):

- estimate: `CostLine.estimate_amount`.
- budget planned / committed / actual: sum of linked `BudgetLine` rows by
  `cost_line_id`.
- PO committed: sum of `PurchaseOrderItem.amount` where
  `po_item.cost_line_id == line.id` and the parent PO status is `issued`,
  `partially_received`, or `completed` (draft POs are not commitments).
  Read through a join in the new repository, FX-converted by the PO
  `currency_code`.
- contracted value: sum of `ContractLine.total_value` where
  `contract_line.cost_line_id == line.id`, FX-converted by the contract
  `currency`.
- claimed to date: sum of `ProgressClaimLine.cumulative_completed_value` for
  those contract lines, reusing the existing claim-line repository join
  (`contracts.ProgressClaimLineRepository.lines_with_status_for_contract`,
  used at `contracts/service.py:1359`).

Cross-module reads use targeted imports inside the method, the established
pattern in this codebase for avoiding import cycles (see
`costmodel/service.py:99`, `662`, `988`, `1021`, all import sibling-module
repositories lazily).

### 5.3 Commitment routing, fixing the fragile wbs match

A new event subscriber set registered from the costmodel `on_startup`
(`backend/app/modules/costmodel/__init__.py`, which currently only registers
permissions). The subscribers reuse the proven short-lived-session pattern from
`finance/events.py` (each handler opens its own `async_session_factory`, line
137, so a failure never rolls back the upstream transaction) and the detached
publish guard already in costmodel (`_safe_publish`).

- on `procurement.po.issued` (payload already carries `po_id`, `project_id`,
  `amount_total`, `currency_code`, see `procurement/service.py:658`): resolve
  each PO line's `cost_line_id`, find the `BudgetLine` linked to that cost line,
  and add the line amount to `BudgetLine.committed_amount`. When a PO line has
  no `cost_line_id` yet, fall back to the existing `boq_position_id` match so
  legacy POs still route. This makes the costmodel budget, the one the EVM and
  dashboard read, finally reflect commitments. It runs alongside the existing
  finance handler, which keeps updating `finance.ProjectBudget`, so neither
  system regresses; the spine subscriber is additive.
- on `procurement.gr.confirmed` (payload carries `amount`, `currency_code`,
  `procurement/service.py:860`): move the matched amount from
  `committed_amount` to `actual_amount` on the linked `BudgetLine`, clamping
  committed at zero exactly as the finance handler does
  (`finance/events.py:188`).
- on `contracts.contract.signed` (`contracts/service.py:900`) and
  `contracts.claim.certified` (`contracts/service.py:1062`): recompute the
  contracted and claimed columns lazily, or simply publish
  `costmodel.spine.changed` so any open budget cockpit refetches. No write is
  required for these because the rollup reads contract values live.

This is the single point where estimate, budget, procurement, and contracts
become one spine: every module keeps writing its own rows, the spine links them
by `cost_line_id`, the rollup reads them through one FX-correct path, and the
two procurement events fold real commitments into the costmodel budget.

### 5.4 Why extend costmodel rather than add a module

`costmodel` already `depends=["oe_projects", "oe_boq"]`
(`costmodel/manifest.py:14`), already owns the budget line that links to BOQ,
already has the FX rollup helpers, and is `auto_install=True`. Procurement and
contracts depend downstream on it conceptually. Placing the spine here means the
keystone ships in one already-loaded core module with no new module
registration, no new dependency edges, and the budget-to-spine link lives next
to the budget model it connects. Procurement, contracts, rfq_bidding, and boq
only gain one nullable column each plus, for procurement, a subscriber that
already has a precedent in finance.

## 6. Frontend

Feature folder: `frontend/src/features/costmodel` (exists today with
`CostModelPage.tsx`, `CostBenchmark.tsx`, `api.ts`, `index.ts`). The spine is a
new tab on the existing 5D Cost Model page rather than a separate route, so it
sits beside the budget and S-curve the user already opens.

Components to add under `frontend/src/features/costmodel`:

- `CostSpinePanel.tsx`: the main spine view. A grid grouped by control account
  with expandable rows, columns Estimate / Budget / Committed / Contracted /
  Actual / Variance, currency-aware. Follows the table styling already used in
  `CostModelPage.tsx`.
- `ControlAccountTree.tsx`: left-side tree of control accounts driving the grid
  filter, same interaction model as the BOQ hierarchy tree.
- `GenerateSpineButton.tsx`: triggers `POST .../spine/generate-from-boq/`, shows
  the created-account and created-line counts in a toast, the same pattern as
  the existing "generate budget from BOQ" action.
- `CostLineRollupDrawer.tsx`: opens on a line, lists the linked BOQ positions,
  budget lines, PO items, contract lines, and RFQs with deep links to those
  modules' pages.

State and data: extend `frontend/src/features/costmodel/api.ts` with the new
endpoints using the same client the file already uses. Server state goes through
React Query (the project standard per the root CLAUDE.md), keyed by
`["spine", projectId]`, invalidated on generate and on the
`costmodel.spine.changed` signal surfaced through the existing notifications
channel. No new global Zustand store is needed; the active control-account
filter is local component state.

How it surfaces to the user: open a project, open 5D Cost Model, switch to the
Cost Spine tab. If no spine exists, a single Generate from BOQ button builds it.
After generation the grid shows every control account with the estimate rolled
up from BOQ and, as POs are issued and contracts signed, the Committed and
Contracted columns fill in live. Clicking any line opens the drawer that proves
the linkage by listing the exact records from each module.

## 7. Reuse, confirmed in code

| Reused asset | File | Used for |
| --- | --- | --- |
| `BudgetLine`, `BudgetLineRepository`, `aggregate_by_*` | `costmodel/models.py:67`, `repository.py:191` | the budget side of the spine, committed/actual sink |
| `_amount_in_base`, `_project_fx_context` | `costmodel/repository.py:24`, `243` | FX-correct rollup, one shared convention |
| `_serialise_money`, money field serializers | `costmodel/schemas.py:20` | Decimal-as-string JSON for new schemas |
| `_safe_publish`, `event_bus.publish_detached` | `costmodel/service.py:46` | spine events |
| `pick_default_boq`, `PositionRepository.list_for_boq` | `costmodel/service.py:982`, `boq/repository.py` | spine generation from BOQ |
| `boq.Position.classification`, `reference_code` | `boq/models.py:117`, `145` | control-account codes and stable line codes |
| `verify_project_access`, `RequirePermission`, `SessionDep`, `CurrentUserId` | `app/dependencies.py:411`, `274`, `516`, `518` | RBAC and project scoping on every spine route |
| costmodel permission set | `costmodel/permissions.py` | no new permissions to register |
| short-lived-session subscriber pattern | `finance/events.py:137` | commitment-routing subscribers |
| auto-PO-from-award event already copies `position_id` | `procurement/events.py:146` | the new PO item `cost_line_id` is populated here too |
| idempotent migration guards | `alembic/versions/v3150_file_favorites.py:49` | the new migration |
| GUID self-FK tree pattern | `boq/models.py:101` | control-account parent link |

## 8. Phasing

Region-neutral core first, no stubs. Every path in the MVP is real and
exercised end to end.

### Phase 1, MVP core, 6 days

Scope: the two new tables and the seven linkage columns with the migration;
`ControlAccount` and `CostLine` models, schemas, repository, the
`CostSpineService` with `generate_from_boq`, `rollup_for_project`,
`rollup_for_line`, and link/unlink; all endpoints in section 4; the
`CostSpinePanel`, `ControlAccountTree`, and `GenerateSpineButton` on the 5D
page; FX-correct rollup reading estimate from cost lines, budget from linked
budget lines, PO committed from linked issued PO items, contracted value from
linked contract lines. Generation auto-links existing budget lines. This is a
working spine: create a project, build BOQ, generate budget, generate spine,
link a PO line, see committed roll up.

Effort: 6 days.

### Phase 2, live commitment routing, 3 days

Scope: the costmodel event subscribers for `procurement.po.issued` and
`procurement.gr.confirmed` that fold committed and actual into the linked
costmodel `BudgetLine`, with the `boq_position_id` fallback for unlinked legacy
POs; populate `po_item.cost_line_id` inside the existing auto-PO-from-award
handler; the `CostLineRollupDrawer` with deep links. After this phase the
dashboard and EVM that read the costmodel budget reflect real procurement
without manual budget edits.

Effort: 3 days.

### Phase 3, deeper fidelity and partner-pack hooks, 4 days

Scope: contract-side wiring (set `contract_line.cost_line_id` on contract line
create and on the tender-to-contract path; recompute claimed-to-date in the
rollup using the existing progress-claim-line join); RFQ `cost_line_ids`
solicitation list and a from-spine RFQ create; spine status lifecycle
(`open`/`locked`/`closed` on accounts, blocking edits to a locked account's
lines, reusing the lock idea already in `boq.BOQ.is_locked`,
`boq/models.py:39`); a `costmodel.spine.changed` signal feeding the cockpit
refresh.

Partner-pack extension points (region-specific behaviour layered on the neutral
core, never in it):
- `classification_standard` is a label, so a DACH pack can seed DIN 276
  Kostengruppen as control accounts, a US pack CSI MasterFormat divisions, a UK
  pack NRM elements, by calling the existing accounts endpoint. No core change.
- pay-application formatting (US AIA G702/G703, DACH Abschlagsrechnung, UK JCT
  interim certificate) consumes the spine rollup as its data source and renders
  in a pack-specific exporter; the spine itself stays format-neutral. The hook
  is the stable `CostLineRollupResponse` shape, which already carries
  estimate / contracted / claimed-to-date per line.
- the existing partner-pack mechanism (entry-point group
  `openconstructionerp.partner_packs`, per MEMORY) selects which standard a
  tenant seeds; the spine reads whatever accounts exist.

Effort: 4 days.

Total: 13 days across three phases, MVP usable end to end after phase 1.

## 9. Risks and edge cases

- **Two budget systems stay parallel.** The spine feeds the costmodel
  `BudgetLine`. `finance.ProjectBudget` keeps its own committed/actual via the
  finance subscriber. They will show the same totals only if both are populated
  for the same scope. Mitigation: the spine is additive and authoritative for
  the 5D dashboard and EVM, which already read the costmodel budget; a later,
  separate initiative can converge the two budget tables. This design does not
  attempt that convergence and does not regress finance.

- **Currency mixing.** A project can carry cost lines, POs, and contracts in
  different currencies. The rollup must convert everything through the project
  FX rates and surface `mixed_currency` when an FX rate is missing, never blend
  silently. Mitigation: reuse `_amount_in_base` which keeps unconverted foreign
  amounts visible rather than zeroing them (`repository.py:43`), and the
  `mixed_currency` flag pattern from the Monte Carlo endpoint.

- **BOQ re-import or renumber.** Positions can be deleted and re-imported, and
  `ordinal` changes on renumber. Cost lines persist independently and link by
  the durable `boq_position_id` plus their own stable `code`, so a renumber does
  not orphan procurement or contract links. Edge: a deleted position leaves its
  cost line with a dangling `boq_position_id`; the line stays valid and keeps
  its downstream links, status can be set `superseded`.

- **Idempotent generation.** Re-running generate-from-boq after BOQ edits must
  not duplicate accounts or lines or double-link budgets. Mitigation: upsert on
  `(project_id, code)` and fill-nulls-only, the same guarantee as
  `generate_budget_from_boq`.

- **Cross-module delete safety.** Deleting a cost line that POs or contracts
  reference would strand commitments. Mitigation: the DELETE endpoint refuses
  with 409 and returns the linked counts; ON DELETE SET NULL on the
  `control_account_id` self and parent FKs prevents tree-delete cascades from
  nuking lines.

- **Concurrent PO issue events.** Two POs issued at once both add to the same
  budget line committed amount. Mitigation: the subscriber reads-modifies-writes
  in its own session and commits; for the rare hot line, an additive SQL
  `UPDATE ... SET committed_amount = committed_amount + :delta` avoids lost
  updates, the same shape the finance handler relies on.

- **Performance on large projects.** A 6k-position BOQ yields thousands of cost
  lines. The rollup must avoid N+1. Mitigation: the repository does grouped
  aggregate queries per module (one budget aggregate, one PO-item aggregate
  grouped by `cost_line_id`, one contract-line aggregate), mirroring the
  existing FX-aware aggregators and the N+1 fixes already in
  `procurement/service.py:913`.

- **Permission and scope leakage.** A spine read must not expose another
  project's lines. Mitigation: every route calls `verify_project_access` and
  scopes every query by `project_id`, and detail routes that take only a
  `line_id` resolve the line, then verify access to its `project_id`, the same
  pattern the costmodel budget-line PATCH uses (`router.py:272`).

## 10. Test plan

### Backend, pytest

Tests follow the repo's per-module temp-sqlite-before-import pattern: a temp DB
path is set into `DATABASE_URL` and `DATABASE_SYNC_URL` before any `from app...`
import (confirmed in `tests/integration/test_pipelines_executor.py:34` and
described in its docstring). Service-only unit tests use the `SimpleNamespace`
repo-stub pattern from `tests/unit/test_costmodel_service.py:29` and
`tests/unit/test_procurement.py:30`.

New files:
- `backend/tests/unit/test_cost_spine_service.py`: stubbed-repo unit tests for
  `generate_from_boq` (account tree built from classification, one line per
  costed position, section headers skipped, currency inherited), idempotency
  (second run creates nothing new), `rollup_for_line` math including FX
  conversion and the mixed-currency flag, and the link/unlink and 409-on-delete
  guards.
- `backend/tests/integration/test_cost_spine_api.py`: full ASGI client run
  against the temp DB. Create project, BOQ with positions, generate budget,
  generate spine, assert accounts and lines created and budget lines linked;
  create and issue a PO with a line carrying `cost_line_id`, assert the
  subscriber moves committed onto the linked budget line and that the rollup and
  the existing `/5d/dashboard` reflect it; create a contract line linked to a
  cost line and assert contracted value appears; IDOR checks that a second
  user cannot read or mutate the first project's spine (mirrors the IDOR block
  in `test_pipelines_executor.py`).
- extend `backend/tests/unit/test_procurement_finance_r7.py` or add a sibling to
  assert the new costmodel subscriber and the finance subscriber both fire
  without interfering.

Run: `cd backend && python -m pytest tests/unit/test_cost_spine_service.py
tests/integration/test_cost_spine_api.py -q`.

### Frontend, vitest

- `frontend/src/features/costmodel/CostSpinePanel.test.tsx`: renders the grid
  from a mocked rollup payload, asserts per-account grouping, currency
  formatting, and the mixed-currency warning banner. Follows the existing
  component-test pattern in `frontend/src/features/procurement/POStatusPipeline.test.tsx`.
- `frontend/src/features/costmodel/GenerateSpineButton.test.tsx`: mocks the
  generate endpoint, asserts the success toast shows created counts and that the
  spine query is invalidated.

Run: `cd frontend && npx vitest run src/features/costmodel`.

### Manual browser verification on the :8000 server

With the dev backend on :8000 and the frontend dev server proxying to it:
1. Log in, open a project that has a BOQ with priced positions.
2. Open 5D Cost Model, click Generate budget from BOQ, then open the new Cost
   Spine tab and click Generate from BOQ. Confirm control accounts and cost
   lines appear with the Estimate column populated and matching the BOQ total.
3. Go to Procurement, create a PO, set a line's cost line to one shown in the
   spine, issue the PO. Return to the Cost Spine tab and confirm the Committed
   column rose by the PO line amount and that the 5D dashboard KPIs moved.
4. Go to Contracts, create a contract with an SoV line linked to a cost line,
   sign it. Confirm Contracted value appears in the spine.
5. Open a cost line drawer and confirm it lists the exact BOQ position, budget
   line, PO item, and contract line, each deep-linking to its module page.
6. Switch project language via `?lang=de` and confirm no raw i18n keys leak in
   the new panel.

## 11. Structured summary mapping

- new tables: `oe_costmodel_control_account`, `oe_costmodel_cost_line`.
- new columns: `cost_line_id` and `control_account_id` on
  `oe_costmodel_budget_line`; `cost_line_id` on `oe_boq_position`,
  `oe_procurement_po_item`, `oe_procurement_req_item`,
  `oe_contracts_contract_line`; `cost_line_ids` JSON on `oe_rfq_rfq`.
- new endpoints under `/api/v1/costmodel/...spine...` per section 4.
- connects: boq, costmodel, procurement, rfq_bidding, contracts (and feeds the
  finance and full_evm/eac consumers downstream).

# 05 - True 5D Cockpit (BIM element to BOQ to schedule activity to cost)

Status: design, not yet built
Owner: DataDrivenConstruction
Depends on: 01-cost-spine
Module home: `backend/app/modules/costmodel` (new sub-surface) + a thin read service spanning `bim_hub`, `boq`, `schedule`
Constraint: BIM and CAD data only through the DDC cad2data canonical format. No IfcOpenShell, no native IFC parsing. BCF is permitted for issues and viewpoints but is not used by this feature.

## 1. What this is and why it connects the modules

The 5D cockpit is one read-and-navigate surface that joins the four dimensions we already store in separate tables: a BIM element (3D), the BOQ position that prices it (cost basis), the schedule activity that builds it (4D time), and the cost roll-up that tracks it (5D money). Today each leg of that chain exists and is queryable in isolation, but no endpoint and no screen presents the full chain end to end. A quantity surveyor who selects a wall in the viewer cannot see, in one place, which BOQ position carries its rate, which activity is scheduled to pour it, and what the planned-vs-actual cost of that scope is. The cockpit closes that gap.

The defensible part is not any single join. It is that we already own every link table, so the cockpit is a thin aggregation layer over verified infrastructure rather than a new data model. The links that make it possible are all present in the code:

- BIM element to BOQ position: `oe_bim_boq_link` (`BOQElementLink` in `backend/app/modules/bim_hub/models.py`) plus the live quantity binding `oe_boq_quantity_link` (`QuantityLink` in `backend/app/modules/boq/models.py`).
- Schedule activity to BOQ position: `Activity.boq_position_ids` JSON column (`backend/app/modules/schedule/models.py`, line 116) and `WorkOrder.boq_position_id`.
- Schedule activity to BIM element: `Activity.bim_element_ids` JSON column (line 145).
- Schedule activity to cost: `Activity.cost_planned` and `Activity.cost_actual` (`Numeric(20,4)`, lines 167-176).
- Cost roll-up to both BOQ and activity: `BudgetLine.boq_position_id` and `BudgetLine.activity_id` (`backend/app/modules/costmodel/models.py`, lines 82-83).

## 1a. Verification of existing fields (task requirement)

The task asked to confirm that `Activity` already carries the linking fields before designing the join. Confirmed against `backend/app/modules/schedule/models.py`:

| Field | Line | Type | Purpose |
|-------|------|------|---------|
| `boq_position_ids` | 116 | `JSON` list, server_default `[]` | BOQ positions this activity builds |
| `bim_element_ids` | 145 | `JSON` list or null | BIM element UUIDs (strings) for 4D linking |
| `cost_planned` | 167 | `Numeric(20,4)` nullable | Planned cost (PV) when cost-loaded |
| `cost_actual` | 172 | `Numeric(20,4)` nullable | Actual cost to date (AC) |

The `costmodel.BudgetLine` carries `boq_position_id` (line 82) and `activity_id` (line 83), so the cost dimension can be attributed to either the BOQ position or the activity. These are the four anchors the cockpit joins. No new linking columns are strictly required for the MVP. We add one optional persistence table for saved cross-dimension scopes and one cache table for the materialized graph, both described in section 2.

## 1b. What already exists, so we do not rebuild it

The 4D slice in `backend/app/modules/schedule/service_4d.py` and `router_4d.py` already wires schedule to BIM (through EAC predicate resolution and `ScheduleSnapshotService`, which builds an `{element_id: status}` map) and schedule to cost (through `ScheduleDashboardService`, which computes SPI, CPI and an S-curve from `Activity.cost_planned` and `Activity.cost_actual`). The costmodel `CostModelService.calculate_evm` in `backend/app/modules/costmodel/service.py` already links budget lines to activities to compute project EVM. The bim_hub `BIMHubService.list_links_for_model` already aggregates BIM elements to BOQ positions per model.

The cockpit does not duplicate any of that. It adds the one missing capability: an element-centric and activity-centric join that walks all four anchors together and returns the connected node graph for a single selection, plus a project-level overlay that colours the 3D model by schedule status and cost variance at the same time. It reuses `ScheduleSnapshotService` for the status map and the costmodel aggregates for the money.

## 2. Data model

### 2.1 Reused tables (no change)

Everything the join needs already exists. The cockpit reads:

- `oe_bim_model`, `oe_bim_element` (`bim_hub/models.py`)
- `oe_bim_boq_link` (`BOQElementLink`)
- `oe_boq_boq`, `oe_boq_position`, `oe_boq_quantity_link` (`boq/models.py`)
- `oe_schedule_schedule`, `oe_schedule_activity`, `oe_schedule_work_order` (`schedule/models.py`)
- `oe_costmodel_budget_line`, `oe_costmodel_snapshot` (`costmodel/models.py`)

### 2.2 New table: `oe_costmodel_cockpit_scope`

A saved, named cross-dimension selection so a user can persist a scope of interest (for example "Level 3 concrete works") and return to its 5D rollup. This is the cockpit analogue of `BIMElementGroup` but it spans dimensions rather than just elements. It lives in the costmodel module because the cockpit read surface is mounted there, alongside the existing 5D endpoints.

Columns follow the house conventions: ids are `GUID()`, money is string or `Numeric`, dates and times are ISO `String` columns, JSON for flexible lists, `metadata_` blob present everywhere.

| Column | Type | Notes |
|--------|------|-------|
| `id` | `GUID()` PK | inherited from `Base` |
| `project_id` | `GUID()` FK `oe_projects_project.id` ondelete CASCADE, indexed | project scoping |
| `name` | `String(255)` not null | human label |
| `description` | `Text` not null default "" | |
| `anchor_type` | `String(20)` not null | one of `bim_element`, `boq_position`, `activity`, `manual` |
| `bim_element_ids` | `JSON` list, server_default `[]` | element UUID strings |
| `boq_position_ids` | `JSON` list, server_default `[]` | position UUID strings |
| `activity_ids` | `JSON` list, server_default `[]` | activity UUID strings |
| `created_by` | `GUID()` nullable | |
| `metadata_` | `JSON` not null default `{}` | mapped to column name `metadata` |

Unique constraint `(project_id, name)` so the UI can address scopes by name, mirroring `BIMElementGroup`'s `uq_bim_element_group_project_name`.

### 2.3 New table: `oe_costmodel_cockpit_link_cache`

Optional read cache so the project-level 3D overlay does not re-walk every link on every model open. It stores the precomputed per-element rollup keyed by `(project_id, bim_element_id)`. It is a cache, never a source of truth; the live graph endpoint can always be served without it. Phase 2, not MVP.

| Column | Type | Notes |
|--------|------|-------|
| `id` | `GUID()` PK | |
| `project_id` | `GUID()` FK, indexed | |
| `bim_element_id` | `GUID()` indexed | matches `oe_bim_element.id` |
| `boq_position_ids` | `JSON` list | resolved positions |
| `activity_ids` | `JSON` list | resolved activities |
| `schedule_status` | `String(20)` nullable | worst-of status from `ScheduleSnapshotService` |
| `planned_cost` | `String(50)` default "0" | money as string |
| `actual_cost` | `String(50)` default "0" | money as string |
| `computed_at` | `String(40)` nullable | ISO timestamp |
| `metadata_` | `JSON` not null default `{}` | |

Unique constraint `(project_id, bim_element_id)`. Composite index `(project_id, schedule_status)` for the overlay legend counts.

### 2.4 Alembic migration outline

One revision, scoped to the costmodel module, following the existing pattern (for example `v3123_boq_fk_indexes` referenced in `boq/models.py`). The file goes in `backend/alembic/versions/`.

```
revision: vXXXX_cockpit_scope
down_revision: <current head>

upgrade():
  op.create_table(
    "oe_costmodel_cockpit_scope",
    sa.Column("id", GUID(), primary_key=True),
    sa.Column("created_at", sa.DateTime(timezone=True), ...),   # Base mixin cols
    sa.Column("updated_at", sa.DateTime(timezone=True), ...),
    sa.Column("project_id", GUID(), sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"), nullable=False),
    sa.Column("name", sa.String(255), nullable=False),
    sa.Column("description", sa.Text(), nullable=False, server_default=""),
    sa.Column("anchor_type", sa.String(20), nullable=False),
    sa.Column("bim_element_ids", sa.JSON(), nullable=False, server_default="[]"),
    sa.Column("boq_position_ids", sa.JSON(), nullable=False, server_default="[]"),
    sa.Column("activity_ids", sa.JSON(), nullable=False, server_default="[]"),
    sa.Column("created_by", GUID(), nullable=True),
    sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
  )
  op.create_index("ix_cockpit_scope_project", "oe_costmodel_cockpit_scope", ["project_id"])
  op.create_unique_constraint("uq_cockpit_scope_project_name", "oe_costmodel_cockpit_scope", ["project_id", "name"])
  # link cache (phase 2 - same revision is fine, table is inert until used)
  op.create_table("oe_costmodel_cockpit_link_cache", ...)
  op.create_unique_constraint("uq_cockpit_cache_project_elem", "oe_costmodel_cockpit_link_cache", ["project_id", "bim_element_id"])
  op.create_index("ix_cockpit_cache_project_status", "oe_costmodel_cockpit_link_cache", ["project_id", "schedule_status"])

downgrade():
  op.drop_table("oe_costmodel_cockpit_link_cache")
  op.drop_table("oe_costmodel_cockpit_scope")
```

Note on dev path: the project uses dynamic `create_all` for module tables on a fresh SQLite database (see MEMORY note "Match pipeline 7-stage wizard" and `v3.2.0` clean-install fix). The new models must be imported in the costmodel `models.py` so they register with `Base.metadata`, and the costmodel module must already be pulled into `main.py` startup (it is, it is `auto_install=True`). No extra wiring beyond declaring the models.

## 3. API

New router file `backend/app/modules/costmodel/router_cockpit.py`, mounted under the existing costmodel include in `main.py` (the costmodel router is auto-mounted at `/api/v1/costmodel` by the module loader and aliased at `/api/v1/finance/evm`; the cockpit router mounts at `/api/v1` so its paths are project-scoped and read naturally). All endpoints reuse `verify_project_access` from `app.dependencies` and `RequirePermission`, exactly like the existing costmodel router.

### 3.1 Permissions

The cockpit is read-mostly. It reuses the registered keys, no new permission registration needed for the MVP:

- Read endpoints: `Depends(RequirePermission("costmodel.read"))` (Role.VIEWER).
- Saved-scope write endpoints: `Depends(RequirePermission("costmodel.write"))` (Role.EDITOR).
- The graph walk also touches bim, boq and schedule data, but authorization is by project, not by module, so a single `verify_project_access(project_id, user_id, session)` call gates the whole join. This matches how `CostModelService.calculate_evm` already reads across modules under `costmodel.read`.

If product later wants the cockpit gated independently of the cost module, add `cockpit.read` / `cockpit.write` to `costmodel/permissions.py`; the MVP does not need it.

### 3.2 Endpoints

All paths are under `/api/v1`. Money is returned as plain strings or numbers consistent with each source module's existing serializers. Project scoping is enforced on every call.

| Method | Path | Permission | Purpose |
|--------|------|-----------|---------|
| GET | `/projects/{project_id}/cockpit/element/{element_id}` | costmodel.read | Element-anchored 5D node: the element, its linked BOQ positions, the activities that build it, and the cost rollup for that scope. |
| GET | `/projects/{project_id}/cockpit/position/{position_id}` | costmodel.read | BOQ-anchored node: the position, the BIM elements bound to it, the activities, and cost. |
| GET | `/projects/{project_id}/cockpit/activity/{activity_id}` | costmodel.read | Activity-anchored node: the activity, its BOQ positions, its BIM elements, planned-vs-actual cost. |
| GET | `/projects/{project_id}/cockpit/overlay` | costmodel.read | Project-level overlay: `{element_id: {status, cost_variance_band}}` for colouring the whole model. Query: `as_of_date`, `schedule_id`, `model_id`. |
| GET | `/projects/{project_id}/cockpit/summary` | costmodel.read | Linkage coverage KPIs: percent of elements linked to a position, positions linked to an activity, activities cost-loaded. Drives the "completeness" cards. |
| GET | `/projects/{project_id}/cockpit/scopes` | costmodel.read | List saved cross-dimension scopes. |
| POST | `/projects/{project_id}/cockpit/scopes` | costmodel.write | Create a saved scope. |
| GET | `/projects/{project_id}/cockpit/scopes/{scope_id}/rollup` | costmodel.read | The 5D rollup for a saved scope (same node shape as the anchored endpoints, unioned). |
| DELETE | `/cockpit/scopes/{scope_id}` | costmodel.write | Delete a saved scope (loads scope, verifies its project). |

### 3.3 Core response shape: the 5D node

A single node returned by the three anchored endpoints. Pydantic schemas live in `backend/app/modules/costmodel/schemas_cockpit.py`.

```
CockpitNode:
  anchor:            { type: "bim_element"|"boq_position"|"activity", id: UUID }
  bim:               list[CockpitBimRef]      # id, stable_id, element_type, storey, discipline, quantities
  boq:               list[CockpitBoqRef]      # position_id, boq_id, ordinal, description, unit, quantity, unit_rate, total (money as str)
  schedule:          list[CockpitActivityRef] # activity_id, schedule_id, name, wbs_code, start_date, end_date, progress_pct, status, is_critical
  cost:              CockpitCostRollup        # planned, committed, actual, forecast, earned_value, variance, spi, cpi, currency
  link_provenance:   list[CockpitLinkEdge]    # from_type, from_id, to_type, to_id, link_type, confidence, source ("manual"|"rule"|"quantity_link"|"activity_field")
  warnings:          list[str]                # e.g. "element linked to position in a different BOQ revision"
```

`CockpitCostRollup` mirrors the fields the costmodel dashboard already produces, with `currency` resolved through `CostModelService._get_project_currency` and never defaulted to EUR. Where multiple currencies appear across linked budget lines, the rollup carries a `mixed_currency` flag and converts through the existing `_amount_in_base` FX helper in `costmodel/repository.py`, exactly as `generate_cash_flow_from_schedule` already does. No money is ever blended without conversion.

The `overlay` endpoint returns a compact map, not full nodes, because it covers the whole model:

```
CockpitOverlayResponse:
  project_id: UUID
  as_of_date: str (ISO)
  model_id: UUID | null
  elements: { <element_id>: { status: str, cost_variance_band: "under"|"on"|"over"|"unknown", planned: str, actual: str } }
  legend_counts: { not_started: int, in_progress: int, completed: int, delayed: int, ahead_of_schedule: int, unlinked: int }
```

## 4. Service logic - the connective tissue

New service `CockpitService` in `backend/app/modules/costmodel/service_cockpit.py`. It is stateless, takes an `AsyncSession`, and orchestrates the existing repositories and services. This is the heart of the feature, so the join order is spelled out explicitly. It never imports IfcOpenShell or parses IFC; all BIM data comes from `oe_bim_element` rows that were already populated by the DDC cad2data canonical ingest pipeline.

### 4.1 Element-anchored walk (`get_element_node`)

Given `project_id` and `element_id`:

1. Load the `BIMElement` and verify its model belongs to the project (reuse the `_verify_project_access` pattern via `model.project_id`). Project scoping is non-negotiable.
2. BIM to BOQ. Query `oe_bim_boq_link` for `bim_element_id == element_id` to get directly linked positions. Also resolve `oe_boq_quantity_link` rows whose `element_stable_ids` contains the element's `stable_id`, because some positions are bound by the live quantity link rather than the manual element link. Union both, deduplicate by `position_id`. Record each edge's provenance (`manual`, `rule`, or `quantity_link`).
3. BIM to schedule. Reuse `ScheduleService.get_activities_for_bim_element(element_id, project_id)` which already exists (`schedule/service.py`, line 914) and scans `Activity.bim_element_ids` Python-side across the project. This is the direct element-to-activity edge.
4. BOQ to schedule. For each position found in step 2, find activities whose `boq_position_ids` contains that position id. Union with step 3 activities, deduplicate by `activity_id`. This catches the common case where the element is priced by a position and the position (not the element) is what the planner linked to the activity.
5. Cost rollup. For the union of positions and activities, pull `BudgetLine` rows where `boq_position_id` is in the position set or `activity_id` is in the activity set, plus the `Activity.cost_planned` and `Activity.cost_actual` values. Aggregate planned, committed, actual, forecast through the FX-aware path. Compute earned value as `planned * progress` per activity, the same identity `ScheduleDashboardService` uses. SPI and CPI are returned as `None` when there is no cost signal, never as zero, matching the 4D service contract.
6. Assemble the `CockpitNode` with provenance edges and any warnings (for example, a position linked to a BOQ whose `status` is locked, or an element linked across a revision boundary).

### 4.2 BOQ-anchored and activity-anchored walks

Same join graph, different entry point. `get_position_node` starts from `oe_bim_boq_link` and `oe_boq_quantity_link` to find elements, scans `boq_position_ids` to find activities, and rolls up cost by `BudgetLine.boq_position_id`. `get_activity_node` reads the activity's own `boq_position_ids` and `bim_element_ids` directly (cheapest path, no scan), then resolves elements and positions and rolls up cost from `BudgetLine.activity_id` plus the activity's own `cost_planned` / `cost_actual`. All three converge on the same `CockpitNode` builder so the response is identical regardless of anchor.

### 4.3 Project overlay (`get_overlay`)

This is the screen-defining call. It produces the colour map for the whole model:

1. Resolve the project's primary schedule (or the `schedule_id` query param) and call `ScheduleSnapshotService.snapshot(schedule_id, as_of_date, model_version_id)` to get the `{element_id: status}` map. This already handles the worst-of-status rule when an element is touched by several activities.
2. For cost banding, walk `BudgetLine` rows grouped by `activity_id`, compute planned-vs-actual per activity, then attribute each activity's variance band to the elements in its `bim_element_ids`. An element with no linked cost is banded `unknown`.
3. Merge status and cost band per element id. Count the legend buckets, including an `unlinked` bucket for elements present in the model but absent from both maps, so the completeness story is honest.
4. If the `oe_costmodel_cockpit_link_cache` is populated and fresh (phase 2), serve from it; otherwise compute live. The cache is invalidated by the existing module events (`schedule.activity.bim_links_updated`, `schedule.activity.position_unlinked`, `costmodel.budget_line.updated`, and the bim link create/delete) through the event bus that those services already publish.

### 4.4 How the modules connect, in one sentence each

- bim_hub gives the element, its canonical quantities, and the manual element-to-position links.
- boq gives the priced position and the live quantity binding that ties a position to canonical element quantities.
- schedule gives the activity, its direct element and position link arrays, and its progress and status derivation.
- costmodel gives the budget lines and EVM math that turn the linked scope into planned-vs-actual money, currency-correct.

The cockpit is the read service that walks those four in a fixed order and returns the connected node. That walk is the product.

## 5. Reuse - confirmed in code

| Reused asset | File | What we use it for |
|--------------|------|--------------------|
| `Activity.boq_position_ids`, `bim_element_ids`, `cost_planned`, `cost_actual` | `schedule/models.py` 116,145,167,172 | the four anchors |
| `BOQElementLink` (`oe_bim_boq_link`) | `bim_hub/models.py` 167 | element to position edge |
| `QuantityLink` (`oe_boq_quantity_link`) | `boq/models.py` 355 | live element-quantity to position edge |
| `BudgetLine.boq_position_id`, `activity_id` | `costmodel/models.py` 82,83 | cost attribution to either anchor |
| `ScheduleService.get_activities_for_bim_element` | `schedule/service.py` 914 | element to activity reverse lookup |
| `ScheduleSnapshotService.snapshot` | `schedule/service_4d.py` 363 | element status map for the overlay |
| `ScheduleDashboardService` SPI/CPI/EV identities | `schedule/service_4d.py` 550 | cost rollup math, do not reinvent |
| `CostModelService._get_project_currency`, `_amount_in_base` | `costmodel/service.py`, `costmodel/repository.py` | currency-correct, FX-aware rollup |
| `BIMHubService.list_links_for_model` | `bim_hub/service.py` 1391 | model-wide element-to-position aggregate |
| `verify_project_access`, `RequirePermission`, `CurrentUserId`, `SessionDep` | `app/dependencies.py` | project scoping + RBAC |
| `event_bus.publish_detached` and existing module events | `costmodel/service.py` 46, schedule services | cache invalidation |
| `PlanningCrossLinks` strip | `frontend/src/features/schedule/PlanningCrossLinks.tsx` | cockpit joins the existing planning nav chain |
| BIM viewer, `BIMLinkedBOQPanel`, `CreateTaskFromBIMModal`, `LinkActivityToBIMModal` | `frontend/src/features/bim/` | the cockpit panel docks into the existing viewer rather than a new viewer |

## 6. Frontend

Feature folder: a new `frontend/src/features/cockpit/` plus a docked panel inside the existing `frontend/src/features/bim/` viewer. We do not build a second 3D viewer; the cockpit overlay and side panel mount onto `BIMPage.tsx`, which already loads the canonical model and selection state.

### 6.1 Components and screens

- `CockpitPage.tsx`: the standalone cockpit route. Left is the existing 3D viewer (reused from `features/bim`), right is `CockpitNodePanel`. Top is a `PlanningCrossLinks`-style strip so the cockpit sits inside the BOQ to Schedule to 5D chain that already exists.
- `CockpitNodePanel.tsx`: renders a `CockpitNode` as four stacked cards (BIM, BOQ, Schedule, Cost) with the provenance edges drawn between them as a small linkage diagram. Selecting any chip in one card cross-highlights the related rows in the others and in the 3D scene.
- `CockpitOverlayLegend.tsx`: the colour legend with `legend_counts`, plus a toggle between "colour by schedule status" and "colour by cost variance". This drives the element tint in the viewer.
- `CockpitCoverageCards.tsx`: the completeness KPIs from `/cockpit/summary` (percent linked at each hop), so users see and can fix gaps.
- `SaveCockpitScopeModal.tsx`: persist the current cross-dimension selection as a named scope.
- `api.ts`: typed client for the new endpoints, generated against the same OpenAPI types the rest of the frontend uses.

### 6.2 State

Zustand store `cockpitStore` for the current anchor, the resolved node, the overlay mode (status vs cost), and the cross-highlight selection. Server data via React Query keyed on `(project_id, anchor_type, anchor_id, as_of_date)`, matching the existing `features/costmodel/api.ts` and `features/schedule/api.ts` patterns. The overlay map is a separate React Query key so the legend and tint refetch independently of the side panel.

### 6.3 How it surfaces to the user

Three entry points, all reusing existing affordances:

1. From the BIM viewer: clicking an element opens the `CockpitNodePanel` for that element. The existing `BIMLinkedBOQPanel` is extended (or the cockpit panel sits beside it) so the user goes from "linked BOQ" to the full 4-card chain in one step.
2. From the BOQ editor and the schedule Gantt: a "View in 5D cockpit" action on a position or activity opens `CockpitPage` anchored on that node.
3. From the 5D Cost Model page (`features/costmodel/CostModelPage.tsx`): a new tab "Cockpit" that opens the project overlay so the model lights up red where cost is over and amber where the schedule is slipping, at the same time.

Route registration in `frontend/src/app/App.tsx` next to the existing `/5d` and `/bim` routes, with a lazy import like the others. Sidebar entry under the Planning group, gated by the `costmodel` module key the same way `/5d` already is (`Sidebar.tsx` line 321).

## 7. Risks and edge cases

- Cross-revision BOQ links. A position can belong to a locked or superseded BOQ (`BOQ.is_locked`, `parent_estimate_id`). The walk must surface a warning and prefer the active revision, not silently sum a stale rate. Handled by a warning in `CockpitNode.warnings`.
- Double-counting cost. Cost can be attributed both to a position (via `BudgetLine.boq_position_id`) and to the activity that builds that position (via `BudgetLine.activity_id`). The rollup must deduplicate budget lines by `BudgetLine.id` and attribute each line once, never adding the same line under both the position and the activity branch.
- Many-to-many fan-out. One element can feed several positions, one position can be built by several activities. The node shows the full set, but the cost rollup must divide shared budget across consumers using a documented rule (equal split by default, the same simplification `ScheduleDashboardService` already makes) and label it as an estimate.
- JSON-column scans. `Activity.bim_element_ids` and `boq_position_ids` are JSON lists scanned Python-side (the codebase deliberately avoids dialect-specific JSON operators for SQLite and PostgreSQL parity). The overlay must bound the scan by project and, on large projects, fall back to the link cache (phase 2). Without the cache, the live overlay is O(activities times elements) and needs a per-project guardrail.
- Currency blending. Multiple linked budget lines in different currencies must convert through `_amount_in_base` and set `mixed_currency`. Never sum raw amounts across currencies. This is an established bug class in this codebase (see the cash-flow and Monte Carlo fixes) and must not regress.
- Empty or partial chains. An element with no BOQ link, a position with no activity, an activity with no cost are all valid states. The node renders the present legs and the coverage cards count the gaps rather than erroring.
- Legacy dict-shaped `bim_element_ids`. The model docstring warns some legacy rows may hold a dict. Normalize with `list(activity.bim_element_ids or [])` and treat non-list as empty, exactly as the existing service code does.
- Stale cache. The link cache must be invalidated on the link-mutation events the modules already publish. If an event is missed, the live endpoints remain correct; the cache is best-effort and a "recompute overlay" action forces a rebuild.
- Authorization. Every endpoint resolves the project and calls `verify_project_access`; the join must never leak a node for a project the caller cannot see, returning 404 (not 403) consistent with the platform IDOR policy.

## 8. Phasing

### Phase 1 - MVP, end to end, no stubs (effort: 6 days)

Element-anchored, position-anchored and activity-anchored node endpoints, the `/cockpit/summary` coverage endpoint, the `CockpitService` walk over the existing link tables, the `CockpitNode` schema with FX-correct cost rollup, and the `CockpitNodePanel` docked in the BIM viewer plus a standalone `CockpitPage`. No new persistence beyond reads; saved scopes deferred. Every leg works against real data: select an element, see its positions, activities and planned-vs-actual cost. Region-neutral.

Region partner-pack extension point: the cost rollup labels (retention, certified-to-date, this-period vs previous) are exposed through a formatter hook so a partner pack can render an AIA G702/G703 continuation-sheet view (US), a DIN 276 cost-group rollup (DACH), or a JCT interim-valuation view (UK) without touching the core node. The core returns neutral fields (planned, committed, actual, forecast, earned, variance); packs map them to local document semantics.

### Phase 2 - project overlay and the colour map (effort: 4 days)

The `/cockpit/overlay` endpoint reusing `ScheduleSnapshotService`, the `CockpitOverlayLegend` with the status-vs-cost toggle, element tinting in the viewer, and the `oe_costmodel_cockpit_link_cache` with event-driven invalidation. This is the visually defensible "the whole model lights up by 4D status and 5D variance at once" view.

### Phase 3 - saved scopes and rollup persistence (effort: 3 days)

The `oe_costmodel_cockpit_scope` table and its CRUD endpoints, the `SaveCockpitScopeModal`, the scope rollup endpoint, and the cockpit tab on the 5D Cost Model page. Lets teams curate and revisit named cross-dimension scopes.

### Phase 4 - deeper fidelity (effort: 5 days)

Time-phased cost on the overlay (cost variance as of a chosen date, not just to-date), what-if propagation (reuse `CostModelService.create_what_if_scenario` so a rate change in the cockpit flows to the linked positions and activities), and per-region partner-pack rollup views built on the Phase 1 formatter hook. Also a BCF export of cockpit-flagged elements (over-budget or delayed) as issues with viewpoints, using the permitted BCF I/O path and no IfcOpenShell.

## 9. Test plan

### Backend (pytest, per-module temp SQLite set before app import)

Follow the established pattern in `backend/tests/integration/test_4d_api.py`: a per-test temp SQLite file, `Base.metadata.create_all` after importing the FK-target models (`projects`, `users`, `bim_hub`, `boq`, `schedule`, `costmodel`), dependency overrides for `get_session` and `get_current_user_id`, and a seeded project owned by the test user. New files:

- `tests/unit/test_cockpit_walk.py`: with a hand-built fixture (one model, three elements, two positions, two activities, three budget lines spanning both anchors), assert the element-anchored walk returns the correct unioned positions and activities, deduplicates budget lines by id, and computes the FX-correct rollup. Assert SPI/CPI are `None` when no cost is loaded.
- `tests/unit/test_cockpit_overlay.py`: assert the status map merges with the cost bands, the worst-of-status rule holds when an element is linked to a delayed and an in-progress activity, the legend counts (including `unlinked`) sum to the element count, and a multi-currency fixture sets `mixed_currency`.
- `tests/integration/test_cockpit_api.py`: end-to-end over the mounted router. Cover the three anchored endpoints, the overlay, the summary, save-scope create and list, and the authorization cases: a foreign user gets 404, a missing project gets 404, a viewer can read but cannot create a scope.
- Edge tests: locked-BOQ warning surfaces, legacy dict-shaped `bim_element_ids` is treated as empty, double-attributed budget line is counted once.

### Frontend (vitest)

Co-located tests in `frontend/src/features/cockpit/__tests__/` mirroring the existing `features/bim/__tests__` style:

- `CockpitNodePanel.test.tsx`: renders a mocked `CockpitNode` and asserts the four cards, the provenance edges, and that selecting a BOQ chip cross-highlights the matching activity row.
- `CockpitOverlayLegend.test.tsx`: asserts the legend counts render and the status-vs-cost toggle switches the tint mode.
- `cockpit/api.test.ts`: asserts the query keys and that money strings are passed through without float rounding, consistent with the existing money-handling tests.

### Manual browser verification on the :8000 server

Against a running local backend on :8000 with a demo project that has a BIM model, a BOQ with linked positions, a schedule with activities, and generated budget lines (use the existing 5D "generate budget from BOQ" and "generate cash flow" actions to populate cost):

1. Open the BIM viewer, click a linked wall, confirm the cockpit panel shows its BOQ positions, the activities that build it, and a non-zero planned-vs-actual cost with the correct project currency.
2. Open the cockpit overlay, toggle status colouring, confirm delayed activities tint their elements and the legend counts match the activity statuses; toggle cost colouring, confirm over-budget scopes tint red.
3. From the BOQ editor, use "View in 5D cockpit" on a position and confirm the same node renders anchored on that position.
4. Save a scope, reload, confirm it lists and its rollup matches the live union.
5. Authorization: as a viewer account confirm read works and save is blocked; as a foreign user confirm the cockpit endpoints return 404.

## 10. Summary

The 5D cockpit is the read surface that finally presents the BIM-to-BOQ-to-activity-to-cost chain as one connected node, on top of link tables we already own and a 4D status engine we already ship. The MVP needs no new linking columns, only a thin join service and a panel that docks into the existing viewer. It is region-neutral at the core with a formatter hook for AIA, DIN and JCT rollup views in partner packs. The defensible position is that this join is cheap for us and expensive for anyone without our four pre-wired anchors.

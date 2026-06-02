# 09 - AI Assistant grounded in CWICR/pgvector + Cross-module Project-Controls Dashboard

Status: design, not yet implemented.
Owner: DataDrivenConstruction.
Depends on: 01-cost-spine, 03-budget-cockpit, 04-auto-evm.

## 1. What this feature is

Two synthesis surfaces that tie the platform's modules into one coherent product, built almost entirely on infrastructure that already exists in the codebase.

1. A **submittal / RFI / spec assistant** that is grounded in the CWICR cost catalogue and the cross-module pgvector store. The user asks a natural-language question about a submittal, an RFI, or a spec section, and the assistant answers by retrieving the right submittals, RFIs, documents, BOQ positions and CWICR cost items, then quoting them with provenance. It can also draft an RFI or summarise a submittal review, always for human confirmation.

2. A single **executive project-controls dashboard** that joins the cost spine, schedule, quality, safety, risk and change data into one screen. Cost (EVM: CPI, SPI, CV, SV, EAC, VAC), schedule (SPI, milestone slippage), quality (first-pass yield, cost of poor quality, NCR count, RFI turnaround), safety (TRIR, incidents), risk (open exposure, unmitigated high risks) and changes (change-order ratio, pending variation value) are presented per project and across the portfolio, currency-honest, with one-click drill-down to the source records.

The whole point is the connective tissue. Neither surface introduces a new data domain. The assistant is a retrieval-and-reasoning layer over modules that already store the data; the dashboard is an aggregation layer over KPIs that already compute the data. This document grounds every claim in the real files.

## 2. What already exists (verified in code)

Both halves are roughly 70 percent built. The work is connecting and completing, not greenfield.

### 2.1 The assistant half is mostly built

`backend/app/modules/erp_chat/service.py` already runs a full SSE streaming agent loop (`ERPChatService.stream_response`, lines 238-495) with Anthropic and OpenAI tool-calling, a 5-round cap (`MAX_AGENT_ROUNDS`), per-user daily token budget, history hardening, and per-turn observability (tokens in/out, cache hit, latency) persisted on `ChatMessage`.

`backend/app/modules/erp_chat/tools.py` already defines the tools and handlers, including:

- `search_cwicr_database` (handler `handle_search_cwicr_database`, lines 863-894) which calls `CostItemRepository.search(q=..., region=..., limit=20)` over the real CWICR table.
- `search_documents`, `search_boq_positions`, `search_risks`, `search_tasks`, `search_bim_elements`, `search_anything`, all routing to `app.modules.search.service.unified_search_service` (the two-track vector + SQL fused search).
- `get_risk_register`, `get_schedule`, `get_validation_results`, `get_cost_model`, `compare_projects`.
- A robust RBAC and IDOR gate: `_require_project_access` (404-over-403), `check_tool_permission` (manager+ for write tools), `TOOL_PERMISSIONS`, `TOOL_HANDLER_MAP`.

`backend/app/modules/costs/vector_adapter.py` already embeds CWICR into the `oe_cost_items` collection with the E5 `passage:`/`query:` prefix convention, plus a SQL ILIKE lexical fallback for when the vector extra is absent (`search`, lines 514-688). `to_text` is `description | classifier_codes | unit`; payload carries unit, unit_cost, currency, region_code, source, language, and DIN276/NRM/MasterFormat codes.

`backend/app/core/vector_index.py` is the multi-collection store: `COLLECTION_COSTS = "oe_cost_items"`, `COLLECTION_DOCUMENTS`, `COLLECTION_CHAT`, etc., plus `search_collection`, `unified_search`, `reciprocal_rank_fusion`, and the `EmbeddingAdapter` protocol.

`backend/app/modules/ai_agents/base.py` is a complete ReAct framework: `Agent`, `AgentRunner` (wall-clock, token, iteration and per-step timeouts), `ToolRegistry`, `FunctionTool`, `register_agent`, `global_tool_registry`, and `__agent_context__` injection that strips any LLM-forged context and re-injects the trusted one. `backend/app/modules/ai_agents/models.py` persists `AgentRun` and `AgentStep`.

The RFI and submittal targets are real: `backend/app/modules/rfi/models.py` `RFI` (subject, question, official_response, discipline, cost_impact, schedule_impact, linked_drawing_ids), `backend/app/modules/submittals/models.py` `Submittal` (title, spec_section, submittal_type, status, linked_boq_item_ids).

What is missing for the assistant: there is no `search_submittals` tool, no `search_rfis` tool, no RFI/submittal vector adapters, and no dedicated submittal/RFI/spec drafting agent. The cost grounding is keyword-only today (`search_cwicr_database` uses SQL `search`, not the `oe_cost_items` vector adapter). And there is a real bug in two existing handlers (see Risks, item R1).

### 2.2 The dashboard half is mostly built

`backend/app/modules/bi_dashboards/kpis.py` (2163 lines) already registers, as graceful-degradation Python formulas, the entire cost/schedule/quality/safety spine:

- EVM: `cpi`, `spi`, `cv`, `sv`, `eac`, `etc`, `vac`, `tcpi`, all built on `_evm_snapshot` which sources BAC from `Project.budget`/`contract_value`, PV/EV from `Task.planned_value`/`earned_value`, and AC from `finance.Payment` plus `procurement.PurchaseOrder`, with per-project FX conversion via `Project.fx_rates` and portfolio-mode per-currency bucketing (never blends currencies).
- Financial: `procurement_savings`, `change_order_ratio`, `cash_in_30d`, `cash_out_30d`, `dso`.
- Quality: `first_pass_yield` (inspections), `copq` (NCR cost impact), `punch_close_rate`, `rfi_close_avg_days`.
- Safety: `safety_trir`.
- Sustainability/operational: `embodied_carbon_per_m2`, `equipment_utilization`, `subcontractor_avg_rating`, `bid_win_rate`, `project_count_active`.

Each KPI returns a `KPIComputation` (Decimal value, unit, source_record_count, breakdown). `kpis.compute`, `kpis.benchmark` (portfolio median + percentile) and `kpis.drilldown` (per-KPI record providers, EVM drill-down already registered) are the read API.

`backend/app/modules/bi_dashboards/models.py` has `Dashboard`, `DashboardWidget` (kpi_code, drill_path, config_json), `DashboardWidgetSnapshot` (cached value), `KPIValue` (trend history), `AlertRule` (single + composite expression), `ReportDefinition`/`ReportRun`/`ReportSchedule`, `SavedFilter`. The consumer module deliberately omits cross-module ORM FKs.

`backend/app/modules/bi_dashboards/service.py` has `render_dashboard`, `evaluate_dashboard` (cross-filter), `drill_down`, `run_report`, alert evaluation, and snapshot caching. `backend/app/modules/bi_dashboards/router.py` exposes the full CRUD and the `install-starter-pack` seed. `seed.py` already ships 5 role-based dashboards (CEO/CFO/PM/Site Manager/Safety Officer).

`backend/app/modules/project_intelligence/` is a single-project readiness scorer (collector + scorer + advisor) weighted for the Estimation Dashboard (BOQ 0.40, cost_model 0.30, validation 0.20, risk 0.10). It is NOT a portfolio executive controls view, but its collector (`collect_project_state`, 14 parallel per-domain collectors over raw SQL) and its `/summary` shape are reusable patterns.

What is missing for the dashboard: there is no risk-exposure KPI, no NCR-count KPI, no pending-variation-value KPI, no schedule-milestone-slippage KPI; there is no single "executive project controls" dashboard preset that puts cost + schedule + quality + safety + risk + changes side by side with status banding; and there is no consolidated single-call "controls snapshot" endpoint that returns the whole spine for one project plus drill links in one round-trip (the dashboard render path computes each KPI in its own widget).

## 3. Scope split: what we build

The MVP completes both halves end to end with no stubs, reusing the existing engines. We do not rebuild erp_chat, the KPI registry, or the vector store. We add:

For the assistant: RFI and submittal vector adapters, four new grounded tools (`search_submittals`, `search_rfis`, `search_cost_catalog` using the real `oe_cost_items` vector adapter, `get_submittal_detail`/`get_rfi_detail`), an upgraded system prompt, and a dedicated submittal/RFI/spec drafting agent registered in `ai_agents`. The assistant surfaces inside the existing erp-chat full-page UI and floating panel, with no new module needed for the chat itself.

For the dashboard: a small new module `project_controls` that adds the missing KPIs (risk exposure, NCR count, pending variation value, milestone slippage) to the shared KPI registry, plus a consolidated `GET /api/v1/project-controls/snapshot` endpoint that assembles the cost + schedule + quality + safety + risk + change spine in one round-trip with drill links and status banding, plus a `controls_executive` dashboard preset seeded into bi_dashboards. The frontend gets a new `project-controls` feature folder.

We use a new thin module (`project_controls`) rather than bolting onto bi_dashboards because the snapshot endpoint has a different contract (one call returns the whole spine, status-banded, with cross-module drill URLs) and because per the module conventions every new surface is its own module with its own manifest, permissions, router and tests. The new KPIs themselves register into the existing shared `bi_dashboards.kpis` registry so the BI dashboards, alerts and reports automatically gain them too.

## 4. Data model

Dates/times are String ISO columns, money is string or `Decimal`, ids are `GUID` UUID, per the platform convention. We reuse existing models wherever they exist.

### 4.1 Reused, unchanged

| Model | File | Used for |
|-------|------|----------|
| `ChatSession`, `ChatMessage`, `ChatTurnFeedback` | `erp_chat/models.py` | Assistant conversation + observability |
| `AgentRun`, `AgentStep` | `ai_agents/models.py` | Drafting-agent run timeline |
| `CostItem` | `costs/models.py` | CWICR grounding (rate string, region, classification JSON, descriptions) |
| `RFI`, `Submittal` | `rfi/models.py`, `submittals/models.py` | Assistant retrieval targets |
| `Dashboard`, `DashboardWidget`, `KPIValue`, `AlertRule`, `DashboardWidgetSnapshot` | `bi_dashboards/models.py` | Controls dashboard config + trend + alerts |
| `Risk` (`oe_risk_register`) | `risk/models.py` | Risk-exposure KPI source (impact_cost, risk_tier, status, mitigation) |
| `NCR` (`oe_ncr_ncr`) | `ncr/models.py` | NCR-count + COPQ source (severity, status, cost_impact) |
| `VariationRequest`, `VariationOrder`, `VariationCostImpact` | `variations/models.py` | Pending-variation-value KPI (estimated_cost_impact, final_cost_impact, currency, status) |
| `Schedule`, `Activity`, `Baseline` | `schedule/models.py` | Milestone-slippage KPI |
| `Project` (`fx_rates`, currency, budget, contract_value) | `projects/models.py` | FX + base-currency resolution (already used by `kpis._project_currency_and_fx`) |

### 4.2 New tables

Only one genuinely new table is needed, plus the standard chat/agent rows are already created by their modules. The assistant grounding and the dashboard snapshot are both read-only over existing data; the only persistent new state is a saved view for the controls dashboard, and an audit row for assistant-drafted artefacts.

**`oe_project_controls_view`** - a user-saved configuration of the executive controls board (which KPIs, which projects, status thresholds). This is distinct from `bi_dashboards.Dashboard` because the controls board is a fixed-layout spine, not a free widget grid, and its config is a typed thresholds object rather than a generic `layout_json`.

| Column | Type | Notes |
|--------|------|-------|
| `id` | `GUID` | PK (Base provides) |
| `name` | `String(255)` | required |
| `owner_user_id` | `GUID` nullable, indexed | no ORM FK (consumer pattern) |
| `scope` | `String(16)` | `personal` / `role` / `global`, default `personal` |
| `role_ref` | `String(64)` nullable | for role-scoped views |
| `project_ids_json` | `JSON` | list of project UUID strings, `[]` means whole portfolio |
| `kpi_codes_json` | `JSON` | ordered list of KPI codes shown; default the executive spine |
| `thresholds_json` | `JSON` | `{kpi_code: {amber: "0.95", red: "0.90", direction: "lower_is_worse"}}` |
| `is_default` | `Boolean` | default false |
| `created_at`, `updated_at` | inherited String ISO from Base | |

**`oe_project_controls_drafted_artifact`** - an audit row recording an assistant-drafted RFI or submittal summary that a human accepted, so we never silently mutate domain data and we keep provenance (per the AI-augmented-human-confirmed principle).

| Column | Type | Notes |
|--------|------|-------|
| `id` | `GUID` | PK |
| `project_id` | `GUID` nullable, indexed | no ORM FK |
| `kind` | `String(32)` | `rfi_draft` / `submittal_summary` / `spec_answer` |
| `agent_run_id` | `GUID` nullable | links to `oe_ai_agents_run` |
| `target_type` | `String(32)` | `rfi` / `submittal` / `none` |
| `target_id` | `GUID` nullable | the RFI/Submittal it was applied to, if accepted |
| `draft_content` | `Text` | the markdown draft |
| `grounded_refs_json` | `JSON` | `[{collection, id, score, title}]` cited sources |
| `accepted_by` | `GUID` nullable | who confirmed |
| `accepted_at` | `String(40)` nullable | ISO string |
| `created_by` | `GUID` nullable | |
| `created_at` | inherited | |

We do NOT add a separate vector table. CWICR, RFI, submittal and document embeddings all live in the existing unified collections (`oe_cost_items`, `oe_documents`, plus two new logical collections `oe_rfis` and `oe_submittals` declared as constants in `vector_index.py`). New collections cost nothing structurally: the underlying LanceDB/Qdrant generic schema is `id, vector, text, tenant_id, project_id, module, payload` and a new collection is just a new name.

### 4.3 Alembic migration outline

Module-scoped migration `backend/app/modules/project_controls/migrations/` (the module convention), or a single repo migration under `alembic/versions/` following the existing numbered scheme (the codebase uses `vXXXX_*` revision ids, currently around v3150). One revision:

- `op.create_table("oe_project_controls_view", ...)` with the columns above, `GUID()` for ids, `String` ISO for timestamps, `JSON` for the list/dict columns, `server_default` on booleans (`"0"`) and JSON (`"[]"` / `"{}"`) matching the bi_dashboards pattern (server defaults are mandatory because the platform uses `create_all` on fresh SQLite and the columns must populate without a Python default, the v4.4.1 lesson).
- `op.create_table("oe_project_controls_drafted_artifact", ...)`.
- `op.create_index` on `owner_user_id`, on `project_id` for both tables, and on `(kind)` for the artifact table.
- No FKs to other modules' tables (consumer-module rule). The `agent_run_id` is a soft reference, not an ORM FK, because `project_controls` must not couple to the ai_agents lifecycle.

The new KPI formulas need NO migration: they register into the in-process `KPI_FORMULAS` dict on import and are seeded as `KPIDefinition` rows by the existing `bootstrap_system_kpis` on startup, which is idempotent.

The two new vector collections need NO migration: vector storage is outside the relational schema.

## 5. API

All under `/api/v1`. Project scoping uses the established `verify_project_access` (from `app.dependencies`) and the erp_chat tool-level `_require_project_access` for the in-agent path.

### 5.1 Assistant (extends erp_chat, no new module)

The chat transport endpoints stay exactly as they are (`POST /api/v1/erp_chat/stream/`, sessions CRUD). We extend the tool surface, which is invoked inside the existing SSE stream, so no new HTTP endpoint is required for the basic grounded assistant. The new tools are added to `erp_chat/tools.py`:

| Tool name | Permission | Grounding source | Notes |
|-----------|------------|------------------|-------|
| `search_cost_catalog` | read | `costs.vector_adapter.search()` (`oe_cost_items`, E5) | Replaces keyword-only `search_cwicr_database` as the preferred path; passes `region`, `din276_kg_prefix`, `project_currency`. Keeps `search_cwicr_database` as a SQL fallback alias. |
| `search_submittals` | read | `unified_search_service(types=["submittals"], project_id=...)` | New `oe_submittals` collection |
| `search_rfis` | read | `unified_search_service(types=["rfis"], project_id=...)` | New `oe_rfis` collection |
| `get_submittal_detail` | read | `SubmittalService` / repository, gated by `_require_project_access` | Returns spec_section, status, linked BOQ items, review history |
| `get_rfi_detail` | read | `RFIService` / repository, gated by `_require_project_access` | Returns question, official_response, discipline, cost/schedule impact |

Each follows the existing handler contract exactly: returns `{renderer, data, summary}`; project-scoped handlers call `_require_project_access` first and return `_auth_error` (404-shaped) on denial; all are added to `TOOL_PERMISSIONS` and `TOOL_HANDLER_MAP`.

A new drafting agent endpoint lives in `ai_agents` (its router already exists for run/fetch):

`POST /api/v1/ai_agents/agents/{agent_name}/run` (existing shape) with `agent_name = "submittal_rfi_assistant"`. Body `{project_id, input}`. RBAC: requires the ai_agents create permission plus, inside the agent's tools, `_require_project_access` on every project-scoped call. Response is the existing `AgentRun` + steps timeline. The agent's `allowed_tools` is the read-only grounded set above plus a `draft_rfi` and a `summarise_submittal` tool that produce text only and never mutate domain rows.

`POST /api/v1/project-controls/drafts/{draft_id}/accept` (new, in project_controls) records human confirmation, optionally applying the draft to the target RFI/submittal via that module's service, and writes the `oe_project_controls_drafted_artifact` accepted fields. RBAC: manager+ on the project (reuses the manager check pattern).

### 5.2 Project-controls dashboard (new module `project_controls`)

Router mounted at `/api/v1/project-controls/`.

| Method + path | Request | Response | RBAC |
|---------------|---------|----------|------|
| `GET /snapshot` | query `project_id` (UUID, optional - omit for portfolio), `period_start`, `period_end` (ISO date strings, optional) | `ControlsSnapshotResponse` (see below) | `project_controls.read` (VIEWER); if `project_id` set, also `verify_project_access` |
| `GET /views` | - | `list[ControlsViewRead]` (caller's + shared) | `project_controls.read` |
| `POST /views` | `ControlsViewCreate` | `ControlsViewRead` | `project_controls.write` (EDITOR) |
| `PATCH /views/{view_id}` | `ControlsViewUpdate` | `ControlsViewRead` | owner or admin (404-on-miss) |
| `DELETE /views/{view_id}` | - | 204 | owner or admin |
| `GET /drill/{kpi_code}` | query `project_id`, `limit` | `DrillResponse` (delegates to `bi_dashboards.kpis.drilldown`) with cross-module deep-link URLs added | `project_controls.read` + `verify_project_access` |
| `POST /drafts/{draft_id}/accept` | `AcceptDraftRequest` | `DraftedArtifactRead` | manager+ on project |

`ControlsSnapshotResponse` shape (one round-trip for the whole spine):

```
{
  "project_id": "uuid | null",
  "currency": "EUR | '' for portfolio",
  "multi_currency": false,
  "generated_at": "ISO",
  "groups": [
    {
      "domain": "cost",
      "kpis": [
        {"code": "cpi", "label": "Cost Performance Index", "value": "0.97",
         "unit": "ratio", "status": "amber", "source_record_count": 42,
         "breakdown": {...}, "drill_url": "/project-controls/drill/cpi?project_id=..."}
      ]
    },
    {"domain": "schedule", "kpis": [ "spi", "milestone_slippage_days" ]},
    {"domain": "quality",  "kpis": [ "first_pass_yield", "copq", "ncr_open_count", "rfi_close_avg_days" ]},
    {"domain": "safety",   "kpis": [ "safety_trir", "incident_count" ]},
    {"domain": "risk",     "kpis": [ "risk_open_exposure", "risk_high_unmitigated_count" ]},
    {"domain": "changes",  "kpis": [ "change_order_ratio", "pending_variation_value" ]}
  ],
  "alerts": [ {"kpi_code": "cpi", "severity": "warning", "message": "..."} ]
}
```

`status` is derived server-side by banding `value` against the view's `thresholds_json` (or sane region-neutral defaults), so the client renders a traffic light without re-implementing the rule. Money KPIs carry `breakdown.currency` / `breakdown.by_currency` so the client groups by ISO code in portfolio mode, never blending (the existing `_portfolio_money_breakdown` contract).

## 6. Service logic: the connective tissue

This is the core of the feature. Both surfaces are orchestrators over existing engines.

### 6.1 Assistant grounding flow

When a user asks the assistant something like "is the rebar submittal for the basement approved, and what does CWICR say a comparable rate is", the existing `ERPChatService.stream_response` runs its agent loop. The model, seeing the upgraded system prompt, plans tool calls:

1. `search_submittals(query="basement rebar", project_id=...)` resolves through `unified_search_service(types=["submittals"], ...)`. That function (verified at `search/service.py:389`) runs both a vector ANN track over the `oe_submittals` collection and a SQL ILIKE track, fuses them with RRF, and returns hits with `id`, `score`, `title`, `snippet`, `payload`. The `oe_submittals` collection is populated by a new `SubmittalVectorAdapter` (see 6.2) whose `to_text` concatenates `title | spec_section | submittal_type | status`.
2. The model calls `get_submittal_detail(submittal_id=...)`, which (after `_require_project_access`) reads the `Submittal` row and returns spec_section, status, ball_in_court, date_returned, and `linked_boq_item_ids`. This is the bridge from the unstructured retrieval to the structured record.
3. The model calls `search_cost_catalog(query="reinforcement bar B500B", region="DE_BERLIN", din276_kg_prefix="33", project_currency="EUR")`. This routes to `costs.vector_adapter.search()` (verified at `costs/vector_adapter.py:514`), which applies the E5 `query:` prefix, runs vector search over `oe_cost_items`, post-filters by region/currency/DIN276 trade prefix, and falls back to SQL lexical search when the vector extra is missing, so it always returns real CWICR codes with rate, unit, currency. This is the CWICR/pgvector grounding the brief asks for, and it is a hard upgrade over the current keyword-only `search_cwicr_database`.
4. The model writes its answer, quoting each hit with its score and snippet (the system prompt already mandates provenance).

The connective insight: a single question fans out across submittals, the structured submittal record, BOQ links, and the priced CWICR catalogue, then comes back as one grounded answer. Cross-module retrieval is exactly what `unified_search_service` plus the per-module adapters already enable; we are adding the two missing adapters (RFI, submittal) and wiring the cost-vector adapter into a tool so the catalogue grounding uses semantic recall, not just ILIKE.

For drafting, the new `submittal_rfi_assistant` agent registered via `ai_agents.register_agent` uses `AgentRunner` (the ReAct loop in `ai_agents/base.py`). Its tools are the read-only grounded set plus `draft_rfi` and `summarise_submittal`, which are `FunctionTool` wrappers that compose retrieved context into a markdown draft and return text only. Nothing is written to `rfi` or `submittals` tables by the agent. The draft, its `grounded_refs_json`, and the `agent_run_id` are persisted to `oe_project_controls_drafted_artifact`; the human reviews it in the UI and, on confirm, `POST /drafts/{id}/accept` applies it through the RFI/submittal service and stamps `accepted_by`/`accepted_at`. This honours the AI-augmented-human-confirmed principle and the confidence-score expectation (the hit scores are the confidence signal surfaced in the draft).

### 6.2 New vector adapters (the missing grounding inputs)

Two tiny adapters, each implementing the `EmbeddingAdapter` protocol (`collection_name`, `module_name`, `to_text`, `to_payload`, `project_id_of`), exactly like `erp_chat/vector_adapter.py` and `costs/vector_adapter.py`:

- `rfi/vector_adapter.py` -> `oe_rfis`. `to_text = subject | question | discipline | official_response`. `to_payload` carries rfi_number, status, discipline, cost_impact, project_id. `project_id_of` returns `RFI.project_id`.
- `submittals/vector_adapter.py` -> `oe_submittals`. `to_text = title | spec_section | submittal_type | status`. `to_payload` carries submittal_number, spec_section, status. `project_id_of` returns `Submittal.project_id`.

Each is hooked into the event bus like every other module (the ~5-line pattern described in `vector_index.py`): subscribe to `rfi.*.created`/`updated` and `submittals.*.created`/`updated`, call `index_one`. Both new collection names are added to `ALL_COLLECTIONS`, `COLLECTION_LABELS`, and the `search/service` type map so `search_anything` and the global Cmd+K search pick them up for free. Each module's router mounts the shared `create_vector_routes(...)` (the same factory erp_chat uses at the bottom of its router) so reindex/status come for free.

### 6.3 Controls dashboard aggregation flow

The `GET /project-controls/snapshot` service method is the join. It does NOT re-query each module directly; it calls the already-built `bi_dashboards.kpis.compute(code, session, project_id=..., period_start=..., period_end=...)` for each code in the executive spine, in parallel via `asyncio.gather`. Each KPI formula internally fans out to its own source module with graceful degradation (the `ImportError`/`Exception` -> `Decimal("0")` pattern), so the snapshot works even when, say, the carbon module is uninstalled.

The spine is:

| Domain | KPI codes | Source modules (via existing formulas) |
|--------|-----------|-----------------------------------------|
| Cost | `cpi`, `cv`, `eac`, `vac` | `_evm_snapshot` over tasks + finance + procurement + projects |
| Schedule | `spi`, `sv`, `milestone_slippage_days` (new) | tasks (EVM) + schedule (new milestone formula) |
| Quality | `first_pass_yield`, `copq`, `rfi_close_avg_days`, `ncr_open_count` (new) | inspections, ncr, rfi |
| Safety | `safety_trir`, `incident_count` (new) | safety |
| Risk | `risk_open_exposure` (new), `risk_high_unmitigated_count` (new) | risk |
| Changes | `change_order_ratio`, `pending_variation_value` (new) | changeorders, variations |

The new KPIs are added to `bi_dashboards/kpis.py` as `@register_kpi(...)` formulas (so the BI dashboards, alerts and reports gain them too), each following the established money-honest pattern:

- `risk_open_exposure` (unit currency, category risk): sums `Risk.impact_cost` (string -> `_to_decimal`) over `oe_risk_register` where `status` not in (closed, mitigated, accepted), converting per-project via `_amount_in_base` / `_project_currency_and_fx`, per-currency bucketed in portfolio mode via `_portfolio_money_breakdown`. Breakdown includes count and a probability-weighted exposure variant.
- `risk_high_unmitigated_count` (unit count): counts rows where `impact_severity` in (high, very_high, critical) and `mitigation_strategy` empty. Mirrors the `project_intelligence` collector's risk gap.
- `ncr_open_count` (unit count, quality): counts `oe_ncr_ncr` where `status` not in (closed, resolved, verified).
- `incident_count` (unit count, safety): counts `oe_safety` incidents in the period (complements the rate-based `safety_trir`).
- `pending_variation_value` (unit currency, changes): sums `VariationRequest.estimated_cost_impact` where status in (draft, submitted, under_review), converting via `Project.fx_rates`, per-currency in portfolio mode. Distinct from `change_order_ratio` which uses signed/approved change orders.
- `milestone_slippage_days` (unit days, schedule): max positive delta between `Activity.end_date` and its baseline finish, sourced from `schedule.Baseline` versus current activities (the `project_intelligence` collector already reads `oe_schedule_baseline`). Region-neutral: pure date arithmetic on ISO string columns parsed with the existing `_parse_date`.

Each new formula registers a drill-down provider via `register_kpi_records(code)` returning the underlying rows (e.g. the open risks, the pending variations), so `GET /project-controls/drill/{kpi_code}` and the BI dashboard drill-down both work. The drill response is then enriched in the project_controls service with cross-module deep-link URLs (e.g. a pending-variation row gets `/variations/{id}`, an open-risk row gets `/risk?id=...`) so a click on the dashboard jumps straight to the source record. This is the connective tissue: one screen, six domains, every number traceable back to the owning module's detail page.

Status banding: the service compares each KPI's `value` against the active `ControlsView.thresholds_json` (or region-neutral defaults: CPI/SPI amber<0.95 red<0.90, TRIR amber>1.0 red>3.0, change_order_ratio amber>5% red>10%, etc.) and stamps `status` green/amber/red. Defaults live in a `project_controls.thresholds` constant so partner packs can override them.

A `controls_executive` dashboard is added to `bi_dashboards/seed.py` `_DEFAULT_DASHBOARDS` (scope role, role_ref admin) wiring kpi_card and line_chart widgets to the spine codes, so the existing BI dashboards page also renders the executive board and the existing alert engine can fire on the new KPIs.

### 6.4 How the two halves connect to each other

The assistant gets a `get_controls_snapshot` read tool that calls the project_controls snapshot service, so a user can ask "how is project X doing" and the assistant answers from the same numbers the dashboard shows, then offers to drill (e.g. "your CPI is 0.91, the three biggest cost variances are ..."). This closes the loop: the dashboard is the glance, the assistant is the conversation, both over one source of truth.

## 7. Frontend

TypeScript, React, Zustand for local UI state, React Query for server state, Tailwind, per the frontend conventions. Existing feature folders confirmed: `frontend/src/features/erp-chat`, `frontend/src/features/bi-dashboards`, `frontend/src/features/project-intelligence`, `frontend/src/features/ai-agents`.

### 7.1 Assistant

No new feature folder for chat itself. The existing `erp-chat/full-page` (ChatFullPage, left MessageThread/ToolCallCard, right DataPanelRouter + renderers) and `FloatingChatPanel` already render tool results. We add:

- Three new renderer components under `erp-chat/full-page/right/renderers`: `SubmittalsResult.tsx`, `RFIsResult.tsx`, `CostCatalogResult.tsx`, keyed off the `renderer` field the new tool handlers emit (`semantic_search` for the search tools, plus `submittal_detail`, `rfi_detail`). Each renders the hits as cards with score badge, snippet, and a deep link to the owning module page.
- A `DraftReviewDrawer.tsx` (can live in `ai-agents` since the agent runs there) that shows the agent's draft, the grounded refs with scores, and Accept / Edit / Discard, calling `POST /project-controls/drafts/{id}/accept`.

The user surfaces the assistant exactly where it is today (floating button on every page, full-page route), now answering submittal/RFI/spec questions with cited cost and document evidence.

### 7.2 Controls dashboard

New feature folder `frontend/src/features/project-controls`:

- `ProjectControlsPage.tsx` - the route component. A project selector (or "Portfolio") at the top, then six domain panels (Cost, Schedule, Quality, Safety, Risk, Changes) each rendering KPI tiles.
- `ControlsTile.tsx` - one KPI: label, value formatted by unit (currency formatter honouring `breakdown.currency`, ratio, percent, days, count), traffic-light from `status`, sparkline from KPI history, and a click that opens the drill.
- `DrillDrawer.tsx` - opens on tile click, fetches `GET /project-controls/drill/{kpi_code}`, renders the underlying rows with their cross-module deep links.
- `MultiCurrencyBadge.tsx` - when `multi_currency` is true, renders the per-currency breakdown instead of a blended total (reusing the existing money-grouping convention).
- `api.ts` - React Query hooks: `useControlsSnapshot(projectId, period)`, `useControlsDrill(kpiCode, projectId)`, `useControlsViews`, `useSaveControlsView`.
- `index.ts`, co-located `__tests__`.

State: server data via React Query (snapshot cached with a short stale time matching the snapshot dashboard); the active project, period and selected view in a small Zustand store. The page is added to the router and sidebar via `ROUTE_MODULE_KEY` so the role-based onboarding presets can gate it like every other module.

## 8. Reuse summary (verified in the code)

| Reused asset | File | What we build on it |
|--------------|------|---------------------|
| `ERPChatService.stream_response` SSE agent loop | `erp_chat/service.py:238` | Host for the new grounded tools, unchanged |
| `TOOL_DEFINITIONS` / `TOOL_HANDLER_MAP` / `TOOL_PERMISSIONS` / `_require_project_access` | `erp_chat/tools.py` | Add 5 tools following the identical contract |
| `unified_search_service` (vector + SQL + RRF) | `search/service.py:389` | RFI/submittal/document retrieval for the assistant |
| `costs.vector_adapter.search` (E5 `oe_cost_items` + SQL fallback) | `costs/vector_adapter.py:514` | The CWICR/pgvector grounding tool |
| `EmbeddingAdapter` protocol + `index_one` + `create_vector_routes` | `core/vector_index.py`, `core/vector_routes.py` | Two new adapters (RFI, submittal) in ~30 lines each |
| `AgentRunner` / `Agent` / `register_agent` / `global_tool_registry` / `FunctionTool` | `ai_agents/base.py` | The submittal/RFI/spec drafting agent |
| `bi_dashboards.kpis` registry: `register_kpi`, `compute`, `benchmark`, `drilldown`, `register_kpi_records`, `_evm_snapshot`, `_project_currency_and_fx`, `_amount_in_base`, `_portfolio_money_breakdown`, `_parse_date` | `bi_dashboards/kpis.py` | Add 6 new KPIs that plug straight into the shared registry, currency-honest |
| `bi_dashboards.service` render/evaluate/drill + snapshot caching | `bi_dashboards/service.py` | Reused by the seeded `controls_executive` dashboard |
| `bi_dashboards.seed._DEFAULT_DASHBOARDS` | `bi_dashboards/seed.py` | Add the `controls_executive` preset |
| `project_intelligence.collector` parallel per-domain isolated-session pattern | `project_intelligence/collector.py:970` | Pattern for the snapshot fan-out (gather over per-KPI compute) |
| `verify_project_access`, `RequirePermission`, `CurrentUserId`, `SessionDep` | `app/dependencies.py` | Project scoping + RBAC on every new endpoint |
| `permission_registry.register_module_permissions` | `core/permissions.py` | `project_controls.*` permissions |
| `GUID`, `Base` | `app/database.py` | New tables |
| Existing FE: erp-chat renderers, bi-dashboards page, project-intelligence components | `frontend/src/features/*` | Host the new renderers + the new controls feature |

## 9. Phasing

Effort in engineer-days. The MVP is end-to-end with no stubs: a grounded assistant that answers submittal/RFI/spec questions with CWICR-priced evidence, and a controls dashboard that shows the real six-domain spine for a project and the portfolio.

### MVP core (no stubs) - 11 days

- **A1. CWICR-vector grounding tool** (1.5d): add `search_cost_catalog` tool to `erp_chat/tools.py` routing to `costs.vector_adapter.search` with region/currency/DIN276 args; keep `search_cwicr_database` as fallback; fix the `_parse_str` bug (R1); upgrade the system prompt; tests.
- **A2. RFI + submittal adapters and search tools** (2d): two `EmbeddingAdapter`s, event-bus indexing hooks, two new collection constants in `vector_index.py`, `search_rfis` / `search_submittals` / `get_rfi_detail` / `get_submittal_detail` tools, vector routes mounted, backfill on startup; tests.
- **D1. New KPIs in the shared registry** (3d): `risk_open_exposure`, `risk_high_unmitigated_count`, `ncr_open_count`, `incident_count`, `pending_variation_value`, `milestone_slippage_days`, each with a drill-down provider, currency-honest, graceful-degradation; unit tests per KPI.
- **D2. `project_controls` module** (2.5d): manifest, permissions, `oe_project_controls_view` + `oe_project_controls_drafted_artifact` models, alembic, repository, service `snapshot()` (parallel compute + status banding + per-currency), router (`/snapshot`, `/views` CRUD, `/drill`), `controls_executive` dashboard added to bi seed; tests.
- **F1. Controls frontend** (2d): `project-controls` feature folder, snapshot page, tiles, drill drawer, multi-currency badge, React Query hooks, sidebar/route wiring; vitest.

### Phase 2: drafting agent and accept loop - 5 days

- **A3. `submittal_rfi_assistant` agent** (3d): register the agent, `draft_rfi` and `summarise_submittal` text-only tools, persist drafts to `oe_project_controls_drafted_artifact`, `POST /drafts/{id}/accept` applying to the target via the RFI/submittal service; tests including the human-confirm path.
- **F2. Draft review UI** (1.5d): `DraftReviewDrawer`, accept/edit/discard, cited-refs display; vitest.
- **A4. `get_controls_snapshot` assistant tool** (0.5d): the assistant reads the same snapshot the dashboard shows; test.

### Phase 3: deeper fidelity - 6 days

- **D3. Saved views, thresholds editor, alerts on new KPIs** (2d): thresholds editor UI, default-view selection, confirm new-KPI alert rules fire through the existing `AlertRule` engine.
- **D4. Trend and benchmark on the controls tiles** (1.5d): wire `KPIValue` history sparklines and `kpis.benchmark` percentile onto each tile.
- **A5. Submittal/RFI cross-references and impact rollup** (1.5d): assistant can answer "which open RFIs have a cost impact and how much" by combining `get_rfi_detail` with the variations/change KPIs.
- **P1. Partner-pack extension points** (1d): document and wire the threshold-default and dashboard-preset override hooks for region packs.

### Region-neutral core and partner-pack extension points

The MVP is deliberately region-neutral. Status thresholds, KPI selection, and the dashboard preset are all data, not code: `ControlsView.thresholds_json`, `kpi_codes_json`, and the `controls_executive` seed. Region-specific behaviour layers on via the existing partner-pack mechanism (entry-point group `openconstructionerp.partner_packs`):

- **US (AIA G702/G703)**: a pack can register an additional `controls_executive_us` dashboard preset emphasising schedule of values, retainage and stored materials, and supply `change_order_ratio` thresholds tuned to AIA practice. The CWICR grounding already filters by region (e.g. `US_*`) and currency (USD), so the assistant returns RSMeans-style US rates without core changes.
- **DACH (DIN 276)**: the `search_cost_catalog` tool already accepts `din276_kg_prefix` for trade-aware filtering; a DACH pack supplies KG-band thresholds and a Kostengruppen-grouped variant of the cost panel.
- **UK (JCT)**: a pack supplies variation/change thresholds aligned to JCT valuation cycles and an alternative `pending_variation_value` banding.

No region logic ships in core. Each pack overrides `project_controls.thresholds` defaults and optionally adds a dashboard preset, exactly as the existing packs already override onboarding presets and cost databases.

## 10. Risks and edge cases

- **R1 (real bug to fix in MVP):** `erp_chat/tools.py` `_generic_collection_search` and `handle_search_anything` call `_parse_str(args, "query", required=True, max_len=500)`, but `_parse_str(raw, field_name, *, required, max_length)` expects the raw value first and has no `max_len` kwarg. As written this passes the whole `args` dict as `raw` and raises a `TypeError` on the unexpected `max_len`. The existing semantic tools are effectively broken on every call. Fix to `_parse_str(args.get("query"), "query", required=True, max_length=500)` and cover with a test. This must be fixed because the assistant grounding tools sit on the same path.
- **R2 Vector backend optional:** LanceDB/Qdrant may be absent (`pip install` without the `[vector]` extra). The cost adapter already falls back to SQL lexical; the new RFI/submittal search must degrade the same way (the two-track `unified_search_service` already runs a SQL ILIKE track, so this is covered as long as the SQL track knows the new collections' source tables). The controls dashboard does not depend on vectors at all.
- **R3 Empty embeddings on fresh install:** new collections start empty; the startup backfill must index existing RFI/submittal rows, and the SQL track covers the window before backfill completes.
- **R4 Currency blending:** the absolute rule (within-project FX convert, across-portfolio group by ISO code, never sum mixed currencies) must hold for every new money KPI. We reuse `_amount_in_base` and `_portfolio_money_breakdown` exactly; tests assert a two-currency portfolio never collapses to one scalar.
- **R5 IDOR on new tools and endpoints:** every project-scoped tool calls `_require_project_access` (404-shaped) before reading; every endpoint uses `verify_project_access`. The drafting agent's tools re-verify via `__agent_context__` and never trust the LLM-supplied project_id. Tests assert a non-owner gets 404, not 403, and that a cross-tenant project_id leaks nothing.
- **R6 Agent must not auto-mutate:** the drafting agent produces text only; domain rows change only through the explicit human-confirm `accept` endpoint. No tool in the agent's `allowed_tools` writes to `rfi`/`submittals`. Test asserts a run leaves the RFI/submittal tables untouched.
- **R7 Snapshot latency:** computing the whole spine for the portfolio fans out per-KPI and each EVM KPI itself iterates all projects. We parallelise with `asyncio.gather`, reuse the bi snapshot cache where a KPI was just computed, and cap portfolio mode to active projects (the `benchmark`/portfolio helpers already iterate `select(Project.id)` only). For very large portfolios the snapshot is paginated by project and the heavy EVM rollup is cached on `KPIValue` via the existing persist path.
- **R8 KPI graceful degradation:** an uninstalled source module must not 500 the snapshot. Every new formula uses the established `try/except ImportError -> Decimal("0"), source_record_count=0` pattern, and the snapshot renders a "no data" tile rather than failing.
- **R9 Hallucinated citations:** the assistant must only cite hits actually returned by the tools. The system prompt mandates quoting hit scores and snippets; the draft persists `grounded_refs_json` so a reviewer can verify provenance, and the UI renders the score so low-confidence matches are visible.
- **R10 Date columns are strings:** schedule/finance/variation dates are ISO `String`. All date math uses the existing `_parse_date` helper (handles `YYYY-MM-DD` and full ISO), never `isinstance(value, date)`.
- **R11 Thresholds direction:** banding must know whether higher or lower is worse per KPI (CPI lower is worse, TRIR higher is worse). The `thresholds_json` carries an explicit `direction`; defaults encode it per code.

## 11. Test plan

Backend uses the per-module temp-sqlite pattern: `tests/conftest.py` sets `DATABASE_URL`/`DATABASE_SYNC_URL` to a temp SQLite file before any `from app...` import, and module suites may self-redirect with their own temp file. New tests live under `backend/tests/modules/project_controls/` (with a `conftest.py` mirroring the existing per-module ones) and extend `backend/tests/modules/erp_chat/`, `rfi/`, `submittals/`, `ai_agents/`, `bi_dashboards/`.

Backend pytest:

- KPI formulas: for each of the 6 new KPIs, a single-project case with seeded rows asserts the exact `value`, `unit`, `source_record_count` and breakdown; a portfolio case with two currencies asserts per-currency bucketing and no blending; an empty/uninstalled case asserts `Decimal("0")` and `source_record_count=0`. Drill-down providers assert the right rows come back.
- Snapshot endpoint: seed a project across all six domains, assert `/snapshot` returns all groups, correct `status` banding against default and custom thresholds, correct currency, and drill URLs; assert portfolio mode (`project_id` omitted) aggregates and flags `multi_currency`.
- RBAC/IDOR: non-owner gets 404 on `/snapshot?project_id=...` and on `/drill`; owner and admin succeed; views CRUD enforces ownership (404 on miss).
- Assistant tools: `search_cost_catalog` returns real CWICR hits (with vector backend stubbed off, via the SQL lexical fallback so the test runs without the `[vector]` extra); `search_submittals`/`search_rfis` return seeded rows; `get_*_detail` enforces `_require_project_access`; the R1 fix is covered by a test that the semantic tools no longer raise `TypeError`.
- Vector adapters: `to_text`/`to_payload`/`project_id_of` for RFI and submittal adapters, and that the event-bus hook calls `index_one` without raising when the backend is absent.
- Drafting agent: a scripted `LLMBridge` mock (the `ai_agents` framework already supports this) drives a run that calls the read tools and emits a draft; assert the run persists steps, the draft is recorded with grounded refs, and the RFI/submittal tables are unchanged; assert `accept` applies the draft and stamps `accepted_by`.

Frontend vitest (co-located `__tests__`):

- `ControlsTile` renders the right traffic-light per status, formats currency/ratio/percent/days/count correctly, and shows the multi-currency badge when `multi_currency` is true.
- `ProjectControlsPage` renders six domain panels from a mocked snapshot and opens the drill drawer on tile click.
- `api.ts` hooks call the right endpoints with project/period params.
- New erp-chat renderers (`CostCatalogResult`, `SubmittalsResult`, `RFIsResult`) render hits with score badges and deep links from a mocked tool result, extending the existing `erp-chat/__tests__` approach.

Manual browser verification on the `:8000` server (the running dev backend serves the built frontend):

- Seed a demo project (the country-pack one-click seed already produces full demos), open `/project-controls`, confirm the six panels populate with real numbers, switch to Portfolio, confirm per-currency grouping, click a tile, confirm the drill drawer lists source rows and the deep links jump to the owning module page (e.g. a pending variation opens `/variations/...`).
- Open the floating assistant, ask a submittal/RFI question for the demo project, confirm the tool cards render submittal/RFI/CWICR hits with scores and that the answer quotes them; ask "how is this project doing" and confirm the snapshot-backed numbers match the dashboard.
- Run the drafting agent for an RFI, confirm the draft drawer shows grounded refs, accept it, and confirm the RFI/submittal record updated and an audit row exists.
- Confirm RBAC: a viewer-role account sees the dashboard read-only and cannot accept drafts; a cross-project id returns not-found, never another tenant's data.

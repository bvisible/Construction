# OpenConstructionERP Master Implementation Plan

Author: DataDrivenConstruction
Status: the single plan we follow for the nine connective-tissue features
Source designs: docs/strategy/impl/01 through 09, grounded in docs/strategy/COMPETITIVE_FEATURE_ANALYSIS.md

This is the master plan that sequences and groups the nine feature designs into a single buildable program. It does not restate every design. Each feature has a point-by-point step list and a pointer to its full design doc. The theme across all nine is the one the competitive analysis lands on: we already own the modules, the differentiated work is connecting them into one system of record, not adding more modules.

The whole program is region-neutral at the core. Region behaviour (US AIA G702/G703, DACH DIN 276, UK JCT, NEC, FIDIC) is layered through the existing partner-pack entry-point mechanism, never branched into core. No feature uses IfcOpenShell or native IFC parsing; BIM and CAD data come only through the DDC cad2data canonical format, and BCF stays an I/O format used by nobody in this program. Every phase listed is shippable with no stubs.

---

## 0. Decisions locked (2026-06-01)

The founder confirmed the four open decisions from section 7:

1. Execution order: dependency order. Cost spine (01) first, then the financial stack, the three independent features (06, 07, 08) in parallel, synthesis surfaces (09) last.
2. Release cadence: incremental. Shippable, browser-verified releases (v6.4, v6.5 and onward), grouped by dependency.
3. Depth per feature: maximal fidelity on the first pass. Each feature is built through all its phases (the Full days column in section 1), to full standards-compliance, before it is considered done. We do not ship an MVP slice and defer the rest. This supersedes the MVP-first framing in sections 3 and 5 wherever they differ.
4. Region focus: region-neutral core plus partner packs. US AIA, DACH DIN, UK JCT behaviour is layered through the partner-pack entry-point mechanism, never branched into core.

Resulting release grouping (maximal fidelity, dependency-ordered, incremental):

- v6.4: 01 cost spine, full (13d). Independent lane starts in parallel: 06 submittals/RFI full (11d), 07 version compare full (17d), 08 field PWA full (20d).
- v6.5: 02 pay apps full (23d) and 03 budget cockpit full (21d), both depend on 01 only and run in parallel.
- v6.6: 04 auto EVM full (19d) and 05 5D cockpit full (18d).
- v6.7: 09 AI assistant + controls dashboard full (22d), plus any independent-lane depth not yet shipped.

Calendar time per release is the longest parallel lane plus its review and verification, not the sum of the features in it. Every cut stays browser-verified with no stubs.

---

## 1. The nine features at a glance

| ID | Feature | Owner module | Depends on | MVP days | Full days |
|----|---------|--------------|------------|----------|-----------|
| 01 | Estimate-to-budget-to-procurement cost spine | costmodel (extended) | none | 6 | 13 |
| 02 | Payment applications / progress billing | contracts (extended) | 01 | 8 | 23 |
| 03 | Unified budget cockpit | costmodel (extended) | 01 | 7 | 21 |
| 04 | Auto-derived earned value (EVM) | new oe_auto_evm | 01, 03 | 6 | 19 |
| 05 | True 5D cockpit (BIM to BOQ to activity to cost) | costmodel (new sub-surface) | 01 | 6 | 18 |
| 06 | Submittals and RFI through approval routes + CDE linkage | submittals, rfi, new doc_links | none | 4 | 11 |
| 07 | Drawing / document version compare with overlay | new compare module | none | 6 | 17 |
| 08 | Offline field PWA | field_diary (extended) | none | 9 | 20 |
| 09 | AI assistant grounded in CWICR + controls dashboard | erp_chat, ai_agents, new project_controls | 01, 03, 04 | 11 | 22 |

MVP-core total across all nine: 63 days. Full-fidelity total: 164 days. The plan ships MVP cores first and deepens later, so value lands early and each release is browser-verified.

---

## 2. Dependency-ordered execution sequence

The cost spine (01) is the keystone. It introduces the one stable cost-line identity that the financial features read, so it must land first and clean. After it, the financial stack builds in dependency order. Three features have no dependency and run in parallel from day one. The two synthesis surfaces (AI and the controls dashboard, 09) come last because they read everything the earlier features produce.

```
                01 cost spine  (keystone, depends on nothing)
                 |        |        |
        +--------+        |        +-----------------+
        |                 |                          |
   02 pay apps      03 budget cockpit          05 5D cockpit
   (needs 01)        (needs 01)                 (needs 01)
                          |
                     04 auto EVM
                     (needs 01 and 03)
                                                   09 AI + controls
                                                   (needs 01, 03, 04)

   independent lane, can run from day 1 in parallel with everything:
        06 submittals/RFI      07 version compare      08 field PWA
        (no dependency)        (no dependency)         (no dependency)
```

Rules the sequence respects, taken from each design's depends_on:

- 01 first and alone enough to stabilise. It is the only feature with no upstream and the only one three others sit on. Treat its Phase 1 as a hard gate before 02, 03, 05 start their dependency-bearing work.
- 02, 03, 05 each depend on 01 only. They can start as soon as 01 Phase 1 is merged, and they can run concurrently with each other because they touch different owner modules (contracts, costmodel cockpit surface, costmodel 5D surface). Coordinate the two costmodel features (03 and 05) so their migrations and router additions do not collide.
- 04 depends on 01 and 03. It reads the cost-account keying from 01 and the reconciled budget grain from 03, and it extracts the shared EVM formula helper that 03's forecast methods also lean on, so it starts after 03 Phase 1.
- 06, 07, 08 depend on nothing. They activate dormant infrastructure (approval_routes, the version chain, the offline queue and field auth) for high visible value and can be staffed in parallel from the start. This is exactly the parallelism the competitive analysis recommends in its step 4 and step 6.
- 09 depends on 01, 03 and 04. Its controls dashboard joins the cost spine and the auto EVM numbers, and its assistant reads the same snapshot, so it is the closing feature. Its assistant half (vector adapters, grounded tools) has no hard data dependency and could start earlier, but the dashboard half gates the release, so the whole feature lands last.

---

## 3. Milestone grouping mapped to releases

Each release is a shippable, browser-verified increment. A release contains complete MVP-core slices, never half a vertical. Deepening phases for an earlier feature land in a later release alongside the next feature's MVP, so every release moves the product forward on more than one front.

### v6.4 - The cost spine and the dormant-infrastructure wins

Lands the keystone plus the three independent features' MVP cores, because none of them wait on the spine and they activate visible infrastructure immediately.

- 01 cost spine, Phase 1 MVP (6d) and Phase 2 live commitment routing (3d).
- 06 submittals/RFI, Phase 1 MVP (4d) and Phase 2 CDE/BOQ linkage (3d).
- 07 version compare, Phase 1 MVP (6d).
- 08 field PWA, Phase 1 MVP (9d).

Release theme: a single cost identity now flows estimate to budget to committed, approval routing is finally live on submittals and RFIs, drawings can be compared revision to revision, and a site worker can capture offline on a phone and have it land on the desktop. Spine effort to a usable end-to-end state: 9 days including live commitment routing. Independent-lane effort: 22 days. These run concurrently, so calendar time is set by the longest lane (the field PWA at 9d plus its share of review and verification), not the sum.

### v6.5 - The financial cockpit and earned value

Builds the controls stack directly on the v6.4 spine.

- 03 budget cockpit, Phase 1 MVP (7d) and Phase 2 cost-account fidelity and progress claims (5d).
- 04 auto EVM, Phase 1 MVP (6d), which also extracts the shared EVM formula helper that 03 and finance route through.
- 02 pay apps, Phase 1 MVP (8d) and Phase 2 completion sourcing (5d).
- 07 version compare, Phase 2 CDE integration (3d).
- 08 field PWA, Phase 2 inspections capture and conflict review (6d).

Release theme: budget reconciles to committed and actual on one screen, EVM is computed from real data instead of typed in, and a certified progress claim mints a finance invoice with retention split out. Core financial effort: 26 days. With the carried deepening phases it is a substantial release; staff it across the financial team plus the field and documents owners finishing their phase 2 work.

### v6.6 - The 5D flagship and the synthesis surfaces

Lands the most defensible demo and the two surfaces that make the connected data legible.

- 05 5D cockpit, Phase 1 MVP (6d) and Phase 2 project overlay and colour map (4d).
- 09 AI + controls, MVP core (11d): grounded assistant plus the six-domain controls dashboard.
- 02 pay apps, Phase 3 retention and stored materials (4d).
- 04 auto EVM, Phase 2 higher-fidelity PV/EV/AC and scheduling (7d).

Release theme: select a BIM element and see its BOQ position, schedule activity and planned-versus-actual cost in one node; ask the assistant a submittal or RFI question and get a CWICR-priced, cited answer; open one executive board that joins cost, schedule, quality, safety, risk and change. Core effort for the two headline features: 27 days.

### v6.7 and onward - Depth, certificates and region packs

The remaining deepening phases, grouped so each still ships something whole.

- 02 pay apps, Phase 4 certificate export and region packs (6d).
- 03 budget cockpit, Phase 3 snapshots/movement/audit (4d) and Phase 4 partner-pack region extensions (5d).
- 04 auto EVM, Phase 3 region packs and reconciliation (6d).
- 05 5D cockpit, Phase 3 saved scopes and rollup persistence (3d) and Phase 4 deeper fidelity (5d).
- 06 submittals/RFI, Phase 3 default route templates, SLA badges and partner-pack templates (4d).
- 07 version compare, Phase 3 geometry-similarity carry-over (5d) and Phase 4 partner-pack extension points (3d).
- 08 field PWA, Phase 3 sync robustness and PWA hardening (5d).
- 09 AI + controls, Phase 2 drafting agent and accept loop (5d) and Phase 3 deeper fidelity, saved views, thresholds, trends, partner-pack hooks (6d).

Release theme: region certificate formats, time-aware audit snapshots, the human-confirmed AI drafting loop, and the partner-pack extension points populated for US, DACH and UK. Split v6.7 and v6.8 by capacity; keep each cut browser-verified.

---

## 4. Per-feature step lists

Each list is MVP-core first, taken from the feature's design. Steps follow the build order backend model and migration, schemas, repository, service, router, tests, frontend, browser verify. Deepening phases are summarised at the end of each feature; the full breakdown is in the design doc.

Migration ordering note that governs the whole program: four designs (01, 02, 06, 07) each independently propose the revision id `v3151` off the confirmed head `v3150_file_favorites`. That is a collision. The plan assigns a single linear chain in build order, restated in section 6. Each feature below names its assigned revision id, not the doc's placeholder.

### 01 - Cost spine (doc 01-cost-spine.md, keystone)

1. Backend models: add `ControlAccount` (oe_costmodel_control_account, self-FK tree mirroring boq.Position.parent_id) and `CostLine` (oe_costmodel_cost_line, the stable spine id carrying the estimate baseline and BOQ provenance) to costmodel/models.py.
2. Migration `v3151_cost_spine`, down_revision `v3150_file_favorites`, idempotent guards (_table_exists, _index_exists, _column_exists) because fresh SQLite create_all builds the tables first. Creates the two tables plus seven nullable linkage columns: cost_line_id and control_account_id on oe_costmodel_budget_line; cost_line_id on oe_boq_position, oe_procurement_po_item, oe_procurement_req_item, oe_contracts_contract_line; cost_line_ids JSON on oe_rfq_rfq. Column drops use batch_alter_table for SQLite.
3. Schemas: ControlAccount and CostLine create/update/response plus CostLineRollupResponse and SpineRollupResponse, money as Decimal-as-string via the existing _serialise_money serializer.
4. Repository: CostSpineRepository plus ControlAccount and CostLine repositories beside BudgetLineRepository; grouped aggregate queries per module (one budget aggregate, one PO-item-by-cost_line_id, one contract-line) to avoid N+1 on a 6k-position BOQ.
5. Service: CostSpineService with generate_from_boq (build account tree from position.classification, one cost line per costed position, skip section headers, inherit project currency, write cost_line_id back onto positions, auto-link existing budget lines, idempotent upsert on (project_id, code)), rollup_for_project, rollup_for_line, link/unlink. FX through the shared _amount_in_base and _project_fx_context so the spine cannot invent different FX math.
6. Router: all section-4 endpoints under /api/v1/costmodel/projects/{project_id}/spine/..., verify_project_access on every route, costmodel.read/write/manage permissions (no new keys). DELETE refuses with 409 plus linked counts.
7. Tests: test_cost_spine_service.py (tree from classification, one line per costed position, header skip, currency inheritance, idempotency, rollup FX math and mixed_currency flag, 409-on-delete) and test_cost_spine_api.py (create project, BOQ, budget, spine; assert budget lines linked; IDOR a second user gets 404). Per-module temp-sqlite-before-import pattern.
8. Frontend: Cost Spine tab on CostModelPage with CostSpinePanel (account-grouped grid: estimate/budget/committed/contracted/actual/variance), ControlAccountTree, GenerateSpineButton with created-count toast; api.ts client keyed React Query ["spine", projectId]. CostSpinePanel.test.tsx and GenerateSpineButton.test.tsx.
9. Browser verify on :8000: open a priced-BOQ project, generate budget then generate spine, confirm Estimate matches BOQ total; ?lang=de leaks no raw keys.

Phase 2 (3d): costmodel subscribers for procurement.po.issued and procurement.gr.confirmed folding committed/actual into the linked BudgetLine (boq_position_id fallback for legacy POs), populate po_item.cost_line_id in the auto-PO-from-award handler, CostLineRollupDrawer with cross-module deep links; after this the 5D dashboard and EVM reflect real procurement. Phase 3 (4d): contract-side wiring, RFQ solicitation, account status lifecycle, costmodel.spine.changed signal, partner-pack hooks (classification_standard label seeds DIN/CSI/NRM accounts, pay-app formatters consume the stable rollup shape).

### 02 - Payment applications (doc 02-payment-applications.md, depends on 01)

1. Backend model: PaymentApplication (oe_contracts_payment_application, 1:1 satellite of a progress claim holding approval_instance_id, approval_status, invoice_id, source_mode, certified_value as MoneyType) in contracts/models.py; add prior_completed_value, materials_stored_value, source_activity_id, source_boq_position_id to ProgressClaimLine; add default_approval_route_id and billing_format (default generic) to Contract.
2. Migration `v3153_payment_applications` (assigned chain id, down_revision `v3152_doc_links`), batch_alter_table for the SQLite column adds, all with server_default so existing rows backfill.
3. Schemas: PaymentApplicationCreate/Response/Decision and SourcePreviewLine, decimal-as-Decimal, dates-as-str.
4. Repository: PaymentApplicationRepository.
5. Service: create_payment_application (resolve route then contract default then newest active project route for progress_claim, start approval instance, transition claim draft to submitted), payment_application_view, refactor the shared persist-and-rollup tail into _apply_generated_result. Add progress_claim to approval_routes TARGET_KINDS (column already open String(64)).
6. Events: new contracts/events.py with two subscribers registered in on_startup. Bridge 1, approval_routes.instance.completed/rejected filtered on target_kind=progress_claim drives the existing idempotent claim FSM. Bridge 2, contracts.claim.certified mints exactly one finance Invoice (receivable for client, payable for subcontractor) with retention split out, idempotent on PaymentApplication.invoice_id and an invoice metadata token. Each subscriber opens its own async_session_factory session and swallows failures so it never rolls back the upstream transaction.
7. Router: lifecycle endpoints (POST/GET payment-application, list per contract, decision proxy) plus the certified-to-invoice path; reuse _verify_contract_access and _verify_claim_access (404, never 403).
8. Tests: test_payment_applications.py and an integration flow test. Cover sourcing math with exact Decimal assertions, bridge 1 (instance.completed drives claim to certified), bridge 2 (exactly one invoice, correct direction, no second invoice on re-delivery), Decimal-string regression, RBAC/IDOR (VIEWER denied, no-access 404), FSM 409 guards.
9. Frontend: PaymentApplicationDrawer (editable SoV completion grid, approval timeline, billing summary with finance invoice deep link), PaymentApplicationStatusBadge, claims-tab approval-status column. Co-located vitest.
10. Browser verify on :8000: open an active contract with an SoV, create a draft claim, promote to a pay application, approve through each route step, confirm the claim certifies and a finance receivable invoice with retention split appears via the drawer deep link.

Phase 2 (5d): source-from-schedule, source-from-cost-spine, source-preview with preview-then-commit and the cost-spine claim.paid subscriber contract. Phase 3 (4d): stored materials rolled into gross, retention ledger view, per-line retention overrides. Phase 4 (6d): generic certificate JSON builder plus a registered-builder extension point and reference packs for AIA G702/G703, DIN, JCT.

### 03 - Budget cockpit (doc 03-budget-cockpit.md, depends on 01)

1. Backend: add six nullable columns to oe_costmodel_budget_line (cost_account_code indexed, committed_source, actual_source, forecast_method, committed_locked, actual_locked) and a new CostLink table (oe_costmodel_cost_link, the join tying a contract/CO/invoice/claim source to a budget account and bucket, unique on project/source_module/source_type/source_id/bucket).
2. Migration `v3155_budget_cockpit` (assigned chain id), batch_alter_table for the column adds, indexes on (project_id, bucket) and (project_id, cost_account_code). Snapshot table deferred to Phase 3.
3. Schemas: CockpitResponse, CockpitRow, CockpitTotals, SourceRef, money as Decimal-as-string, mixed_currencies and missing_fx_rates surfaced.
4. Repository: extend with CostLink access; reuse the FX-aware aggregators.
5. Service: CockpitService.refresh_cockpit reading active contracts (total_value), approved change orders (get_summary), paid payable invoices; FX via the shared helpers; write committed/actual back to derived unlocked lines; forecast methods budget and committed_plus_etc; account mapping by category with the __unmapped__ catch-all so money is never silently dropped. Idempotent: a second refresh yields identical numbers and no duplicate CostLink rows.
6. Router: GET cockpit, POST refresh, GET sources, PATCH 5d/budget-lines extended with lock/source/forecast_method; costmodel.read for reads, costmodel.write for refresh/links, IDOR-404 by re-resolving the parent project from the row.
7. Tests: service rollup unit tests with stub repos (committed equals contract value, rises on approved CO, unchanged on submitted CO; actual bucketing; idempotency; locked/manual lines survive but still total; FX and missing-rate; three forecast methods; paid-claim-vs-invoice dedupe), router RBAC/scope test, migration round-trip.
8. Frontend: BudgetCockpit (reconciled table, refresh button with synced-count toast, expandable sources with deep links, period selector, mixed-currency hint), CockpitWaterfall, cockpitApi, new Cockpit tab on CostModelPage. BudgetCockpit.test.tsx.
9. Browser verify on :8000: open a project with contracts, an approved CO and a paid payable invoice, refresh, confirm committed equals contract plus approved CO and actual reflects the paid invoice, re-click for idempotency, lock a manual committed and confirm it survives refresh while still in totals, add a foreign-currency contract with no rate and confirm the mixed-currency hint instead of dropped or blended money.

Phase 2 (5d): honour cost_account_code on contract lines/CO items/invoice lines, paid progress claims as an actual source with invoice-vs-claim dedupe, manual links, eac_cpi forecast wired to calculate_evm, group-by-account view. Phase 3 (4d): oe_costmodel_cockpit_snapshot, movement column, waterfall, audit rows, optional auto-snapshot on month rollover. Phase 4 (5d): partner-pack region renderings (AIA continuation, DIN Kostengruppen, JCT interim valuation) with no change to rollup math.

### 04 - Auto EVM (doc 04-auto-evm.md, depends on 01 and 03)

1. Shared helper first: extract the EVM index/forecast formulas (SV/CV/SPI/CPI/EAC/VAC/ETC/TCPI with the TCPI at-or-over-budget clamp and the SPI proxy clamp) into app/core/evm.py and route finance, costmodel and auto_evm through it so the three calculators stop drifting. This is the single most valuable cleanup the feature buys.
2. Backend model: new oe_auto_evm module with AutoEvmDerivation (provenance and config: ev/pv methods, ac source, derived bac/pv/ev/ac as strings, inputs_json/warnings_json, link to the finance snapshot it wrote). The EVM numbers reuse oe_finance_evm_snapshot, no new EVM store.
3. Migration `vXXXX_auto_evm_init` (next free chain id at build time, additive only, no cross-module FKs so create_all ordering cannot fail).
4. Schemas: DeriveRequest, DerivationResponse (shared with preview), DerivationListResponse, AutoEvmConfig, MethodCatalogResponse.
5. Repository: AutoEvmRepository (list/create/get/latest-for-period).
6. Service: AutoEvmService.derive composing project FX once, BAC from costmodel budget lines (finance fallback), pv_method=budget_time_phased, ev_method=schedule_progress, ac_source=budget_actual with documented fallbacks; persist via finance-snapshot upsert per (project_id, period) plus an append-only derivation row inside a SAVEPOINT; then refresh the full_evm forecast. methods.py registry with register_ev_method/register_pv_strategy/register_ac_source for pack hooks.
7. Permissions: auto_evm.read/create/manage registered on startup.
8. Router: POST derive (persist), GET preview (persist=false, writes nothing), GET derivations, GET/PUT config, GET methods; verify_project_access on every path, no cross-project list.
9. Tests: unit (budget_time_phased PV, schedule_progress EV weighting precedence, the shared helper table-driven test, currency and missing-fx, all fallbacks, no_data status) and integration (derive writes exactly one snapshot and one derivation, re-derive upserts the snapshot but appends a derivation, preview writes nothing, RBAC, contract_certified EV equals compute_sov_status earned). Re-run existing finance/costmodel/full_evm/eac formula tests to prove the helper extraction is behaviour-preserving.
10. Frontend: AutoEvmPanel on CostModelPage next to EVMDashboard, DerivationProvenanceDrawer, api.ts whose derive mutation invalidates ["costmodel"] and ["full-evm"]. vitest for panel, drawer and invalidation targets.
11. Browser verify on :8000: open a seeded project, Derive now, confirm the existing Earned Value Analysis card and S-curve update without refresh, open the provenance drawer, switch to contract-certified and confirm EV matches the SOV earned total, confirm an empty project returns a clean no-data state.

Phase 2 (7d): baseline_phased and activity_cost_loaded PV, contract_certified and boq_progress EV, paid_invoices/contract_claims_paid/ledger AC, per-project config, opt-in idempotent scheduled derivation, costmodel snapshot mirroring, SPI/CPI breach notification. Phase 3 (6d): us_aia, dach_din, uk_jct packs registering extra methods at startup; core never branches on region.

### 05 - 5D cockpit (doc 05-five-d-cockpit.md, depends on 01)

1. Backend service first (MVP is reads only, no new persistence): CockpitService walking the existing link tables. bim to boq via oe_bim_boq_link plus oe_boq_quantity_link; to schedule via get_activities_for_bim_element plus boq_position_ids scan; to cost via BudgetLine plus Activity cost fields. Dedup budget lines by id so a line attributed to both a position and its activity is counted once. FX-correct rollup, SPI/CPI None when no cost.
2. Schemas: CockpitNode (anchor, bim, boq, schedule, cost rollup, link_provenance, warnings) and CockpitOverlayResponse in schemas_cockpit.py; currency resolved through _get_project_currency, never defaulted to EUR, mixed_currency flag when linked budget lines differ.
3. Router: router_cockpit.py with three anchored GET endpoints (element, position, activity) plus /cockpit/summary coverage KPIs; costmodel.read, single verify_project_access gates the whole cross-module join.
4. Tests: test_cockpit_walk.py (unioned positions/activities, dedup by id, FX rollup, SPI/CPI None with no cost), test_cockpit_api.py (three endpoints, summary, authz 404 for foreign user and missing project, viewer read-yes). Per-module temp-sqlite with FK-target models created after import.
5. Frontend: features/cockpit with CockpitNodePanel (four stacked BIM/BOQ/Schedule/Cost cards with provenance edges and cross-highlight) docked into the existing BIM viewer, standalone CockpitPage, CockpitCoverageCards, api.ts; reuses the existing features/bim 3D viewer, never a second viewer. Region-neutral cost-label formatter hook for AIA/DIN/JCT packs. Co-located vitest.
6. Browser verify on :8000: open a demo project with a BIM model plus linked BOQ plus schedule plus generated budget, click a linked element, confirm the four-card node with correct-currency planned-versus-actual.

Phase 2 (4d): /cockpit/overlay reusing ScheduleSnapshotService for the status map merged with cost-variance bands, CockpitOverlayLegend status-vs-cost toggle, element tinting, oe_costmodel_cockpit_link_cache with event-driven invalidation and an unlinked legend bucket. Phase 3 (3d): oe_costmodel_cockpit_scope saved scopes plus the Cockpit tab on the 5D page. Phase 4 (5d): time-phased overlay, what-if propagation via create_what_if_scenario, partner-pack rollup views, BCF export of over-budget/delayed elements through the permitted BCF I/O path.

### 06 - Submittals and RFI through approval routes (doc 06-submittals-rfi.md, no dependency)

1. Phase 1 is activation, no new table. Convenience endpoints POST/GET /submittals/{id}/route and POST/GET /rfi/{id}/route delegating to ApprovalRouteService, resolving project scope from the row, double-permission (submittals.update plus approval_routes.write, mirroring create_variation_from_rfi).
2. Subscribers: submittals/approval_subscribers.py and rfi/approval_subscribers.py registered from each module on_startup, wiring instance.completed and instance.rejected back into the existing idempotent approve_submittal and the manager-gated reject path; only ever drive transitions the FSM already allows. Record the instance id in row metadata for deep-linking. Engine returns 409 on a second pending workflow; the UI surfaces it as already-running with cancel-then-restart.
3. Tests: test_submittal_approval_link.py and test_rfi_approval_link.py (start creates a submittal-kind Instance and moves the submittal out of draft; reject moves to rejected with the step comment; full approval becomes approved idempotently on a duplicate event; 409 on a second concurrent workflow), router RBAC/IDOR.
4. Frontend: embed the existing ApprovalInstanceCard plus route picker into submittal and RFI detail screens with new api helpers and React Query keys. Co-located vitest.
5. Browser verify on :8000: open a submittal, start a workflow, approve each step to flip to approved and confirm a submitter notification, run the reject path.

Phase 2 (3d): new doc_links module (oe_doc_links_link polymorphic link from a submittal or RFI to a CDE container/revision, document or BOQ position; unique dedup; same-tenant target validation; dual-write boq_position into Submittal.linked_boq_item_ids), migration `v3152_doc_links` (assigned chain id, the first child of the spine migration), back-reference endpoint and CDE Referenced-by panel, Links sections on detail screens. After this /api/health module count increments by one with alembic_head_matches true. Phase 3 (4d): seed region-neutral default route templates per project so the picker is never empty, partner-pack templates and step labels (US AIA stages, DACH DIN stages, UK JCT chain), Step.sla_hours overdue badge plus a scan, an Approvals dashboard tile.

### 07 - Drawing / document version compare (doc 07-drawing-version-compare.md, no dependency)

1. Backend, the core blocker first: re-upload today overwrites Document.file_path in place so historical bytes are unretrievable. Add storage_key (String 500 nullable), mime_type, page_count to oe_file_version; extend FileVersionCreate and register_new_version to persist them (NULL defaults, no caller breakage); amend upload_document_revision to record the per-version path it already writes instead of losing it.
2. New table CompareSession (oe_compare_session, two FKs into oe_file_version, the physical link between the chain and the markup diff, cached change_summary JSON). Migration `v3154_drawing_version_compare` (assigned chain id) adds the three columns and the table.
3. Schemas: CompareCandidate (chain row enriched with download_url and page_count), CompareResultResponse with the change_summary shape (added/removed/carried markup buckets plus client-posted pixel changed_pct).
4. Repository and service: new compare module. candidates (chain enriched), diff (load both FileVersion rows, reject two ids not in one chain with 422 before the access check, single verify_project_access, bucket markups by file_version_id with identity carry-over via metadata supersedes pointer, NULL file_version_id attributed to current), sessions CRUD. compare.read/compare.write permissions.
5. New documents endpoint GET /documents/{id}/versions/{version_id}/download/ serving a specific version from storage_key, reusing download_document path-safety, legacy fallback to file_path for the current row only, 410 for unrecoverable historical bytes. Lazy backfill of the current row storage_key on first candidates read.
6. Tests: test_compare.py (register_new_version persists the three fields and leaves them NULL when omitted; diff rejects cross-chain ids 422; markup bucketing including NULL attributed to current; saved session round-trip; compare.write for persist and delete) and integration test_compare_download.py (base download returns OLD bytes, current returns NEW bytes, cross-tenant 404, legacy non-current 410).
7. Frontend: reuse the existing three-mode PdfCompare.tsx; add VersionPickerBar (two version selectors from useCompareCandidates, default base=previous compare=current), MarkupDiffOverlay (green added, red removed ghosted, grey carried), MarkupDiffList, a Markup diff toggle and Save comparison, deep links from RevisionsPanel. Co-located vitest.
8. Browser verify on :8000: open a multi-revision PDF, Compare from the Revisions panel, exercise overlay/diff/side-by-side, toggle Markup diff and verify colouring and counts, Save comparison and reopen the saved session, confirm a DWG offers no pixel compare and a pre-feature historical version shows the 410 message gracefully.

Phase 2 (3d): candidates joins oe_cde_revision for revision-code labels, Compare revisions in CDEHistoryDrawer, compare-saved entries in the documents activity timeline. Phase 3 (5d): geometry-similarity carry-over, server-assisted page alignment hint, flattened-PDF export via the report renderer. Phase 4 (3d): partner-pack read-only summariser registry for AIA scope-addition delta, DIN cost-group mapping, JCT variation reference.

### 08 - Offline field PWA (doc 08-field-pwa.md, no dependency)

1. Backend model: one new table oe_field_sync_op (server-side idempotency and audit ledger, unique on (session_id, client_op_id) so the queue drains safely more than once) in field_diary/models.py; add geo_lat/geo_lon to oe_inspections_inspection and field_source to oe_field_diary_entry (additive nullable).
2. Migration `vXXXX_field_pwa_sync` (next free chain id at build time, verify alembic heads, do not hardcode). Add oe_field_sync_op to the pre-create_all import list in main.py (the recurring fresh-install gotcha).
3. Schemas: FieldCapture envelope (client_op_id, captured_at, lat/lon/accuracy), FieldPunchCreate, FieldInspectionCreate, FieldCaptureResponse, FieldTodayResponse with server_time for clock-skew reconciliation.
4. Service: FieldSyncService.apply_op (idempotency check on (session_id, client_op_id) returns the prior result on a seen op, else dispatch into the existing punchlist/inspections/daily_diary/field_diary services forcing project_id from the session, record the ledger row, 409 to conflict, other 4xx to rejected). Field-to-office daily_diary subscriber on field_diary.entry.submitted appending a DiaryEntry with source_module and source_ref.
5. Router: today/, capture/photo/ (magic-byte gated), capture/punch/, capture/inspection/, sync/batch/ (max 50), sync/ops/, all on the existing field-session deps (RequirePinPlusMagicLink plus _require_field_module_grant), project_id read from the session not the URL, 404 not 403 on mismatch. These never touch the standard RequirePermission stack.
6. Tests: integration (idempotency, cross-project scope rejection, module-grant kill switch, PIN required, photo magic-byte gate, field-to-office diary bridge idempotent, inspection capture feeding create-defect) and FieldSyncService.apply_op unit tests with stubbed repos. Per-module temp-sqlite-before-import with APP_DEBUG.
7. Frontend: replace the FieldShellPage skeleton with a working bottom-nav shell mounting useFieldSync and OfflineBanner; FieldAuthPage PIN entry; FieldTodayTab; FieldCaptureFlow (camera, categorise, submit) with FieldPunchForm and FieldDiaryEntryForm; useFieldSync drain loop using field-session headers not the JWT; useFieldSessionStore; offlineStore version bump 1 to 2 with a fieldPhotos blob store. Extend offlineStore.test.ts plus submitFieldMutation and useFieldSync vitest.
8. Browser verify on :8000 (APP_DEBUG): admin creates a grant, request-magic-link returns dev token plus PIN, open /field/<token>, enter PIN, throttle to Offline, capture a punch with photo and a diary note, restore network, confirm both land on the desktop Punch List and Daily Diary with the photo in the Documents hub and the geotagged punch on the Geo Hub map, toggle offline/online twice to confirm no duplicate rows. Run qa-crawler against /field and i18n-sweep for new strings. Browser probes against the shared VPS run sequentially, never parallel.

Phase 2 (6d): capture/inspection feeding the existing create-defect/create-ncr bridges from the desktop side, conflict-review surface in FieldProfileTab reading sync/ops, Crew tab read-only, verify geo pins. Phase 3 (5d): exponential backoff, fieldPhotos 200 MB cap with oldest-dropped toast, captive-portal detection, resolve the self-destruct public/sw.js versus workbox question on :8000, surface the PWA install prompt on /field.

### 09 - AI assistant and controls dashboard (doc 09-ai-and-controls.md, depends on 01, 03, 04)

1. Fix the real R1 bug first: erp_chat/tools.py _generic_collection_search and handle_search_anything call _parse_str(args, "query", max_len=500) but the signature is _parse_str(raw, field_name, *, required, max_length), so every call raises TypeError. Fix to _parse_str(args.get("query"), "query", required=True, max_length=500) and cover with a test, because the new grounding tools sit on the same path.
2. Assistant grounding: add search_cost_catalog routing to the CWICR oe_cost_items E5 vector adapter (a hard upgrade over the keyword-only search_cwicr_database, kept as a SQL fallback); add RFI and submittal EmbeddingAdapters (oe_rfis, oe_submittals collections declared as constants), event-bus indexing, startup backfill of existing rows, and search_rfis/search_submittals/get_rfi_detail/get_submittal_detail tools with mounted vector routes. Each tool follows the existing {renderer, data, summary} contract and the 404-shaped _require_project_access gate. SQL ILIKE track covers the window before backfill and the no-vector-extra case.
3. Six new currency-honest KPIs into the shared bi_dashboards.kpis registry (risk_open_exposure, risk_high_unmitigated_count, ncr_open_count, incident_count, pending_variation_value, milestone_slippage_days), each with a drill-down provider and the try/except ImportError to Decimal('0') graceful-degradation pattern, FX-converted within a project and per-currency bucketed across the portfolio via _amount_in_base and _portfolio_money_breakdown. No migration: they register into KPI_FORMULAS and seed via bootstrap_system_kpis. Date math uses _parse_date, never isinstance on a string.
4. New project_controls module: manifest, permissions, oe_project_controls_view and oe_project_controls_drafted_artifact models, migration (next free chain id, server defaults on bool and JSON columns, no cross-module FKs), repository, service.snapshot (parallel kpis.compute via asyncio.gather plus status banding with explicit per-KPI direction plus per-currency), router (/snapshot, /views CRUD, /drill with cross-module deep-link URLs), seed controls_executive into bi_dashboards.
5. Tests: per-KPI value/unit/source_record_count/breakdown for a single project, a two-currency portfolio asserting per-currency bucketing with no blending, an empty/uninstalled case asserting Decimal('0'); snapshot groups, status banding against default and custom thresholds, drill URLs, portfolio multi_currency flag; RBAC/IDOR (non-owner 404 on /snapshot and /drill); assistant-tool tests including the R1-fix regression and search_cost_catalog returning real CWICR rows via the SQL fallback (runs without the [vector] extra); adapter to_text/to_payload/project_id_of and index_one-without-raising-when-backend-absent.
6. Frontend: project-controls feature folder (ProjectControlsPage, ControlsTile traffic-light, DrillDrawer, MultiCurrencyBadge, api.ts hooks, Zustand store, route and sidebar wiring via ROUTE_MODULE_KEY) plus three new erp-chat renderers (CostCatalogResult, SubmittalsResult, RFIsResult with score badges and deep links). Co-located vitest.
7. Browser verify on :8000: open /project-controls, confirm the six panels populate, switch to Portfolio and confirm per-currency grouping, click a tile and confirm the drill drawer with deep links; open the assistant, ask a submittal/RFI question and confirm tool cards render submittal/RFI/CWICR hits with scores and the answer quotes them; ask how is this project doing and confirm snapshot-backed numbers match the dashboard; confirm a viewer account is read-only and a cross-project id returns not-found.

Phase 2 (5d): register the submittal_rfi_assistant drafting agent with draft_rfi and summarise_submittal text-only tools (no domain mutation), persist drafts with grounded_refs_json and agent_run_id, POST /drafts/{id}/accept applying through the RFI/submittal service and stamping accepted_by, DraftReviewDrawer accept/edit/discard, a get_controls_snapshot assistant tool so the assistant answers from the same numbers as the dashboard. Phase 3 (6d): thresholds editor and default-view selection, AlertRule firing on the new KPIs, KPIValue sparklines and benchmark percentile, RFI cost-impact cross-reference, partner-pack threshold and dashboard-preset override hooks for US/DACH/UK.

---

## 5. Consolidated test strategy

Every feature ships with the same four-layer guard. The patterns below are repo conventions verified across the designs, so all nine features test the same way.

### Unit tests (service logic with stub repositories)

Construct the service with SimpleNamespace stub repos, the style in tests/unit/test_costmodel_service.py and test_full_evm_service.py. Assert exact Decimal values on all money math, never floats. The high-value unit cases per feature: spine generation idempotency and rollup FX (01); claim sourcing and the two bridges (02); cockpit rollup, dedupe and the three forecast methods (03); the shared EVM formula helper table-driven test plus PV/EV/AC method precedence and fallbacks (04); the cockpit walk dedup-by-id and SPI/CPI-None-with-no-cost (05); the approval subscriber driving only legal FSM transitions (06); markup bucketing and cross-chain rejection (07); FieldSyncService.apply_op idempotency (08); each new KPI value and per-currency breakdown plus the R1 regression (09).

### Integration tests (per-module temp SQLite before app import)

Set DATABASE_URL and DATABASE_SYNC_URL to a temp SQLite file before any `from app...` import, then Base.metadata.create_all the tables under test (importing FK-target models first where a feature spans modules, as in test_4d_api.py). Override get_session and get_current_user_id, seed a project owned by the test user, run against the ASGI client. publish_detached is shimmed synchronous in conftest so subscriber effects are observable immediately after an awaited call, which is how the event bridges in 01, 02, 06 and 08 are asserted. Every feature includes an IDOR case: a second user gets 404 (never 403) on the first project's resources. Re-run the existing finance/costmodel/full_evm/eac formula suites after 04's helper extraction to prove it is behaviour-preserving.

### Frontend vitest plus TypeScript

Co-located component and api tests following the existing patterns (POStatusPipeline.test.tsx for grids, the offlineStore and markups mocks for the PWA and compare). Assert money strings pass through without float rounding, mixed-currency banners render from mocked payloads, and mutations invalidate the right React Query keys (for example 04's derive invalidates costmodel and full-evm). Run `npx tsc --noEmit` clean on every frontend change; strict mode is on and a type error blocks the cut.

### Sequential browser verification on :8000

Run the dev backend with the factory (`python -m uvicorn app.main:create_app --factory ...`) and the frontend dev server proxying to it. Walk each feature's manual checklist from section 4 in a real browser, in sequence, never parallel against a shared server (concurrent Playwright probes stall the event loop and the local SQLite backend cannot survive more than three concurrent agents). Always include a `?lang=de` pass to confirm no raw i18n keys leak, and run the qa-crawler skill plus i18n-sweep where a feature adds a new surface (08 explicitly, others as they add routes). New strings we create are translated into all 26 non-English locales by the i18n-sweep skill.

### Regression guards

- Alembic round-trip: add each new table and column to tests/integration/test_migrations_roundtrip.py upgrade/downgrade. After every cut, /api/health must report alembic_head_matches true and the expected module count (06 and the new modules in 04, 07, 09 each increment it).
- Money rule guard: a two-currency fixture must never collapse to one scalar; convert within a project via fx_rates, group by ISO code across projects, keep missing-rate amounts in their own units and surface the code, never zero or blend.
- Shared-helper guard (04): the extracted app/core/evm.py is pinned by its own table-driven test and the three caller suites, so finance, costmodel and auto_evm cannot drift again.
- No-stubs guard: each MVP-core phase is end to end. A control with no backend, a number with no source, or a band-aid is a failed phase, not a shippable one.

---

## 6. Alembic ordering (the one cross-cutting decision the plan must make explicit)

Four designs independently propose revision id `v3151` off the confirmed head `v3150_file_favorites`. Alembic cannot have two revisions share an id or a down_revision without branching the history. The plan assigns one linear chain in build order. Each feature uses its assigned id, not the doc placeholder. Features 04, 08 and 09 add no relational table that collides on the immediate head, so they take the next free id at their build time (verify `alembic heads` first, never hardcode, per the VPS relative-DB gotcha in MEMORY).

```
v3150_file_favorites            (current head, do not touch)
  -> v3151_cost_spine                  (01, the keystone migration)
  -> v3152_doc_links                   (06 Phase 2, first child of the spine)
  -> v3153_payment_applications        (02)
  -> v3154_drawing_version_compare     (07)
  -> v3155_budget_cockpit              (03)
  -> vXXXX_auto_evm_init               (04, next free id at build time)
  -> vXXXX_field_pwa_sync              (08, next free id at build time)
  -> vXXXX_project_controls_init       (09, next free id at build time)
```

If two features are in flight at once (the v6.4 parallel lanes), the second to merge rebases its down_revision onto the first's head and renumbers, so the chain stays linear. All new migrations keep the idempotent guard pattern from v3150_file_favorites (_table_exists, _index_exists, _column_exists), because a fresh SQLite install boots the app and runs Base.metadata.create_all before alembic, so every create and add_column must be re-runnable, and every column add carries a server_default so existing rows backfill without a data migration (the v4.4.1 lesson). Every new model table also goes into the pre-create_all import list in main.py.

---

## 7. Open decisions

Four choices tune this plan. Each has a recommended default, already baked into sections 2 through 6, and a one-line note on what changes if you pick differently.

1. Execution order. Default: dependency order, cost spine first, then the financial stack, with the three independent features in parallel and the synthesis surfaces last. If instead you want fastest visible wins first, pull 06, 07 and 08 (the dormant-infrastructure activations) into v6.4 ahead of even the spine and defer the financial stack a release; the spine still has to precede 02, 03, 04, 05.

2. Release cadence. Default: incremental releases (v6.4, v6.5, v6.6, then depth in v6.7 and onward), each a shippable browser-verified increment grouping whole MVP slices. If instead you want a single big bang, hold everything to one v7.0 cut; that delays all value to the end and concentrates regression risk into one release, which the no-stubs and sequential-verification guards make slow.

3. Depth per feature. Default: MVP-first then deepen, so each feature lands a working vertical and its fidelity phases come in later releases. If instead you want a few features fully finished before the next starts, complete each feature through Phase 4 before moving on; that delays the breadth of connected modules and pushes the 5D and controls demos later, weakening the "we connect every loop" positioning.

4. Region focus. Default: region-neutral core plus partner packs, US/DACH/UK behaviour layered through the existing entry-point mechanism with zero core branches. If instead a launch market needs one region native, build that pack's formatters earlier (pull the relevant Phase 3 or 4 work forward) while keeping the core neutral; do not branch region logic into core, because every feature's extension points are designed to keep it out.

---

## 8. Risks and cross-cutting concerns

These hold across all nine features and are non-negotiable.

- Project scoping and IDOR. Every endpoint resolves the owning project and calls verify_project_access (or, for the field PWA, reads project_id from the pinned field session), and returns 404 (never 403) on a cross-tenant miss. Detail routes that take only a child id resolve the row then verify access to its project. The AI agent re-verifies via __agent_context__ and never trusts an LLM-supplied project_id.

- Money and currency rules. Convert within a project through fx_rates, group by ISO currency code across projects, never blend mixed currencies into one scalar. Keep a missing-rate amount in its own units and surface the code with a mixed_currency flag, never zero it. Money is Decimal in, Decimal-as-string out. This is an established bug class in the repo (the cash-flow and Monte Carlo fixes, task #217) and every feature that touches money reuses the shared _amount_in_base and _portfolio_money_breakdown helpers rather than inventing FX math.

- Alembic ordering. One linear chain off v3150_file_favorites per section 6, no shared ids, idempotent guards, server defaults on every column add, new tables in the main.py pre-create_all import list. Verify alembic heads at build time; never hardcode a down_revision against a stale head.

- No IfcOpenShell, no native IFC. BIM and CAD data come only through the DDC cad2data canonical format. The 5D cockpit reads canonical oe_bim_element rows; version compare disables pixel overlay for DWG/RVT/IFC; BCF is permitted as I/O and used by nobody in this program except the optional 5D Phase 4 export, which goes through the permitted BCF path.

- No stubs, no band-aids. Each MVP-core phase is a complete vertical that writes a real row through an existing service and renders real data. A dead control, a hard-coded zero, or a feature behind a flag with no backend is a failed phase. The financial features in particular must not regress the parallel finance.ProjectBudget system: the spine and cockpit are additive and authoritative for the 5D dashboard and EVM, and converging the two budget tables is a separate later initiative explicitly out of scope here.

- Event-bridge idempotency. publish_detached is async in production and synchronous-shimmed in tests, so every subscriber effect (the spine commitment routing, the pay-app invoice mint, the submittal/RFI FSM drive, the field-to-office diary bridge) is idempotent against re-delivery and ordering. Subscribers open their own async_session_factory session and swallow failures so they never roll back the upstream transaction.

- Concurrency and performance. Additive SQL updates (committed_amount = committed_amount + delta) avoid lost updates on hot budget lines. Rollups use grouped aggregate queries per module, never N+1, on large BOQs. The 5D overlay bounds its Python-side JSON scan by project and falls back to the link cache. The controls snapshot fans out per KPI with asyncio.gather and caps portfolio mode to active projects.

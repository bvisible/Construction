# Remaining product backlog + competitive roadmap (TOP-30 and connective-tissue features)

# Handover Dossier - Remaining Roadmap Work (TOP-30 + connective-tissue features)

All paths are relative to the monorepo root `C:\Users\Artem Boiko\Desktop\CodeProjects\ERP_26030500`. Note the repo root is the PARENT of the `marketing-site` directory you may be dropped into; the strategy docs live at the root under `docs/strategy/`.

## 0. Read these first, in order

1. `docs/strategy/improvement-2026-06/PROGRAM_STATE.md` - the live resumable control file for the TOP-30 program. This is the most current roadmap tracker (updated 2026-06-04). Read it before anything else.
2. `docs/strategy/improvement-2026-06/01_sections_competitive_top30.json` - the authoritative ranked list of the 30 competitive-gap features, with rationale, effort, impact, competitors, plus a `top_coordination_improvements`, `critical_hacks_stubs` and `prioritized_waves` block.
3. `docs/strategy/improvement-2026-06/_triage_digest.json` - per-item status, remaining-work checklists, and exact file lists (the `items` list is keyed by `feature` text, fields are `status`/`effort`/`needs_migration`/`remaining`/`files`/`ui`/`test`).
4. `docs/strategy/improvement-2026-06/impl/item-NN-*.md` - deep per-item designs for the still-open TOP-30 items (12, 15, 16, 17, 21, 22, 23, 25, 27, 29, 30), plus `impl-leftover/` (13, 20) and `impl6/` (gap A-I cost-control gaps).
5. `docs/strategy/ROADMAP_STATE.md` and `docs/strategy/IMPLEMENTATION_PLAN.md` and `docs/strategy/impl/01..09-*.md` - the EARLIER nine connective-tissue feature roadmap. Partly superseded by the TOP-30 program (see Section 4); treat it as design reference, not the current tracker.
6. `docs/strategy/COMPETITIVE_FEATURE_ANALYSIS.md` - the positioning narrative behind both roadmaps.

## 1. CRITICAL version/branch state (verify before any release work)

There is a real branch/version split a fresh agent must understand:

- Current working branch is `feat/postgres-only`, HEAD `0c92042d2`. Both `backend/pyproject.toml` (line 3) and `frontend/package.json` (line 4) on this branch say version `6.8.0`.
- The published `v6.9.0` lives on a DIFFERENT branch `release-v6.9.0`, tag `v6.9.0` derefs to commit `a156067de`. That tag has `backend/pyproject.toml` version `6.9.0`.
- `git merge-base HEAD v6.9.0` returns HEAD itself, so v6.9.0 is AHEAD of the working branch: `release-v6.9.0` = `feat/postgres-only` plus seven commits (v6.8.1/6.8.2 desktop launcher fixes, `0162056cc` homepage i18n into 19 languages, `f0db76dc1` quality-push, `f0db76dc1`/`860e7b613` release commit, `a156067de` CI Node heap bump).
- Remote `main` is at `9e017014f` (a third pointer). So three refs diverge: working branch (6.8.0), release branch/tag (6.9.0), and remote main.

Action for the next agent: reconcile these before cutting v6.10. Do NOT assume the working tree is the published v6.9.0. Confirm which branch the founder wants as the base, and that any item-15/22 reporting work you build is layered on the chosen base. The TOP-30 PROGRAM_STATE was written against `feat/postgres-only` == remote main at `d1ede2f90` (now stale).

## 2. TOP-30 status: SHIPPED vs REMAINING

The TOP-30 program ran in six waves (Wave 1-6) and shipped a large batch as v6.8.0 (commit `89238c030`). Per the PROGRAM_STATE status table plus my code verification:

### SHIPPED (DONE), 18 items
- #1 Clash + validation lifecycle events into notifications/punchlist/NCR (commit f20c333f6, Wave 1)
- #3 Event-driven live EVM/KPI refresh, "Live" pill (Wave 2, 8bd83f676)
- #4 Bi-directional ERP/accounting connectors (file-based connector, registry, migration v3155, Wave 3)
- #5 Cross-project portfolio resource leveling, capacity heatmap (Wave 2)
- #6 Unified schedule dependency graph + completion guard (Wave 1)
- #8 Tendering vs Bid award reconciliation, idempotent PO (Wave 1)
- #9 Lien waiver automation + pay enforcement (migration v3154, Wave 3, 34e802714)
- #10 Commitment management: PO draft->approved->issued + budget sync (Wave 3, e0ebb1ac7)
- #11 Change Order AI draft + deterministic impact simulator (Wave 3, c921fb805)
- #13 LTIFR/TRIR computation (`safety/service.py:488-503`)
- #18 ML quantity extraction / symbol recognition - symbol-signature match shipped (`match_elements/symbol_signature.py`, `signature_match_service.py`, SymbolSuggestionPanel UI; v6.8.0)
- #19 Predictive schedule/cost risk analytics (`project_intelligence/forecast.py`, `risk/escalation.py`, ForecastInsightsPanel; v6.8.0)
- #20 Vendor/sub scorecards + prequal gating, event auto-decrement (migration v3158, Wave 3 + v6.8.0). Caveat: no scorecard display UI yet.
- #24 Risk<->task and schedule-slip<->risk auto-escalation (`risk/escalation.py`, v6.8.0)

### PARTIAL (foundation shipped, competitive feature incomplete), 4 items
- #14 Native offline-first mobile app: offline slice shipped (mutation queue, field service worker, useFieldSync). Native mobile shell still a stub - `frontend/src/features/field/FieldShellPage.tsx`.
- #15 Auto client/owner progress report (see Section 3 - this is next planned task, backlog #93)
- #22 Subcontractor portal invoice submission (see Section 3 - next planned task, backlog #93)
- These two (#15, #22) are explicitly named in PROGRAM_STATE as the remaining work for "a clean close".

### REMAINING (triaging, not yet built), ~9 items
Per the status table these are still "triaging" with no implementation landed:
- #2 Integrated mobile field time/attendance with payroll-to-job-cost pipeline (Wave 4, effort XL). Three modules count workforce in parallel (daily_diary.labour_count, fieldreports.workforce, resources.assignment) with no single source of truth and no labour-hours-to-cost flow.
- #7 AI photo intelligence: batch upload, EXIF/GPS georeferencing, auto-tagging, defect classification (Wave 4, L). `/photos` route does no AI extraction today.
- #12 ITP workflow with hold points and quality gates (Wave 5, M). Design at `docs/strategy/improvement-2026-06/impl/item-12-itp-hold-points-design.md`. QMS has ITP fragments only.
- #16 Semantic AI assistant over project documents, Procore-Assist equivalent (Wave 5, L). Design `impl/item-16-semantic-doc-assistant-design.md`. erp_chat is advisory only, global search is keyword based.
- #17 Auto drawing/BIM revision compare with cost impact (Wave 5, L) - one of the 4 fully-missing items. Design `impl/item-17-revision-compare-cost-design.md`. Verified: the only "compare" in markups is an owner-id check (`markups/router.py:622`), no visual diff exists. This is also connective-tissue feature 07.
- #21 ISO 19650 CDE suitability propagation, unify two transition validators (Wave 6, M). Design `impl/item-21-iso19650-cde-suitability-design.md`. CDE state machine exists; suitability_code does not propagate to the Documents index and a direct PATCH can bypass the gates.
- #23 Persistent clash profiles + multi-dimension grouping (Wave 5, M). Design `impl/item-23-clash-profiles-design.md`. Detection is per-run with no saved rule sets.
- #25 Digital handover / closeout package assembly (Wave 6, L). Design `impl/item-25-digital-handover-design.md`.
- #26 Equipment predictive maintenance and fleet utilization analytics (Wave 4, M). Equipment module already tracks hour_meter/telemetry/maintenance; missing ML failure forecasting and utilization analytics.
- #27 Compliance rule engine enforced at workflow gates with jurisdiction rule packs (Wave 6, M). Design `impl/item-27-compliance-gate-engine-design.md`. DSL exists but is not enforced at the workflow boundary; no ISO 19650/OSHA/IBC packs.
- #28 Model-based progress overlay in 3D viewer (Wave 4, L). BIM viewer and progress exist separately; no color-coded completion overlay.
- #29 No-code agent builder (Wave 6, XL). Design `impl/item-29-no-code-agent-builder-design.md`. Note an "AI agent builder" shipped in v6.7.0 per memory; verify overlap before building.
- #30 Takt / line-of-balance scheduling (Wave 6, M) - one of the 4 fully-missing items. Design `impl/item-30-takt-line-of-balance-design.md`. Schedule is Gantt-only.

(That is 13 items still "triaging" plus the 2 partials = the open backlog. The PROGRAM_STATE notes "0 done, 26 partial, 4 missing" was the pre-build triage count; many partials have since been pushed to DONE in the waves above.)

## 3. The next planned tasks: item #15 and item #22 (backlog #93)

These are the explicitly-named "remaining for a clean close" tasks. Both have full designs and partial implementations. The triage `remaining` checklists and the design `File touch list` are the acceptance contracts.

### Item #15 - Automated client/owner progress report
Design: `docs/strategy/improvement-2026-06/impl/item-15-auto-progress-report-design.md`. Triage: status partial, effort XL, needs_migration true (the design itself concludes "Migration: None" for the bounded non-AI slice - resolve this discrepancy; the non-AI slice needs no DDL).

WHAT ALREADY EXISTS (verified in the working tree, MORE than PROGRAM_STATE implies):
- The progress-claim INVOICING half shipped in v6.8.0: contracts `/progress-claims` CRUD + FSM (draft->submitted->approved->certified->paid) + auto-generate by contract type, retention. Files: `backend/app/modules/contracts/router.py` (lines ~873-918, `ProgressClaim`/`ProgressClaimLine`), `backend/app/modules/contracts/service.py`, frontend `frontend/src/features/contracts/ProgressClaimDetailPage.tsx`, `ProgressClaimLineTable.tsx`, `ProgressClaimDetail.test.tsx`.
- The reporting half is now partly built (since the design was written): `progress_report` is in the `report_type` enum at `backend/app/modules/reporting/schemas.py:146` and `:237`; the SYSTEM_TEMPLATE for progress reports is in `reporting/service.py:131`; `_build_default_snapshot` queries progress data at `reporting/service.py:886-952` (`get_latest_project_entry`, photo gallery `snapshot["photos"]`); photo gallery section handler is in `reporting/renderer.py`; the `POST /templates/{id}/run-now/` endpoint exists at `reporting/router.py:265`; cron scheduling metadata (cron parse, next_run_at, is_scheduled) is in `reporting/service.py:312-353` using `reporting/cron.py`.
- `backend/app/modules/progress/repository.py` has the progress query methods.

WHAT IS LEFT TO BUILD (acceptance criteria for closing #15):
1. The actual scheduled-distribution WORKER. Cron fields are stored and parsed, but verified there is NO background job that fires due templates (no `_run_scheduled_reports` / job-runner hook). Wire a worker that polls `next_run_at <= now` templates and calls generate + dispatch.
2. Email dispatch. Verified `send_progress_report_email` does NOT exist in `backend/app/core/mail.py`. The design specifies it (resolves portal user IDs to emails via `PortalUserRepository`, sends rendered HTML). The `run-now` endpoint currently persists the report but does not email it.
3. The portal-facing progress-reports tab. Verified `frontend/src/features/portal/ProgressReportsTab.tsx` does NOT exist; `PortalPage.tsx` has no progress-reports tab; there is no `GET /api/v1/portal/projects/{id}/progress-reports` endpoint in `backend/app/modules/portal/`. Build the tab, the portal API helpers (`listProgressReports`, `getReportContent` in `frontend/src/features/portal/api.ts`), and the backend portal endpoint that lists progress reports for an accessible project.
4. (Out of scope per design but flagged by triage as the "CORE MISSING") LLM narrative prose / `ai_agents/agents/progress_reporter.py`. The design deliberately defers this; the bounded slice ships a fixed-text template. Decide with the founder whether the narrative agent is in or out for the close.

Acceptance: a project template with `report_type=progress_report` and a cron can be scheduled, the worker fires it on schedule, recipients (emails + portal users) receive the rendered HTML, and a portal client sees the historical reports under a Progress Reports tab and can download one. Browser-verify on :8000 with a `?lang=de` pass (no raw i18n keys). New strings translated into all 26 non-English locales via the i18n-sweep skill.

Dependencies: reuses `progress` module (`ProgressEntry`), `reporting` service/renderer, `portal` module, `core/mail.py`, the job runner. The design notes `reporting/service.py` is shared with Wave 2 item #3 (live EVM) but the changes are an additive branch.

### Item #22 - Subcontractor portal invoice submission
Design: `docs/strategy/improvement-2026-06/impl/item-22-sub-portal-invoice-design.md`. Triage: status partial, effort L, needs_migration false (all tables exist).

WHAT ALREADY EXISTS:
- Internal payment-application CRUD + FSM (foreman/finance approval) in `backend/app/modules/subcontractors/` (`models.py` has `PaymentApplication`, `PaymentApplicationLine`, `WorkPackage`, `Agreement`; service has create/list/get/update/approve/reject).
- AR side shipped in v6.8.0: `finance/service.py:910 create_receivable_from_claim` raises an invoice from a certified claim; `ClaimInvoicePreview` + `PaymentModal` with retainage withholding.
- Portal module foundation: `PortalUser`, `PortalAccessRule`, `PortalSession`, `PortalMagicLink`, RLS enforcement, magic-link auth in `backend/app/modules/portal/`.

WHAT IS LEFT TO BUILD (acceptance criteria for closing #22):
1. Portal-facing endpoints. Verified NONE exist in `backend/app/modules/portal/router.py` (no `/me/payment-applications`). Add `GET /me/payment-applications` (RLS-filtered to accessible agreements), `GET /me/payment-applications/{id}`, `POST /me/payment-applications` (submit, status=submitted). Design specifies the service methods (`list_payment_applications_for_user`, `get_payment_application`, `submit_payment_application`) and 5 new schemas in `portal/schemas.py`.
2. RLS at every endpoint - subcontractor only sees/submits for agreements they hold submit/view permission on; return 404 (never 403) on cross-tenant miss, per the platform IDOR rule.
3. Frontend portal payment UI. Verified `frontend/src/features/portal/` contains only `PortalPage.tsx`, `api.ts`, `index.ts` - no payment components. Build `PaymentApplicationList.tsx` and `PaymentApplicationForm.tsx` (mobile-first, single-column, work-package line-item grid, retention calculator, status badges), add `/portal/payments` route (`App.tsx`), portal nav entry, and the api.ts helpers + interfaces.
4. Magic-link submission flow: `PortalService.consume_magic_link()` should be able to redirect to the submission form (per triage item 2).
5. Tests: `backend/tests/modules/portal/test_payment_applications.py` (new) covering empty list, RLS filtering, submit creates application+lines, submit/get RLS denial, endpoint 200/201.

Acceptance: a subcontractor logs in via magic link, sees only their accessible agreements' payment applications, submits a new application with work-package lines, and the application appears in the internal admin UI with status submitted; RLS denies inaccessible agreements; mobile (375px) and desktop layouts both verified; no new migration. i18n into all 26 locales.

## 4. Connective-tissue features 01..09 (the earlier roadmap) - shipped vs remaining

This nine-feature roadmap (`docs/strategy/IMPLEMENTATION_PLAN.md`, designs in `docs/strategy/impl/01..09-*.md`) predates and partially overlaps the TOP-30 program. The TOP-30 waves absorbed most of the financial-loop work but did NOT build the features exactly as the connective-tissue designs specified. Status by code verification:

- Feature 01 Cost spine - SHIPPED in v6.4.0. Real implementation: `backend/app/modules/costmodel/` has `ControlAccount` + `CostLine`, `CostSpineService` (generate_from_boq idempotent, FX rollups grouped by currency), 12 endpoints, frontend CostSpinePanel in the 5D dashboard. This is the keystone and is done.
- Feature 02 Payment applications - PARTIAL / divergent. The design called for a `PaymentApplication` satellite model in the CONTRACTS module (`oe_contracts_payment_application`) with `approval_instance_id`, `billing_format`, an approval_routes bridge, and a `PaymentApplicationDrawer` UI. Verified NONE of that exists: no `class PaymentApplication` in `contracts/models.py`, no `PaymentApplicationDrawer` in `frontend/src/features/contracts/`. What shipped instead is the progress-claim path (contracts `/progress-claims` + `contracts.claim.certified` -> finance invoice bridge in `contracts/events.py`). So the AIA G702/G703 pay-app vertical with approval routing is still open if the founder wants the full feature-02 design rather than the progress-claim substitute.
- Feature 03 Budget cockpit - LIKELY PARTIAL. costmodel `BudgetLine` and finance `ProjectBudget` exist and roll up, and live-EVM/KPI refresh shipped (TOP-30 #3, #10 budget sync). But the unified single-grid budget-to-commitment-to-actual-to-forecast cockpit screen as designed (`docs/strategy/impl/03-budget-cockpit.md`) was not confirmed as a distinct shipped surface. Verify against the live 5D/finance dashboards before deciding it is done.
- Feature 04 Auto EVM - PARTIAL. The design extracts a shared `app/core/evm.py`; verified that file does NOT exist. `full_evm` module exists with the math; live actuals integration shipped via TOP-30 #3. The shared-core extraction and full auto-derivation per the design are not done.
- Feature 05 5D cockpit - foundation present (costmodel spine feeds the FiveD dashboard, `project_intelligence` exists). The bidirectional model-element-to-BOQ-to-activity-to-cost navigation flagship as designed (`docs/strategy/impl/05-five-d-cockpit.md`) is not confirmed complete; treat as partial.
- Feature 06 Submittals/RFI via approval_routes - NOT SHIPPED. Verified `backend/app/modules/submittals/events.py` and `rfi/events.py` contain ZERO references to approval_routes / instance.completed. The `approval_routes` engine exists (`backend/app/modules/approval_routes/`) but submittals/rfi still do not drive their FSM through it. Design: `docs/strategy/impl/06-submittals-rfi.md`. This is dormant connective tissue, same gap the analysis named.
- Feature 07 Drawing version compare - NOT SHIPPED. Verified no visual diff/overlay in `file_versions`/`markups`/`cde` (only `markups/router.py:622` owner-id compare). Same as TOP-30 #17. Design: `docs/strategy/impl/07-drawing-version-compare.md`.
- Feature 08 Field PWA - PARTIAL. Offline slice shipped (TOP-30 #14): `frontend/src/features/field/` has `FieldShellPage.tsx`, `OfflineStatusBadge.tsx`, `useFieldSync.ts`, plus `shared/lib/offline` queue and field service worker. The native mobile shell is still a stub. Design: `docs/strategy/impl/08-field-pwa.md`.
- Feature 09 AI assistant + controls dashboard - NOT SHIPPED as designed. No `project_controls` module exists; `project-intelligence` feature folder exists on the frontend but the cross-module single-pane controls board and the grounded AI assistant (TOP-30 #16 overlaps) are open. Design: `docs/strategy/impl/09-ai-and-controls.md`.

Net: of the nine, only 01 is unambiguously done; 03/04/05/08 are partial via TOP-30 work; 02/06/07/09 remain substantially open (02 only if the founder wants the full design vs the shipped progress-claim substitute).

## 5. Cross-cutting hard constraints and gotchas for any remaining item

- Alembic: there are 207 migration files in `backend/alembic/versions/` and naming has drifted from the design-doc `v3xxx` placeholders to `vNN_*` (e.g. `v41_*`). PROGRAM_STATE recorded the single head as `v3152_ai_agents_custom` then later `v3159` after v6.8.0. ALWAYS run `python -m alembic heads` and confirm exactly one head after adding any migration (see memory `alembic_agent_migration_fork`). Every column add carries a `server_default`; new model tables go into the pre-`create_all` import list in `app/main.py`.
- Money: convert within a project via `fx_rates`, group by ISO currency across projects, never blend, Decimal-in/Decimal-as-string-out, reuse `_amount_in_base`/`_portfolio_money_breakdown`. (Memory notes `_to_decimal`/`_project_fx_map` are duplicated across ~10-17 modules - a cleanup candidate, not urgent.)
- IDOR: every endpoint resolves the owning project, calls `verify_project_access`, returns 404 (not 403) on cross-tenant miss. Field/portal reads project_id from the pinned session.
- Event subscribers: idempotent against re-delivery, open their own `async_session_factory` session, swallow failures so they never roll back the upstream transaction.
- No stubs: a dead control, a hard-coded zero, or a flag-gated empty feature is a failed phase.
- Tests: per-module temp SQLite set before any `from app...` import; run each integration test file in its own process. NEVER run the full backend pytest suite locally (it boots the full app + embedded PG per test and pins the CPU - this caused founder "request timed out" reports). Read failures from GitHub CI instead. Heavy work throttled to <=3 concurrent.
- Frontend: `npx tsc --noEmit` clean (strict mode), `tsc | grep TS1117` for locale dup blindness (single-quoted locale blocks are invisible to the dedup tooling - see memory `i18n_single_quote_dup_blindness`). New user-facing strings translated into all 26 non-English locales via the i18n-sweep skill.
- GitHub text: DataDrivenConstruction voice, human prose, few lists, NO em-dashes anywhere, no AI/Claude attribution. Email only `info@datadrivenconstruction.io`. Commit/push only when asked; push by explicit SHA refspec `git push origin $(git rev-parse HEAD):refs/heads/main` and verify with `git ls-remote` (a plain push can silently no-op). Tags are annotated - compare `vX.Y.Z^{commit}`, not the tag-object SHA.
- Dev env: backend :8000 = `python -m app.cli serve --data-dir "C:/Users/Artem Boiko/.openestimate-v6live" --port 8000` (embedded PostgreSQL, serves `backend/app/_frontend_dist`, no --reload). The TOP-30 program used :8080. Frontend changes need `npm run build` in `frontend/` then mirror dist to `backend/app/_frontend_dist` then restart. Embedded PG quirks: recovery-timeout can silently fall back to SQLite (see memory `embedded_pg_recovery_timeout`); kill the supervising bash before the python; never `git reset --hard`/`git stash`/`git clean` (scratch `_*` files live in the tree).
- VPS deploy by tag (port 9090 behind Caddy), never build the frontend on the VPS (disk near full), use the 4-slash `DATABASE_SYNC_URL` for alembic.

## 6. Suggested next-action sequence for a fresh agent

1. Resolve the branch/version split (Section 1) with the founder; pick the v6.9.0 line or `feat/postgres-only` as the base.
2. Close item #15: build the scheduled worker + `send_progress_report_email` + portal ProgressReportsTab + portal list endpoint; decide narrative-agent in/out.
3. Close item #22: portal payment-application endpoints + RLS + list/form UI + tests.
4. Then pick from the remaining TOP-30 by wave order (Wave 4 field ops #2/#7/#26/#28, Wave 5 AI/coordination #12/#16/#17/#23, Wave 6 lifecycle #21/#25/#27/#29/#30), using the per-item design docs as the acceptance contract.
5. For the full connective-tissue features the founder still wants (notably 06 submittals/RFI through approval_routes, 07 drawing compare = #17, 02 full pay-app vertical, 09 controls dashboard), use `docs/strategy/impl/0N-*.md`.



## OPEN QUESTIONS
- Version/branch reconciliation: the working branch feat/postgres-only and remote main are at 6.8.0 while tag v6.9.0 (branch release-v6.9.0) is at 6.9.0 and ahead. Which branch is the canonical base for the next release, and should the working tree be fast-forwarded to v6.9.0 before building #15/#22? Could not infer the intended reconciliation from the docs.
- Item #15 migration ambiguity: the triage digest marks needs_migration=true but the design doc concludes 'Migration: None required' for the bounded non-AI slice. The reporting-half columns (cron/recipients/is_scheduled) already exist. Confirm no new DDL is actually needed for the worker + email + portal-tab work.
- Item #15 narrative agent scope: the design deliberately defers LLM narrative prose (ships fixed-text template), but the triage calls 'zero narrative text generation' the CORE MISSING piece and lists ai_agents/agents/progress_reporter.py as a target file. Is the narrative agent in or out for closing #15?
- Backlog #93: the founder framed #15 and #22 as tracked under backlog item #93, but no #93 reference is findable in the repo docs or an authenticated issue tracker (gh is not authenticated in this environment). Could not verify the issue title/scope of #93 directly.
- Connective-tissue feature 02 vs the shipped progress-claim path: the original feature-02 design (contracts PaymentApplication satellite + approval_routes bridge + PaymentApplicationDrawer) was NOT built; a progress-claim invoicing path was shipped instead. Is feature 02 considered satisfied by the progress-claim substitute, or does the founder still want the full AIA G702/G703 pay-app vertical?
- Connective-tissue features 03 (budget cockpit) and 05 (5D cockpit) completeness: their financial foundations and live-EVM refresh shipped via TOP-30 work, but I could not confirm in static code whether the unified single-grid budget cockpit screen and the bidirectional 5D navigation surface match their design docs as 'done'. A live browser pass on the 5D/finance dashboards is needed to grade them.
- Item #29 no-code agent builder vs the v6.7.0 'AI agent builder': memory records an AI agent builder shipped in v6.7.0, but #29 is still listed as triaging. The overlap/delta between what shipped and what #29's design requires is unverified.
- Alembic head drift: the design docs assume a v3151->v3159 chain but the versions directory uses vNN_* names (e.g. v41_*) and has 207 files. The exact single current head on the chosen base branch was not confirmed via 'alembic heads' (the command needs a valid-shaped DB URL and was not run here).

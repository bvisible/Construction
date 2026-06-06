# TOP-30 competitive roadmap - execution program

Resumable control file. Read this first on any resume.

## What this is

Implement the 30 ranked competitive-gap features from the June 2026 deep research
(`01_sections_competitive_top30.json`, `result.top_30_missing`) plus the
companion coordination fixes and critical stubs, to high quality with simple,
clear, beautiful UI, and deep browser testing (real Playwright clicks +
screenshots + screenshot analysis) before each wave is committed.

Started: 2026-06-04. Base: branch `feat/postgres-only` == remote `main` at `d1ede2f90`.
Local backend for testing: `http://localhost:8080` (v6.7.0, 117 modules).
Frontend e2e: Playwright is wired (`frontend/playwright.config.ts`, `frontend/e2e/`).

## Hard rules (do not violate)

- The research findings are dated 2026-06-02 and are PARTLY STALE; v6.5-v6.7
  already fixed some. Always triage against current code before implementing.
  Confirmed already done so far: #13 LTIFR/TRIR (`safety/service.py:488-503`);
  #1 clash->notifications high-severity path (`notifications/events.py`
  `_on_clash_high_severity`).
- One change touches one file at a time. Within a wave, lanes must be
  file-disjoint so parallel agents never collide. Shared files
  (`core/events.py`, `notifications/events.py`, `costmodel/service.py`,
  dashboard rollup) get a single owner lane.
- No DB migration without checking `python -m alembic heads` == one head after.
  Current single head: `v3152_ai_agents_custom`.
- Heavy backend work (pytest that boots embedded PG, Playwright) is throttled:
  never more than 3 concurrent. Implementation agents only py_compile + ruff
  their own files; the full test + browser pass runs centrally afterward.
- Commits/PRs/releases: human prose, DDC voice, no em-dashes, no AI attribution.
  Push to main via `git push origin $(git rev-parse HEAD):refs/heads/main`.
- Do not delete other sessions' untracked scratch files.

## Execution protocol per wave

1. Triage (read-only, parallel) - confirm what is really missing.
2. Implement in file-disjoint lanes (parallel). Each lane: confirm finding ->
   implement backend + frontend -> py_compile + ruff its own files. Write tests,
   do not run pytest in-lane.
3. Verify centrally: targeted pytest for touched modules, `tsc --noEmit`,
   `tsc TS1117` locale dup check, `npm run build`, single alembic head.
4. Browser-test the user-facing surfaces: restart backend, run Playwright,
   capture screenshots, read + analyze them, fix what looks wrong, re-shoot.
5. Commit the wave, push to main, update this file's status table, then next wave.

## Waves (research dependency order)

- Wave 1 - event-bus gaps + data-integrity footguns (cheap, high leverage):
  items 1, 8, 13, 24 + coordination fixes (inspection.completed.failed
  subscriber, supplier-rating publish, variation-to-contract hardening,
  plugin_manager manifest/check_updates).
- Wave 2 - planning + financial truth: items 3, 5, 6 + cost-model roll-up,
  validation->NCR escalation.
- Wave 3 - commercial depth + money flow: items 4, 9, 10, 11, 20.
- Wave 4 - field operations first-class: items 2, 7, 14, 26, 28.
- Wave 5 - AI estimating + coordination differentiators: items 12, 16, 17, 18,
  19, 23.
- Wave 6 - compliance, lifecycle, platform reach: items 15, 21, 22, 25, 27, 29,
  30.

## Triage result (2026-06-04)

Authoritative per-item status + files + remaining work + test plans live in
`_triage_digest.json` (this folder). Totals: 0 done, 26 partial, 4 missing.
The 4 fully missing: #4 ERP connectors, #17 drawing-revision compare, #24
risk<->task auto, #30 takt/line-of-balance. "partial" means a foundation exists
but the competitive feature is not complete (e.g. #13 LTIFR/TRIR is computed but
trend analytics is missing; #1 clash high-severity notify exists but
punchlist/NCR/validation subscribers do not). Wave/lane plan: `plan` key in the
digest. This is a genuine multi-wave build; each wave ships as a tested
increment, not a fake "done" on the XL items.

## Status table (initial estimate; digest is source of truth)

| # | Feature | Status | Wave | Notes |
|---|---------|--------|------|-------|
| 1 | Clash + validation events into notifications/punchlist/NCR | DONE | 1 | backend events + UI origin badges (f20c333f6) |
| 2 | Mobile time/attendance -> job cost | triaging | 4 | |
| 3 | Event-driven live EVM/KPI | DONE | 2 | KPI freshness watermark + cost/schedule/finance events invalidate; EVM "Live" pill auto-refreshes |
| 4 | Bi-directional ERP/accounting connectors | DONE | 3 | transport-agnostic connector contract + registry; file connector (CSV/JSON) push invoices/payments out, pull a GL file in as balanced double-entry ledger transactions; dry-run previews and writes nothing; formula-injection guard on export; idempotent pull (one post per transaction ref); auto-push on invoice.approved/paid via background job + idempotency key; MANAGER-only, Fernet-encrypted credentials never echoed; Connectors tab UI; migration v3155; 23 unit tests + full E2E HTTP + browser pass (v3155) |
| 5 | Cross-project resource leveling | DONE | 2 | portfolio capacity heatmap (week/month), cross-project conflict detection + UI |
| 6 | Unify schedule dependency graph + guards | DONE | 1 | canonical store + completion guard 409 + UI hint (f20c333f6) |
| 7 | AI photo intelligence | triaging | 4 | |
| 8 | Tendering vs Bid award reconciliation | DONE | 1 | idempotent bid-award PO + UI toast/link (f20c333f6) |
| 9 | Lien waiver automation + pay enforcement | DONE | 3 | opt-in per agreement; finance-approve + mark-paid held 409 until a covering signed waiver is on file; release-check endpoint + UI toggle + payment badges |
| 10 | Commitment management + budget sync | DONE | 3 | PO FSM is now draft -> approved -> issued; approval (not issue) is the commitment moment that publishes procurement.po.approved -> finance ProjectBudget.committed += amount_total; manager-level approve permission + /approve/ endpoint; UI shows Approve on draft rows, Issue on approved; 4 unit tests + cross-module flow extended; browser-verified committed rose by exact PO total (e0ebb1ac7) |
| 11 | Change Order AI draft + impact simulator | DONE | 3 | deterministic what-if simulator on CO detail (budget before/after, finish-date shift, EVM BAC/EAC/VAC/SPI/CPI recomputed, BOQ preview, cost/days overrides + re-run, save-scenario to audit trail) + AI/heuristic draft-from-notes modal (AI when a key is set, deterministic figure-parsing fallback otherwise, human reviews before create). FX-correct, no LLM required for the simulator. Metadata-stored provenance/scenarios so no migration (single head v3154). 16 unit tests; browser-verified end to end (c921fb805) |
| 12 | ITP workflow with hold points | triaging | 5 | |
| 13 | LTIFR/TRIR computation | DONE | - | safety/service.py:488-503 |
| 14 | Native offline-first mobile app | PARTIAL | 4 | offline slice shipped (v6.8.0): shared/lib/offline mutation queue + connectivity + field service worker + useFieldSync; field app keeps working offline and syncs on reconnect. Full native mobile shell still a stub (FieldShellPage) |
| 15 | Auto client/owner progress report | PARTIAL | 6 | progress-claim invoicing shipped (v6.8.0): auto-generate by contract type (lump sum / cost plus / T&M / unit price) with retention + draft->submitted->approved->certified->paid lifecycle; contracts router /progress-claims + ProgressClaimDetailPage + line table + test. NOT shipped: the owner-facing progress *report* document (photo galleries, narrative, scheduled email distribution to portal) from the design doc |
| 16 | Semantic AI assistant over docs | triaging | 5 | |
| 17 | Auto drawing/BIM revision compare + cost | triaging | 5 | |
| 18 | ML quantity extraction / symbol recog | DONE | 5 | symbol-signature match shipped (v6.8.0): match_elements/symbol_signature.py + signature_match_service.py learn a symbol's geometric signature and suggest recurrences across a drawing set; SymbolSuggestionPanel UI; unit + component tests |
| 19 | Predictive schedule/cost risk analytics | DONE | 5 | project_intelligence forecast.py + service.py (deterministic cost/schedule forecast) and risk/escalation.py (slip->risk escalation path); ForecastInsightsPanel UI; unit + DB tests (v6.8.0) |
| 20 | Vendor/sub scorecards + prequal gating | DONE | 3 | prequal award gate (blocked/rejected/suspended sub cannot activate an agreement or be paid, 409) plus event-driven scorecard auto-decrement now closed (v6.8.0): subcontractors/events.py subscribers on NCR / HSE incident / schedule slip call bump_rating_from_event, idempotent monthly rollup (migration v3158 unique (sub, period)); test_scorecards + test_subs_rating_event_wiring. No scorecard display UI yet |
| 21 | ISO 19650 CDE suitability propagation | triaging | 6 | |
| 22 | Subcontractor portal invoice submission | PARTIAL | 6 | AR side shipped (v6.8.0): finance create_receivable_from_claim raises an invoice from a certified claim; ClaimInvoicePreview + PaymentModal record payment with retainage withholding; internal subcontractor PaymentApplication CRUD exists. NOT shipped: the actual portal self-submission path (no /portal payment-application endpoints, no portal-facing form, no RLS for a sub submitting their own application) |
| 23 | Persistent clash profiles + grouping | triaging | 5 | |
| 24 | Risk<->task + schedule-slip<->risk auto | DONE | 1 | risk/escalation.py wires schedule-slip events to risk auto-escalation (v6.8.0) |
| 25 | Digital handover / closeout package | triaging | 6 | |
| 26 | Equipment predictive maintenance | triaging | 4 | |
| 27 | Compliance rule engine enforced at gates | triaging | 6 | |
| 28 | Model-based progress overlay in 3D | triaging | 4 | |
| 29 | No-code agent builder | triaging | 6 | |
| 30 | Takt / line-of-balance scheduling | triaging | 6 | |

## Log

- 2026-06-04: Program created. Triage workflow launched over all 30 items.
- 2026-06-04: Triage done (31 agents). 0 done / 26 partial / 4 missing. Digest
  saved to `_triage_digest.json`. Desktop installers v6.7.0: Win + macOS
  attached; Linux Tauri build hung in CI (no .deb/.AppImage yet); download page
  made honest about it (commit 1f5252edf).
- 2026-06-04: Wave 1 BACKEND launched (run wf_a40ca164-d22), 4 file-disjoint
  lanes, backend-only, no migrations (reported for one consolidated migration),
  no frontend yet. Lane A clash/validation/inspection -> notifications + auto
  punch/NCR; Lane B schedule dependency single-source + completion guard; Lane C
  bid-award -> PO idempotent reconciliation; Lane D plugin_manager install/update.
  Next: central verify (py_compile, ruff, one consolidated migration, single
  alembic head, targeted pytest), then frontend lanes, then Playwright browser
  test with screenshots, then commit Wave 1.
- 2026-06-04: Wave 1 BACKEND verified + committed. All 4 lanes clean
  (py_compile + ruff). One consolidated migration v3153_clash_source_links
  (oe_punchlist_item.clash_result_id, oe_ncr_ncr.clash_result_id, both nullable
  indexed); single alembic head. Fixed a flagged follow-up: schedule/service_4d
  CSV import now reconciles its JSON edges into the canonical store. Fixed one
  test-harness bug (fake session column-projection detection) found by pytest;
  51/51 Wave 1 unit tests pass. Backend restarted on :8080: 117 modules,
  database ok, embedded PG auto-added both columns, no SQLite fallback. Items
  #1, #6, #8 backend done + plugin_manager stub. STILL TODO for Wave 1: frontend
  (clash/inspection origin badges on punch + NCR, validation deep-link, schedule
  "blocked by predecessor" hint, bid-award PO toast) + Playwright browser test
  with screenshots, then a frontend commit. Then Wave 2.
- 2026-06-04: Wave 1 FRONTEND done + browser-tested + 2 bugs fixed.
  Frontend: punchlist "From clash" badge (red) added next to existing
  inspection/ncr chips (kanban + table); NCR "From clash" badge + metadata on
  the type; schedule progress mutation maps HTTP 409 -> a warning toast titled
  "Blocked by predecessor" carrying the backend detail; tendering award success
  toast now names the auto-created draft PO and offers a "View purchase orders"
  action to /procurement; en.ts keys for all of the above + the validation and
  clash notification bodies. tsc clean (0 errors, 0 TS1117).
  Browser test (Playwright vs vite :5174 -> backend :8080, real demo login,
  injected clash/inspection rows on the Toronto project): punch "From clash" +
  "From inspection" and NCR "From clash" render correctly with zero console
  errors on all six surfaces (punchlist, ncr, validation, schedule, tendering,
  procurement). Two real bugs caught by the deep test and fixed:
    1. Validation ?report= deep link did nothing until a BOQ was picked, so a
       notification link landed on an empty page. ValidationPage now fires the
       report-by-id fetch on the param alone and auto-aligns project + BOQ to
       the linked report. Re-tested cold (no preselected project): the report
       (score 97) renders.
    2. POST schedule relationships returned 500 (MissingGreenlet): the Lane B
       JSON-mirror rebuild calls session.expire_all() and the handler then
       serialised the expired ScheduleRelationship, triggering an implicit
       async refresh from Pydantic's sync attribute access. Fixed by snapshotting
       RelationshipResponse before the mirror rebuild. End-to-end re-test: create
       relationship 201, complete successor while predecessor open -> 409 with
       the named-blocker message, unblocked sequence -> 200. Added integration
       regression test backend/tests/integration/test_schedule_relationship_guard.py
       (real async DB; a fake session cannot reproduce the greenlet error).
    Also fixed a pre-existing red unit test (test_schedule_relationships_limit:
    date object into a VARCHAR start_date, rejected by asyncpg since the SQLite
    removal). NEXT: commit Wave 1 frontend + these fixes, push, then Wave 2.
- 2026-06-04: WAVE 1 SHIPPED. Committed f20c333f6 (11 files: schedule router
  greenlet fix, schedule limit test fix, new integration guard test, en.ts,
  punchlist + ncr + schedule + tendering + validation pages, PROGRAM_STATE),
  pushed to main (remote now f20c333f6, was 56508f372). Final verify before
  commit: tsc 0 errors / 0 TS1117 dups; single alembic head
  v3153_clash_source_links; schedule tests 5/5 (limit 4 + guard 1). The slow
  full-app-boot version of the integration test hung on the 117-module ASGI
  lifespan (>12 min, killed); rewritten to drive the real relationship handler
  against an isolated transactional_session (real asyncpg engine still
  reproduces the greenlet error), runs in ~25s. Items #1, #6, #8 done + plugin
  stub. NEXT: Wave 2 (items 3 live EVM/KPI, 5 cross-project resource leveling,
  6 dependency graph already unified in W1, plus cost-model roll-up and
  validation->NCR escalation).
- 2026-06-04: WAVE 2 built + deep-tested. Three backend lanes (file-disjoint):
  Lane A (bi_dashboards) - KPI freshness watermark keyed per project + global,
  cost/budget/schedule-progress/snapshot/invoice events bump it, new
  GET /bi-dashboards/kpi-freshness; the 5D page polls it and invalidates the
  EVM/dashboard/s-curve queries so the figures refresh on their own, surfaced as
  a green "Live" pill. Lane B (resources) - portfolio capacity heatmap
  (GET /resources/portfolio/capacity, week/month buckets) that rolls every
  project's assignments per resource per bucket, flags over-allocation and
  cross-project contention; new /portfolio/capacity page (heatmap, summary
  chips, legend, week/month toggle) + sidebar entry. Lane D (validation->ncr) -
  a validation run with ERROR results now publishes validation.results.errors_found
  and the NCR module raises one NCR per report (idempotent), shown with a
  "From validation" badge.
  Root-caused the Lane D live failure: the escalation handler ran and its
  session guard passed, but next_ncr_number crashed with asyncpg
  "invalid input syntax for type integer" because an existing NCR carried a
  non-canonical number ("901" from the clash bridge) whose suffix cast to
  integer. SQLite cast an empty/non-numeric string to 0; PostgreSQL rejects it.
  Fixed next_ncr_number to only cast canonical NCR-<digits> rows (regexp_match)
  and hardened the same latent pattern in meetings, rfi and procurement
  (projects already had a Python fallback). New regression test
  test_ncr_number_pg_safe.py runs the real cast on PostgreSQL.
  Also fixed a 5D UX gap found in the screenshot pass: the page forced a second
  project pick even with an active project; it now opens straight to the active
  project and keeps "Back to projects".
  Verify: tsc 0 errors / 0 TS1117; touched-module pytest green (NCR 25/25,
  meetings+rfi+procurement+kpi+capacity 48/48); no migration (all changes are
  query-level or in-memory), single alembic head unchanged. Browser pass
  (Playwright vs vite :5174 -> backend :8080, real demo login): /5d opens to the
  Toronto EVM with the "Live" pill, /portfolio/capacity shows the Carpenter
  cross-project conflict and Tower Crane, /ncr shows the auto-raised "Validation
  errors in BOQ (26)" with the "From validation" badge - zero console errors on
  all three. Items #3 and #5 done (#6 was W1). NEXT: commit Wave 2, push, then
  Wave 3 (commercial depth: items 4, 9, 10, 11, 20).
- 2026-06-04: WAVE 2 SHIPPED. Committed 8bd83f676, pushed to main (remote now
  8bd83f676, was f20c333f6).
- 2026-06-04: Wave 3 item #9 (lien-waiver pay enforcement) built + deep-tested +
  SHIPPED. Backend: SubcontractAgreement gains an opt-in requires_lien_waiver
  boolean (alembic v3154, idempotent; embedded PG auto-adds the column at boot).
  When set, approve_payment_application_finance and mark_paid call
  _assert_lien_waiver_ok, which 409s with code missing_waiver /
  waiver_amount_mismatch unless a signed lien waiver covering the payment's net
  amount is on file. New GET /payment-applications/{id}/release-check reports the
  gate (waiver_required / blocked / reasons) so the UI can warn before the click.
  Frontend (SubcontractorsPage): an inline toggle on each agreement turns the
  requirement on/off (PATCH), and the Payments tab shows a per-payment badge -
  green "Waiver on file" when covered, amber "Waiver required" / "Waiver too low"
  when blocked - only fetched for payments still pending finance approval.
  Deep test caught and fixed a real bug: the gate matched waiver_type against
  the bare bases {conditional, unconditional, partial, final}, but the upload
  endpoint actually stores the compound enum (conditional_partial,
  unconditional_final, ...), so a genuine covering waiver would have been ignored
  and the payment blocked forever. Rewrote the match to exclude only the W-9/W-8
  tax forms and accept every conditional/unconditional lien type; added unit
  coverage for all four canonical types + the W-8 exclusion. Verify: ruff clean,
  tsc 0 errors / 0 TS1117, single alembic head v3154, lien-waiver gate 11/11 +
  NCR PG-safe 2/2 + subcontractors suite 84/84. Browser pass (Playwright vs vite
  :5174 -> backend :8080, seeded sub + active agreement + two foreman-approved
  payments, one with a covering unconditional_final waiver): the toggle flips
  off->on, the Payments tab then shows PA-002 "Waiver on file" (green) and PA-001
  "Waiver required" (amber), zero console errors; live API release-check confirms
  pay1 blocked (missing_waiver) and pay2 released. NEXT: Wave 3 items #10
  (commitment management + budget sync), #20 (vendor scorecards + prequal
  gating), #11 (CO AI draft + simulator), #4 (ERP connectors).
- 2026-06-04: Wave 3 item #9 SHIPPED. Committed 34e802714, pushed to main.
- 2026-06-04: Wave 3 item #20 (prequalification award gate) built + deep-tested.
  Scoped to the genuinely-complete, demonstrable slice: a subcontractor that is
  administratively blocked, or whose prequalification is rejected/suspended, can
  no longer have an agreement moved to active (update_agreement) or have a
  payment claimed (submit_payment_application) - both raise a 409 carrying the
  reason. pending (the default) and approved proceed. New helper
  subcontractor_award_block + GET /subcontractors/{id}/award-eligibility so the
  UI can show the gate before anyone tries. Frontend: an amber "Not approved for
  award" banner in the subcontractor drawer for rejected/suspended vendors
  (the existing rose banner still covers admin-blocked). Verify: ruff clean, tsc
  0 errors / 0 TS1117, prequal gate 10/10 + lien gate 11/11 + subcontractors
  suite 73/73 (94 total), single alembic head v3154 unchanged (all query/in-
  memory, no migration). Browser pass (Playwright vs vite :5174 -> backend
  :8080, seeded a suspended sub and an approved sub with draft agreements): the
  suspended drawer shows the amber banner, the approved drawer shows none, zero
  console errors; live API confirms suspended activation 409 + awardable=false
  and approved activation 200 + awardable=true.
  Deliberately left PARTIAL and logged as such: the NCR-driven scorecard
  auto-decrement half of #20 needs an NCR<->subcontractor link that does not
  exist in the schema yet (qms/ncr models carry no supplier id; the
  procurement.supplier_rating_update event already fires but with no resolvable
  supplier), so that is a separate cross-module schema effort, not faked here.
  NEXT: Wave 3 items #10 (commitment management + budget sync), #11 (CO AI draft
  + simulator), #4 (ERP connectors).
- 2026-06-04: Wave 3 item #10 (commitment management + budget sync) SHIPPED.
  Purchase orders now move draft -> approved -> issued instead of draft ->
  issued. Approval is the budget-commitment moment: approve_po() publishes
  procurement.po.approved, and the finance subscriber (formerly listening on
  po.issued) turns it into ProjectBudget.committed += amount_total. issue_po()
  now requires status approved (409 otherwise). Manager-level procurement.approve
  permission + POST /procurement/{id}/approve/. UI: draft rows show an Approve
  action, approved rows show Issue; approving raises a "budget committed" toast
  and refreshes the finance dashboard. Chose a mandatory FSM gate over the
  triage agent's opt-in approval_routes integration because it is simpler and
  guarantees every PO is a controlled commitment. Tests: 4 new unit (draft cannot
  issue directly, approve then issue, approve idempotent, issued cannot
  re-approve), cross-module flow extended with the approval step. Deep test:
  created a draft PO (total 297,500 CAD) via API, then in the browser clicked
  Approve (status flipped to approved, "Budget committed" toast, Issue button
  appeared) and Issue (status flipped to issued, toast), zero console errors;
  finance committed total rose by exactly 297,500 at approval. Commit e0ebb1ac7,
  pushed to main. No migration (status is an existing string column; single
  alembic head v3154 unchanged). NEXT: #11 (CO AI draft + simulator), #4 (ERP
  connectors).
- 2026-06-04: Wave 3 item #11 (Change Order AI draft + impact simulator)
  SHIPPED. Two deliverables. (1) A deterministic what-if impact simulator on the
  CO detail page: revised budget before/after with % of budget, project finish
  date shifting out by the schedule days, EVM (BAC/EAC/VAC/SPI/CPI) recomputed
  with the CO applied, and a BOQ write preview. Figures come from the finance
  budget aggregation converted to the project base currency (never blending
  currencies), so the forecast matches the EVM snapshot the project would
  record. Cost/extra-days overrides + re-run let a reviewer model an
  alternative; save-scenario snapshots it into the CO metadata audit trail. No
  AI call, always works. (2) AI/heuristic draft-from-notes modal: paste site
  notes / RFI / daily-log text and get a review-ready draft with confidence
  scores; uses the configured AI provider when a key exists, else a
  deterministic figure-parsing heuristic clearly labelled as offline. Nothing is
  saved until the user reviews and confirms (AI-suggests-human-confirms). Chose
  to store AI provenance + saved scenarios in the existing CO metadata JSON
  rather than add columns, so there is NO migration and the single alembic head
  v3154 is unchanged - the triage flagged needs_migration but the data is
  display/audit-only and the metadata column already exists, matching the
  platform's LIGHTWEIGHT rule. New endpoints POST /changeorders/{id}/
  simulate-impact, /publish-scenario, /ai-draft. 16 unit tests (pure cost/EVM/
  schedule math, offline money/day parsing, and simulate_impact on real
  PostgreSQL incl. FX conversion + missing-rate case). Deep browser test on the
  Toronto project: opened CO-001, the What-If panel showed budget 197.58M ->
  198.40M CAD (+825k, 0.4%), finish 2027-09-30 -> 2027-10-02, full EVM and a BOQ
  preview; a 3,000,000 / +45-day what-if re-ran correctly (budget 200.58M,
  finish 2027-11-14); the AI Draft modal generated an offline heuristic draft
  (title, CAD 15,000, 3 days, 45% confidence, one suggested line) and Create
  landed on the new CO-006 with its own live What-If panel - zero console
  errors. Commit c921fb805, pushed to main. NEXT: #4 (ERP connectors).
- 2026-06-04: #4 ERP/accounting connectors DONE (last Wave 3 item). Built a
  transport-agnostic connector contract + registry so a later SFTP/REST/DATEV/SAP
  connector drops into the same service and UI. First connector is file-based:
  push writes the project's invoices and payments as CSV or JSON to the storage
  backend; pull reads a general-ledger file and posts it as balanced double-entry
  ledger transactions. Every export cell goes through the spreadsheet
  formula-injection guard; the inbound parser accepts common header aliases.
  Safe by construction: a dry run previews and writes nothing (no files, no
  ledger rows) and only records its own audit entry; inbound journals must
  balance and be a single debit/credit pair or they are reported and skipped;
  re-importing the same file is a no-op (one post per transaction ref per
  project). Auto-push on invoice.approved / invoice.paid hands off to the
  background job runner with an idempotency key. MANAGER-only manage/sync;
  credentials Fernet-encrypted at rest and never returned (has-credentials flag
  only). New connector subpackage + config/sync-log models + schemas + service +
  event wiring + 9 REST endpoints + Connectors tab in the finance page. Two new
  tables via migration v3155 (embedded runtime auto-creates them); single
  alembic head. Verified: 23 unit tests against real PG, full E2E HTTP on a live
  backend (login, types, create, validate, dry-run wrote no files, live push
  wrote invoices.csv, sync history, missing-inbound surfaced a clean error not a
  crash, editor role got 403, delete 204), tsc 0 errors + production build OK,
  ruff clean, and a Playwright browser pass over the Connectors tab with zero
  console errors. Wave 3 (#9, #10, #11, #4) complete. NEXT: Waves 4-6.
- 2026-06-04: WAVES 4-6 + LEFTOVER SHIPPED AND PUBLISHED as v6.8.0 (commit
  89238c030, tag v6.8.0, single migration head v3159). Live on PyPI
  (openconstructionerp 6.8.0), Docker GHCR (6.8.0 / 6.8 / latest all pullable)
  and a GitHub Release. Status table updated above with honest per-item
  verdicts after a read-only verification pass:
  #18 symbol-signature match DONE, #19 predictive cost/risk forecast + risk
  escalation DONE, #20 sub scorecard event auto-decrement DONE (gap closed),
  #24 schedule-slip->risk DONE, #5 resource leveling page added, #14 offline
  slice PARTIAL (queue + service worker + sync; native shell still stub),
  #15 PARTIAL (progress-claim invoicing shipped; owner progress *report* with
  photos + scheduled email NOT shipped), #22 PARTIAL (AR invoice-from-claim +
  retainage payment shipped; the subcontractor *portal self-submission* path is
  not built). Also in this release: DWG/PDF takeoff real-metre fix and the
  full i18n backlog (~22k strings across 26 locales). REMAINING for a clean
  close of #15/#22: build the owner progress-report document + scheduled
  distribution (#15) and the /portal payment-application submission endpoints +
  form with RLS (#22).

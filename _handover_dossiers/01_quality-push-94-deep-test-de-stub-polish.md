# Quality push (#94): deep-test, de-stub, polish

# Quality-Push Remaining — Handover Dossier (backlog #94)

This covers the ongoing quality initiative: deep-test every module, remove stubs and crutches, polish the UI. It tells a fresh agent exactly what was audited, what got fixed, what is probably still open, and how to verify a module is solid.

## TL;DR for the next agent

- The deep QA sweep is **100% complete as an audit**: all 9 batches, 93 user-facing modules, roughly 465 findings (about 107 high, 153 medium, 205 low). The resume file is `qa-sweep/PROGRESS.md`; per-module detail is in `qa-sweep/findings/{module}.json` (97 JSON files on disk, gitignored).
- A large **fix wave has already landed and shipped as v6.9.0** on `origin/main` (release commit `f0db76dc1`, CHANGELOG `[6.9.0] - 2026-06-05`). The fix work itself is the ~93-file backend hardening commit `f7aa2090b`, the ~59-file frontend consolidation `d83b2a53b`, the MoC screen `e5bf98ef9`, and a handful of targeted fixes (`d04176b12` teams/MoC IDOR, `7e3eb6df4` procurement, `da5248da0` procurement-list-500, `f00549265` non-US match, `3d45227c5` property_dev dead-code drop, `0c92042d2` ruff format).
- **Branch state to fix first**: you are on `feat/postgres-only` at `0c92042d2`. That commit is already an ancestor of `origin/main`; main is 8 commits ahead (version bump + CI heap fix + marketing i18n). Locally `backend/pyproject.toml` and `frontend/package.json` still say `6.8.0` while `origin/main` says `6.9.0`. The working tree also has uncommitted `marketing-site/*.html` edits. Reconcile before doing new work: prefer continuing on `origin/main` (which has v6.9.0) rather than the stale `feat/postgres-only`.

## What the sweep audited and how

Method (from `qa-sweep/PROGRESS.md`): batches of 10 modules, one agent per module doing a deep static + API audit (read the frontend page/components plus backend router/service/repository/schemas/permissions, then run direct-HTTP smoke tests as the demo user). Browser/Playwright verification of flagged flows was a separate throttled pass (max 3 concurrent). Demo creds `demo@openestimator.io` / `DemoPass1234!`, login `POST /api/v1/users/auth/login`, backend `http://localhost:8000` (was v5.9.0 at sweep time).

Severity model: high = broken/wrong (dead button, logic bug, data corruption, RBAC hole, cross-currency money blend, 500); medium = degraded UX / missing empty-loading-error state / missing validation / untranslated; low = polish.

Per-batch high counts (from the rollup table in PROGRESS.md):
1. Core estimation 13H (money-blending pattern; dwg-takeoff 3H)
2. BIM/CAD/coord/validation 10H (COBie 500, diff 500 SQLite-lock, requirements 3H, dead federation toggle)
3. Documents/CDE/files 11H (some highs are env write-500 false positives; documents exemplary)
4. Commercial 13H (procurement 4H worst; finance/contracts/changeorders clean)
5. Planning/field 10H (schedule money+IDOR; "currency defaults EUR" pattern; meetings 2H)
6. Quality/safety/RE 15H (hse-advanced 7H worst in whole sweep; ncr 3H)
7. AI/analytics/CRM 14H (ai-agents 3H, settings 3H)
8. Platform/admin 9H (integrations 2H worst; users invite-role no-op)
9. Remaining (final) 12H (file-references 3H; dashboards route-shadow; smart_views/tasks 2H)

Cross-cutting themes the sweep flagged as fix-wave clusters: (a) cross-currency money blending (totals summed across currencies without FX, mislabeled with one currency) in dashboard, match-elements, procurement, several commercial modules; (b) currency defaulting to "EUR" instead of `project.currency` (schedule labor-cost-by-phase confirmed live: BRL project rendered "EUR"); (c) IDOR / missing `verify_project_access`; (d) dead buttons (FE field-name contract mismatches against backend schemas); (e) i18n gaps.

Important caveat baked into the sweep (PROGRESS.md, Batch 3): 10 concurrent write-smoke-test agents wedged the local aiosqlite pool, so any write-path 500 / error_handling finding in batches 1-3 may be a false positive. Re-verify on a quiet/restarted backend before fixing. Batches 4+ went read-only, so their high findings are more trustworthy.

## What the fix wave already closed (verified in current code)

These were spot-checked against the live tree, not assumed:

- **procurement** (was 4H, worst in Batch 4): all three breakages fixed. `frontend/src/features/procurement/ProcurementPage.tsx:1080` now renders `<MoneyDisplay amount={po.amount_total} currency={po.currency_code} />` (was the non-existent `po.total_amount`/`po.currency`); the create-invoice call at line ~597 now uses the trailing slash `/v1/procurement/${poId}/create-invoice/`; field interfaces updated to `amount_total`/`currency_code`. Backend list-500 fixed in `da5248da0`, draft-only PO + match-quantity normalisation in `7e3eb6df4`.
- **takeoff** (was 2H): cross-project IDOR closed. `backend/app/modules/takeoff/service.py:1431` `_assert_position_in_project` now guards `link_measurement_to_boq` / `_push_quantity_to_position` so you cannot push a quantity onto a BOQ position in a project you cannot access.
- **hse-advanced** (was 7H, worst in the whole sweep, dominated by a frontend-vs-backend contract mismatch where every table rendered blank cells and all 7 Create buttons 422'd): the frontend was rebuilt in `d83b2a53b` (`HSEAdvancedPage.tsx` +1672 lines, new `api.ts` +119) and the backend router hardened in `f7aa2090b`.
- **smart_views** (was 2H, FE dead button): `frontend/src/features/smart_views/api.ts` now has a correct `buildSmartViewShareUrl` helper and a real shared-token resolver.
- **match-elements**: non-US cost matching fixed (`f00549265`, also in MEMORY).
- **MoC (Management of Change)**: backend + permissions existed with no screen; full register UI shipped in `e5bf98ef9` (`frontend/src/features/moc/MoCPage.tsx` +1513, routed `/moc` and `/projects/:id/moc`, in the Commercial sidebar group).

The frontend consolidation `d83b2a53b` rebuilt these 17 feature pages (the worst-offender list): approval-routes, assemblies, bi-dashboards, bid-management, bim, bim_requirements, changeorders, contacts, coordination, correspondence, crm, daily-diary, fieldreports, hse-advanced, inspections, reporting. The backend hardening `f7aa2090b` touched ~63 module backends (accommodation through variations).

## What is most likely STILL OPEN (verify, then fix)

The gap to watch: the **backend hardening was broad but the frontend rebuild was narrow** (only 17 feature dirs). Modules whose sweep high findings live in the FRONTEND and whose FE was NOT touched since the v6.8.0 tag are the prime suspects. Confirmed-not-touched-since-v6.8.0 frontends with sweep highs include:

- **dwg-takeoff** (3H, frontend, NOT rebuilt). Findings at `frontend/src/features/dwg-takeoff/DwgTakeoffPage.tsx:2413-2430` (money aggregation), `:1798-1838,3329-3367` plus SummaryTab (logic), `:1840-1888` CSV / `:1893-1969` PDF export (logic). I confirmed `DwgTakeoffPage.tsx` has zero multi-currency guard tokens and the dir is untouched since v6.8.0. Note `lib/group-aggregation.ts` only aggregates quantities in metres (not money), so the money concern is specifically the page-level cost rollup at ~2413-2430. Treat as a real verification target.
- **settings** (3H): `frontend/src/features/settings/BackupRestore.tsx` (two API-contract highs vs the backup module) and `RegionalSettings.tsx:139,321,350-353,476-481` (logic). The `backup` backend WAS hardened (`f7aa2090b`, plus per-user restore in `d83b2a53b`), so re-check whether the BackupRestore FE now matches the new backend contract.
- **ai-agents** (3H): dead buttons at `backend/app/modules/ai_agents/schemas.py:109`, `frontend/src/features/ai-agents/AgentsPage.tsx:179` and `:521`. ai_agents backend was touched since v6.8.0; the FE AgentsPage was not in the consolidation set, so re-verify the buttons.
- **meetings** (2H): error_handling at `backend/app/modules/meetings/repository.py:50` and `router.py:918,924,931`. The meetings backend does not appear in the hardening file list, so these are probably still open (and were flagged read-only in Batch 5, so trustworthy).
- Other untouched-FE modules with highs to re-verify: **match-elements** dead_button (FE), **dashboard/dashboards** (route-shadow timeline/diff unreachable, no `verify_project_access`), **tendering** (2H), **submittals** (2H), **tasks** (2H), **file-references** (3H), **file-search**, **file-transmittals**, **users** (invite-user modal posts to OPEN `/auth/register` so the role picker is a silent no-op and every invite lands as `viewer`; should hit admin `POST /users/`).

Acceptance criteria for these: each flagged FE control either performs its action against the real backend route (correct path including trailing slash, correct payload field names matching the backend schema) or is removed; money columns render real values (no permanent em-dash) and never blend across currencies; every parametric route does `verify_project_access`/an IDOR guard.

## Genuine stubs / TODO / placeholder inventory (current tree)

Backend: 43 TODO/FIXME/XXX/HACK hits across 18 files, but most are explanatory comments, docstrings (the `CL-XXXX` cost-line code notes in `costmodel/service.py`), or format tokens (`VTODO` in `integrations/router.py` is iCalendar, not a to-do). The only real backend work items are:
- `backend/app/modules/schedule_advanced/cpm.py` (lines 14, 36, 269, 313): CPM only supports Finish-to-Start dependencies. `TODO(Slice 2)` to add SS / FF / SF in both forward and backward passes. Why it matters: schedules with non-FS links compute wrong floats/critical paths. Acceptance: SS/FF/SF honored in both passes with tests.
- `backend/app/modules/costmodel/service.py:816` (`TODO (v1.4)`): EVM PV is `BAC × time_elapsed%`, an approximation, not a time-phased baseline; it clamps PV to >=1% BAC and SPI to [0,5] and sets `spi_capped=True`. Documented limitation, not a stub. Acceptance: time-phased PV from `BudgetLine` + `Activity` planned dates. Note the old silent "50% placeholder" fallback was already removed (now surfaces `schedule_unknown` instead).

Frontend: the bulk of "placeholder/stub/mock" grep hits are false positives (HTML `placeholder=` attributes, locale strings, `.test.tsx` mocks). Genuine "coming soon" surfaces:
- `frontend/src/app/locales/en.ts:754-755` `boq.templates_coming_soon` / `_desc` ("The template selector will be available in a future update.") is a DEAD locale key, referenced by no `.tsx` (BOQ already ships `frontend/src/features/boq/TemplatesPage.tsx`). Either delete the key or confirm TemplatesPage supersedes it.
- `frontend/src/features/reports/ReportsPage.tsx`: the `ReportCard` type has a `comingSoon?` field and a render branch (`:1392`), but no card actually sets `comingSoon: true` in the current tree, so it is inert. `reports.coming_soon` / `integrations.coming_soon` locale keys exist.
- `frontend/src/features/integrations/IntegrationsPage.tsx`: `coming_soon` is a legitimate DATA-DRIVEN connector status (`ConnectorStatus = 'available' | 'coming_soon' | 'info_only'`, used at lines 933/980/1078); 4 occurrences. Some connectors are intentionally not built yet, shown with a neutral badge. Not a bug, but track which connectors are still `coming_soon` and build or remove them over time.
- `frontend/src/app/locales/en.ts:7383` `propdev.documents.email_pending` ("Email automation coming soon") and `:169` `ai.export_coming_soon` ("Export coming soon"): real not-yet-built features surfaced to the user. Decide build-or-remove.

## How to verify a module is "solid" (checklist)

1. Read `qa-sweep/findings/{module}.json` for the original findings and their locations (note: line numbers may have shifted; grep the function name, not the line). The JSON has `summary`, `findings[]` (severity/type/location/description/evidence/suggested_fix), `buttons_checked`, `endpoints_checked`, `api_smoke[]`, `verdict`.
2. Backend: every parametric route calls `verify_project_access` or an explicit IDOR guard; create/mutation routes RBAC-pinned to the right role; status changes go through an FSM with terminal-state guards; money is exact `Decimal`, never blended across currencies, and reads `project.currency` rather than defaulting "EUR".
3. Frontend: every button/onClick hits a real backend route with the correct path (trailing slash matters; the app runs `redirect_slashes=False`) and payload field names that match the backend schema; tables show empty/loading/error states; money columns render real values (no permanent em-dash); no raw i18n keys leak on screen.
4. Run the module live: `demo@openestimator.io` / `DemoPass1234!`, GET the list endpoints, click each create/action button, and confirm 200/expected-422 (not 404 from a path typo, not blank rows from a contract mismatch). Use a quiet/restarted backend to avoid the pool-wedge false positives.
5. For depth, the repo ships skills that automate this: `/deep-review <route>` (8-lens audit + autonomous fix + re-verify), `/i18n-sweep` (translation coverage), and the `qa-crawler` skill (browser total-coverage crawl reading `qa-tests/qa-crawler.yaml`).

## Recommended next steps, in order

1. Reconcile branch/version: move work onto `origin/main` (v6.9.0) or bump `feat/postgres-only` to 6.9.0 in all four version files (`pyproject.toml`, `frontend/package.json`, `CHANGELOG.md`, `Changelog.tsx`) per the version-sync rule, and commit/stash the marketing-site edits.
2. Re-verify-then-fix the untouched-FE highs: dwg-takeoff (money + export), settings/BackupRestore + RegionalSettings, ai-agents buttons, meetings error handling, users invite-role no-op, dashboards route-shadow, file-references, tendering, submittals, tasks.
3. Sweep the recurring clusters end-to-end one more time across ALL modules (not just the 17 rebuilt): cross-currency blend, "EUR default", dead buttons (FE/BE field-name contracts), IDOR. The hardening commit hit the backends broadly; the FE clusters are where residue lives.
4. Close the genuine TODOs: schedule_advanced CPM non-FS dependency types; costmodel time-phased PV (v1.4). Remove the dead `boq.templates_coming_soon` key and either build or remove the `ai.export` and `propdev.documents.email` "coming soon" features.
5. Then run the throttled browser-verification pass (the `qa-crawler` skill or `/deep-review wave`) to confirm zero dead controls / stubs / blank tables across the menu.


## OPEN QUESTIONS
- The detailed per-finding file paths were lost in qa-sweep/HIGH.md (all show 'file: ?'); the authoritative locations live only in qa-sweep/findings/*.json. There is no single rolled-up 'fixed vs open' ledger, so the open/closed status of each high finding had to be inferred from which files the fix commits touched plus spot-checks. A definitive remaining-work list requires re-running the findings against current HEAD (or re-running the sweep) rather than trusting the v5.9.0-era findings JSON.
- The sweep ran against v5.9.0; current shipped is v6.9.0. Line numbers in findings have drifted (confirmed in takeoff service.py), and some modules were heavily rewritten since, so several 'high' findings may already be moot. Each must be re-verified by function name, not line number, before being treated as open.
- dwg-takeoff money finding (DwgTakeoffPage.tsx ~2413-2430): the page has no multi-currency guard and the FE was untouched since v6.8.0, but I did not run it live to confirm the blend still manifests with a real mixed-currency dataset. Needs a live check before fixing.
- settings/BackupRestore.tsx: the backup BACKEND was hardened and per-user restore added, but I did not confirm the BackupRestore FRONTEND was updated to the new contract, so the two 'api' highs there may or may not still apply.
- Whether the local feat/postgres-only branch should be advanced to v6.9.0 or simply abandoned in favor of origin/main is a process decision for the founder; the uncommitted marketing-site/*.html edits in the working tree also need a disposition.
- The qa-sweep/ directory contains ~150 scratch files (logs, .pyc, .txt) committed-or-not that are gitignored noise; it is unclear whether the founder wants them cleaned up as part of the de-crutch effort.

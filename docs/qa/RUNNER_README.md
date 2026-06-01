# OpenConstructionERP — QA Test Plan Runner

This document explains how to execute `MASTER_TEST_PLAN.md` and consume the
resulting artefacts. It is companion to:

- `docs/qa/MASTER_TEST_PLAN.md` — the human-readable plan (~7,500 lines).
- `docs/qa/test_plan_manifest.json` — the machine-readable manifest the
  runner consumes (~20,000 lines, ~650 KB).
- `docs/qa/_build_plan.py` — the generator that produced both files from the
  live `backend/app/modules/` + `frontend/src/features/` inventory.

The plan covers 112 backend modules, 100+ frontend pages, 15 batches, 10
personas, 15 regression-matrix items, and roughly 1,100 individual test
cases. Total estimated runner-minutes (serial): **3,520**. With 5 parallel
runners: **~12 hours wall-clock**. Including triage and the bug-fix loop:
**~94 agent-hours**.

---

## 1. Spinning up the runner agents

The runner is an orchestrator that fans out Playwright agents per batch
against a single shared SUT (system under test). The recommended topology
on a developer workstation is:

```
                  ┌───────────────────────────┐
                  │  Orchestrator (this doc)  │
                  └─────────────┬─────────────┘
                                │
       ┌────────────────────────┼────────────────────────┐
       │                        │                        │
   ┌───▼────┐              ┌────▼───┐               ┌────▼────┐
   │ batch-1│              │ batch-2│      ...      │ batch-15│
   │ agent  │              │ agent  │               │  agent  │
   └───┬────┘              └────┬───┘               └────┬────┘
       └────────────┬───────────┴───────────┬────────────┘
                    │                       │
              ┌─────▼──────┐         ┌──────▼─────┐
              │  Backend   │         │  Frontend  │
              │ (uvicorn)  │         │   (vite)   │
              └─────┬──────┘         └────────────┘
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
    postgres    redis      minio + qdrant
```

### 1.1 One-shot wave (manual)

```bash
# From repo root, with Phase 0 already green:
python scripts/qa/run_wave.py \
  --manifest docs/qa/test_plan_manifest.json \
  --out qa-runs/$(date -u +%Y-%m-%dT%H-%M-%SZ) \
  --parallel 5 \
  --browser chromium
```

`run_wave.py` (not yet in tree — to be created in a follow-up task) parses
the manifest, schedules batches respecting `depends_on`, spawns Playwright
processes per batch, and aggregates results into the run directory.

### 1.2 Sub-agent topology (recommended)

Hand each batch to its own agent worktree. The orchestrator
agent:

1. Reads `test_plan_manifest.json`.
2. For each batch in dependency order:
   a. Creates a worktree: `git worktree add ../qa-batch-NN main`.
   b. Spawns a sub-agent in that worktree with the prompt:
      "Execute batch `batch-NN-<name>` from `docs/qa/MASTER_TEST_PLAN.md`.
      Use Playwright Chromium. Capture screenshots to `qa-runs/<ts>/`.
      Report results as a JSON file at `qa-runs/<ts>/batch-NN-result.json`."
   c. Monitors via filesystem polling.
3. After all batches complete, runs Phase 3 (personas) and Phase 4
   (regression) in two more sub-agents.
4. Triages failures via Phase 5 — auto-spawn fix agents for `minor`/`polish`
   only.
5. Generates the Phase 6 report.

### 1.3 Pre-requisites the runner enforces

Phase 0 is a hard gate. The orchestrator refuses to spawn batch agents
unless `scripts/qa/check_phase0.py` exits zero. Phase 0 checks:

- Docker dependencies all healthy.
- `alembic current` shows `v3123_boq_fk_indexes (head)`.
- `/api/system/modules` returns ≥ 112.
- Playwright critical_paths.spec.ts passes on Chromium.
- Demo accounts can log in.

---

## 2. Interpreting screenshots and the report

### 2.1 Directory layout

After a wave completes, `qa-runs/<ts>/` looks like:

```
qa-runs/2026-05-24T20-30-00Z/
├── report.html               # → open this first
├── batch-01-result.json
├── batch-02-result.json
├── ...
├── screenshots/
│   ├── batch-01-auth-identity/
│   │   ├── users-T001/
│   │   │   ├── 01-login-form.png
│   │   │   └── ...
│   │   └── ...
│   └── personas/
│       └── persona-01-estimator-de/
│           ├── step-01.png
│           └── ...
├── traces/
│   └── <test-id>.zip         # Playwright trace, viewable with `npx playwright show-trace`
├── videos/
│   └── <test-id>.webm        # only captured on failure by default
├── axe-reports/
│   └── <module>.json         # axe-core a11y violations
├── lighthouse/
│   ├── <route>.report.html
│   └── summary.md
├── coverage/                 # frontend code coverage (c8/v8)
├── bugs_*.md                 # one per batch, auto-aggregated
└── recommendations.md        # lead-agent narrative summary
```

### 2.2 The HTML report

`qa-runs/<ts>/report.html` is the single artefact a human reviews to
decide ship/hold. It includes:

- Traffic-light summary per batch (green / yellow / red).
- Per-module collapsible card with passed / failed / skipped counts.
- Inline lazy-loaded thumbnails for every screenshot.
- Filters: status, severity, module, locale, browser.
- Drill-down to the matching `bugs_*.md` entry on failure.

Run `python scripts/qa/build_dashboard.py qa-runs/<ts>/` to regenerate the
HTML after manual triage edits.

### 2.3 Reading screenshot filenames

```
screenshots/<batch-id>/<test-id>/<step-or-state>.png
```

- `batch-id` — e.g. `batch-07-propdev`.
- `test-id` — stable across runs: `propdev-T004` or `S-08` for smoke.
- `step-or-state` — `01-form.png`, `02-after-submit.png`, `axe.json`, etc.

Compare two runs side-by-side:

```bash
python scripts/qa/screenshot_diff.py \
  --old qa-runs/2026-05-23T.../ \
  --new qa-runs/2026-05-24T.../ \
  --out qa-runs/diff_24-vs-23.html
```

---

## 3. Filing new bugs the runner found

The runner auto-files bugs into `docs/qa/bugs_<ISO-timestamp>_<batch-id>.md`
following the schema described in Phase 5 of the master plan. To file a
bug manually (e.g., something the runner missed but you spotted while
reviewing screenshots):

1. Append to `docs/qa/bugs_<latest-ts>_manual.md` (create if absent).
2. Use the same `B-NNN` numbering, continuing from the highest existing.
3. Required fields: `Severity`, `Module`, `Test id` (use `MANUAL-<slug>`),
   `Reproduction`, `Expected`, `Actual`, `Evidence`.
4. If a screenshot is involved, copy it into `qa-runs/<ts>/screenshots/manual/`
   and reference it by full relative path.
5. Open a tracker issue with the same title and link back to the markdown.

For severity ladder rules, see Phase 5.2 of the master plan.

---

## 4. Adding a new test to the plan

The plan is regenerated from the live filesystem inventory plus three
Python literals in `_build_plan.py`. To add a test:

### 4.1 Add a new smoke test

Edit the `smoke_tests` list inside `build_manifest()` (also add a `Test
S-NN — …` section to `PHASE_1_TEXT`). Regenerate:

```bash
python docs/qa/_build_plan.py
```

### 4.2 Add a module-specific edge case

Edit `_module_specific_edge_notes()` and add an entry keyed by the module
folder name. Regenerate.

### 4.3 Add a new persona

Append a dict to `PERSONAS` and a key to `PERSONA_CONCRETE_STEPS`.
Regenerate.

### 4.4 Add a new regression-matrix item

Append a dict to `REGRESSION_MATRIX` with `id`, `name`, `scope`, `check`,
`modules_baseline`. Regenerate.

### 4.5 Add a new batch

Append a dict to `BATCHES` with `id`, `name`, `modules`, `estimated_minutes`,
`summary`, `depends_on`. Modules already in another batch will be silently
skipped (first batch wins) — re-order if needed.

### 4.6 Add a new test template

Add a Template block to `SHARED_TEMPLATES_TEXT` and add the matching
T0NN entry to `per_module_section()` and `build_manifest()`. Regenerate.

### 4.7 Re-run after every plan edit

```bash
python docs/qa/_build_plan.py
git diff docs/qa/MASTER_TEST_PLAN.md  # sanity-check the delta
```

Commit both `_build_plan.py` AND the regenerated `MASTER_TEST_PLAN.md` +
`test_plan_manifest.json` so the static artefacts stay in sync with the
source-of-truth generator.

---

## 5. Known traps and pitfalls

These cost the team hours during previous waves — encode in the runner so
they cost you minutes instead.

| Trap | Symptom | Mitigation |
|------|---------|------------|
| Demo email typo `openestimate.io` (no "r") | 401 on every login | The seed loader uses `openconstructionerp.com` (with "r"). Hard-code in fixtures. |
| Worktree pinned to stale base | Schema mismatch on first request | First step in every batch agent: `git checkout $(git rev-parse origin/main) -- .` |
| Prod browser probes parallelised | Demo VPS event-loop stalls | Phase 3 personas run SEQUENTIALLY on prod; only Phase 2 parallelises. |
| `/api/v1/health` returns 404 | Health check reports red | Use `/api/health` (no `/v1`). |
| `default_response_class=ORJSONResponse` rejects NaN | 500 on BIM bbox endpoints | Regression matrix item `reg-13-orjson-no-nan` catches this. |
| Alembic CLI on VPS hits wrong DB | Migrations appear missing | Always set `DATABASE_SYNC_URL` with 4-slash absolute path. |
| VPS wheel shadowed by source | New JS chunks 404 | After pip install, `cp -r frontend/dist backend/app/_frontend_dist`. |
| Lazy-locale Header race | Header shows EN after switch to DE | `useI18nReady()` in Header re-renders on chunk arrival. |
| Per-page `relative isolate` traps modals | Modals appear behind sticky header | Mount `DashboardBackdrop` in `AppLayout`, not per-page. |
| Bug-report template captures benign 404s | False-positive auto-bug-reports | `getLastError` prefers level=error; handled 404s no longer leak. |
| Sandbox uvicorn `--reload` flakes | Backend dies mid-test | Run without `--reload` in QA waves. |

---

## 6. Quick reference

| Question | Answer |
|----------|--------|
| Demo credentials? | `demo@openconstructionerp.com` / `demo123` (note the "r") |
| Alembic head expected? | `v3123_boq_fk_indexes` |
| Module count? | 112 |
| Smoke tests? | 12 (`S-01` through `S-12`) |
| Batches? | 15 |
| Personas? | 10 |
| Regression items? | 15 |
| Total test cases? | ~1,100 (smoke 12 + module 112×10 + personas 10 + regression 15) |
| Contact for help? | `info@datadrivenconstruction.io` |

---

## 7. Regenerating the plan

The master plan is a generated artefact. To rebuild after a new module is
added to `backend/app/modules/`:

```bash
python docs/qa/_build_plan.py
git add docs/qa/MASTER_TEST_PLAN.md docs/qa/test_plan_manifest.json
git commit -m "docs(qa): regenerate plan after <module> added"
```

The generator script is committed alongside the artefacts so anyone can
re-derive them from a fresh checkout.

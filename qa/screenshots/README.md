# qa/screenshots — full-app screenshot grid

Continuous Playwright suite that captures a **full-page PNG of every key
route** in OpenConstructionERP, organised by section, dated by run.

Use it as a **visual ground-truth ledger** after each merge — a human (or a
future Claude session) can flip through the grid to spot layout
regressions, broken empty-states, 500s, missing translations, etc.

> This is **not** a visual-diff CI gate. We don't fail on pixel deltas —
> we produce deterministic artefacts. A pixel-diff gate is a future
> follow-up.

## Quick start

```bash
# 1. Start backend + frontend in two terminals
make dev-backend          # → http://localhost:8000
make dev-frontend         # → http://localhost:5173 (or 5180 if 5173 busy)

# 2. Run the screenshot suite
make qa-screenshots

# Output:
#   qa-report/screenshots/<YYYY-MM-DD>/<section>/<slug>.png
```

The first run takes ~3-5 minutes (one demo-login + ~70 routes ×
~5 s each). Re-runs are the same — the suite intentionally does not
cache navigations.

## Configuration

All overrides via env vars:

| Var | Default | Purpose |
|-----|---------|---------|
| `QA_BASE_URL` | `http://localhost:5180` | Frontend dev server. Use `5173` if that's where Vite ended up. |
| `QA_API_URL`  | `http://localhost:8000` | Backend FastAPI server. |
| `QA_DEMO_EMAIL` | `demo@openconstructionerp.com` | Demo account (note the **r** in *openestimator*). |
| `QA_PROJECT_ID` | first project from `/api/v1/projects/` | Project id substituted into `:projectId` routes. |
| `QA_BIM_MODEL_ID` | first model from `/api/v1/bim-hub/?project_id=…` | Model id substituted into `:modelId` routes. |
| `QA_SCREENSHOT_DIR` | `qa-report/screenshots/<YYYY-MM-DD>/` | Override output dir. |

```bash
# Example: target a specific project
QA_PROJECT_ID=0cefc29a-4e20-4287-be24-8ea0c2e4343b make qa-screenshots
```

## Route catalogue

Defined in `full-app.spec.ts` → `ROUTES`. Currently ~70 routes across
10 sections (`01_core`, `02_bim`, … `10_admin`). Add a route by appending
an entry — the screenshot file lands automatically at
`qa-report/screenshots/<date>/<section>/<slug>.png`.

```ts
{ section: '06_commercial', slug: 'my_new_page', path: '/my-new-page' },
```

Dynamic params (`:projectId`, `:modelId`) are resolved from
`fetchDemoFixtures()` — extend that function if you add a new param type.

## Interpreting the results

1. **Open the run folder**: `qa-report/screenshots/<today>/`
2. **Browse by section** — each subfolder mirrors a sidebar group.
3. **Look for**:
   - blank pages (white/grey) → component crash, check console
   - red error frames → route 500'd, see Playwright stdout
   - sidebar-only screens with missing content → empty-state regression
   - layout overflow / cropped widgets → CSS / responsive regression
   - missing translations (`projects.list.title` raw key) → i18n gap

The spec writes a per-route log line to stdout:

```
[qa-screenshots] OK  02_bim/bim_viewer → /bim/cdf074f9-95d2-585a-8323-f329d237bafd
[qa-screenshots] ERR 04_propdev/propdev_dashboards → /property-dev/dashboards (Timeout 45000ms exceeded.)
```

…and an end-of-run summary with byte-counts + failed-route table.

## Failure handling

A single route failing does **not** abort the run. On exception the spec:

1. logs the error
2. attempts a best-effort screenshot anyway (often shows the 500/blank)
3. continues to the next route

Only two routes are **hard canaries** (test fails if either errors):
`/` (dashboard) and `/projects`. If those are broken the environment is
fundamentally wrong and the rest of the data is suspect.

## Why a standalone config?

`qa/playwright.config.ts` is a do-not-modify polyglot that drives the
`V_*.spec.ts` verification waves (HSE, RFI, Tendering, …). Its
`testMatch: ['V_*.spec.ts']` deliberately excludes our spec.

We ship a **standalone** `qa/screenshots/playwright.config.ts` that:
- runs serial (`workers: 1`) — one demo-login, stable cookies
- generous 10-min suite timeout (routes × settle time adds up)
- one chromium project at 1440×900 (deterministic viewport)
- no auto-server-start — fails fast with a clear error if the app is down

It does **not** extend or import the polyglot config.

## Related infrastructure

| File | Role |
|------|------|
| `qa/playwright.config.ts` | Polyglot V_* verification harness (do-not-modify). |
| `frontend/playwright.config.ts` | Smoke-batch harness under `frontend/tests/e2e/smoke/`. |
| `frontend/tests/e2e/fixtures/auth.fixture.ts` | Worker-scoped JWT cache (reference for hydrate-storage pattern). |
| `qa/V_*.spec.ts` | Per-module verification waves (HSE, RFI, …). |

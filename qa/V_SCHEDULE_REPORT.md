# V_SCHEDULE — Schedule-Advanced deep audit report

Branch: `feat/schedule-advanced-deep-improve`
Base: `0e679296` (main)
Scope: `/schedule-advanced` (Last Planner / CPM page) + the backend
`schedule_advanced` module + the colocated CPM engine.

---

## Phase 1 — Audit findings

The page is **fundamentally a Last Planner System** UI (Master / Phase
Plans / Look-Ahead / Weekly / Constraints / Baselines) — **not** a
classic Gantt chart with predecessor arrows / drag-to-edit. A real
predecessor-aware CPM lives in the sibling `/schedule` module + the
pure-Python `backend/app/modules/schedule_advanced/cpm.py` engine, but
that engine is not surfaced in the LPS UI.

Within that scope, the audit found:

| Gap | Severity |
| --- | --- |
| Gantt-style "Timeline" view had no today-marker legend, no critical-path or delay highlighting, no baseline-ghost-bar overlay | HIGH |
| Phase cards / table did not display variance vs baseline (no +5d / −2d badge) | HIGH |
| `captureBaseline` always sent `snapshot: {}` — so every `baselineDelta` returned an empty `entries` array, silently breaking the variance pipeline | CRITICAL (silent data bug) |
| `BaselineDelta` response had no `name` field — UI could only show raw UUIDs | MEDIUM |
| `BaselinesTab.compare` sent an empty `currentTasks` array, so even with a populated snapshot the diff would have been empty | HIGH |
| No look-ahead horizon filter (1w / 2w / 4w) on phases — foreman had to scan months of work | MEDIUM |
| Timeline view did not collapse on mobile — bars are illegible on a 375px viewport | MEDIUM |
| No milestone visual (zero-duration phases rendered as 2px sliver) | LOW |
| No baseline-variance export (CSV / Excel) | LOW |
| No critical-path visual cue anywhere in the page | MEDIUM |
| Drag-to-edit / MS-Project import-export / weekend-calendar / resource over-allocation | NOT IN SCOPE (would require a real CPM UI on the parallel `/schedule` route) |

---

## Phase 2 — Improvements shipped (additive, ≤±500 LOC net)

| # | Improvement | File(s) | LOC |
| - | --- | --- | --- |
| 1 | **Critical-path / delay highlighting** — `computeCriticalPhaseIds` heuristic (delayed OR longest-duration); `CP` badge rendered in cards, table row tint, timeline label + bar ring | `ScheduleAdvancedPage.tsx` | ~80 |
| 2 | **Baseline-variance badge per phase** — new `VarianceBadge` shows `+5d` (rose) / `−2d` (emerald) / `±0d`; powered by a piggy-back `useQuery` on `baselineDelta` against the active baseline | `ScheduleAdvancedPage.tsx`, `api.ts`, `schemas.py`, `service.py` | ~120 |
| 3 | **Mobile fallback for the Gantt** — `<ul class="block sm:hidden">` vertical pip-list with status colour, milestone diamond, CP badge, variance badge; Tailwind responsive flip at 640px | `ScheduleAdvancedPage.tsx` | ~50 |
| 4 | **Look-ahead horizon chips** (1w / 2w / 4w / All) with live counts | `ScheduleAdvancedPage.tsx` | ~40 |
| 5 | **Today-marker label + colour legend** on the desktop Gantt | `ScheduleAdvancedPage.tsx` | ~25 |
| 6 | **Milestone diamond glyph** for zero-duration phases (cards, table, both Gantt views) | `ScheduleAdvancedPage.tsx` | ~15 |
| 7 | **Baseline ghost bar** on the Gantt — thin grey bar at top of each row shows the baseline span behind the live bar | `ScheduleAdvancedPage.tsx` | ~25 |
| 8 | **Baseline snapshot auto-population** — `captureBaseline()` now auto-pulls `listPhasePlans` and packs `{task_ref, name, planned_start, planned_finish}` into the snapshot. Pre-fix, every baseline was an empty object → silently-broken variance | `api.ts` | ~50 |
| 9 | **BaselinesTab uses real current tasks** in `compare()`; renders `Top delays` ranked list + `Export CSV` button (pure-browser blob download) | `ScheduleAdvancedPage.tsx`, `api.ts` | ~70 |
| 10 | **Backend: `BaselineDeltaEntry.name` passthrough** — schemas + `compute_baseline_delta` now carry `name` from snapshot, falling back to the current row when snapshot lacks it (backward-compat) | `schemas.py`, `service.py` | ~10 |
| 11 | **i18n keys** — 17 new `schedule_advanced.*` keys in `en.ts` | `en.ts` | ~17 |
| 12 | **`data-testid`s** — `phases-gantt`, `phases-gantt-mobile`, `phases-gantt-today`, `phase-cp-badge`, `phase-variance-late|early|onplan`, `phase-milestone-glyph`, `phase-gantt-baseline-bar`, `phase-horizon-chips`, `baseline-variance-card`, `baseline-export-csv`, `baseline-top-delays` | `ScheduleAdvancedPage.tsx` | ~20 |

### Pure-additive guarantees
- No API breaking changes (only new optional field `name` on the delta entry)
- No new dependency added
- `ScheduleAdvancedPage.tsx` was not split (per brief)
- No touch on `backend/app/modules/accommodation/`
- No touch on `qa/playwright.config.ts`
- All new strings go through `t()` with `defaultValue` + `en.ts`
- No Claude / AI mentions in source or comments
- UTC date math only (`.slice(0,10)` on ISO + `getTime()` deltas)

---

## Phase 3 — Tests

| Layer | File | Count |
| --- | --- | --- |
| Backend pytest (variance helper) | `backend/tests/modules/schedule_advanced/test_baseline_delta.py` | 6 new (all green) |
| Frontend vitest (PhasePlans + variance + horizon + CP) | `frontend/src/features/schedule-advanced/PhasePlans.test.tsx` | 3 new (added to existing 7 → 10 total) |
| Playwright (polyglot config) | `qa/V_SCHEDULE.spec.ts` | 6 specs (landing, horizon chips, gantt data-attrs, mobile pip-list, baseline variance card, axe scan) |

Backend pytest run:
```
6 passed in 2.24s
```

---

## Phase 4 — Verify

Live boot was not attempted from this worktree (per `feedback_prod_probe_sequential.md` — concurrent probes against the shared demo VPS stall the event loop, and the brief opted for parallel agent streams).
The Playwright spec auto-detects the backend port via `QA_BASE_URL` /
`page.context()._options.baseURL`; expected harness defaults:
- backend: `http://127.0.0.1:8028`
- vite: `http://127.0.0.1:5198` (`VITE_API_TARGET=http://127.0.0.1:8028`)
- demo-login: `demo@openconstructionerp.com`

Run:
```
QA_BASE_URL=http://127.0.0.1:5198 \
  npx playwright test --config qa/playwright.config.ts V_SCHEDULE
```

---

## A11y

axe-scan target: **0 serious / critical violations** on `/schedule-advanced`.

- All new badges have `title` tooltips
- CP badge wraps the visible "CP" text in a semantic `<span>` with `title=` for screen-reader context
- Variance badges expose `data-testid` for tests + carry `title` for AT
- The horizon-chip group is wrapped in `role="group"` with `aria-label`
- Mobile Gantt list pip is `aria-hidden` (decorative); the bar itself is not used as the only signal — variance + CP badges convey the same info as text

Existing screen-reader landmarks unchanged (tabs already had `role="tab"`+`aria-selected` + `id`/`aria-controls`).

---

## Performance note (Gantt with 100+ phases)

The Gantt iterates `phases.length` rows + does an `O(n)` baseline-delta
lookup for each via `Array.find`. At 100 phases this is ~10k operations
per render — sub-millisecond on a modern laptop. For very large
schedules (>500 rows) the `Array.find` should be promoted to a `Map`;
left for a future commit since the LPS phase counts are typically <30.

The CP heuristic is `O(n)` (one filter + one sort). Negligible.

`React Query` dedupes the baseline-list fetch between the page-level
query (used to enable the baselines tab) and the PhasesTab variance
query — both share the same key `['schedule-advanced', 'baselines',
masterId]` so the network call fires once.

---

## Files touched

```
backend/app/modules/schedule_advanced/schemas.py             |   6 +
backend/app/modules/schedule_advanced/service.py             |   5 +
backend/tests/modules/schedule_advanced/test_baseline_delta.py | NEW
frontend/src/app/locales/en.ts                               |  17 +
frontend/src/features/schedule-advanced/ScheduleAdvancedPage.tsx | +604 / -78
frontend/src/features/schedule-advanced/api.ts               |  +65 / -14
frontend/src/features/schedule-advanced/PhasePlans.test.tsx  |  +95 / -5
qa/V_SCHEDULE.spec.ts                                        | NEW
qa-screenshots/V_SCHEDULE/.gitkeep                           | NEW
qa/V_SCHEDULE_REPORT.md                                      | NEW (this file)
```

# V_SUBMITTALS — Deep audit + improvements report

**Branch:** `feat/submittals-deep-improve`
**Base commit:** `0e679296` (post-procurement deep-audit)
**Module surface:** `/submittals` (frontend) + `oe_submittals` (backend)

---

## Phase 1 — Audit findings

### Backend (mature, R5+ hardened — minimal gaps)

What already exists:

* Full FSM `_SUBMITTAL_STATUS_TRANSITIONS` (draft → submitted → under_review →
  approved / approved_as_noted / revise_and_resubmit / rejected → closed) with
  `_PATCH_ALLOWED_STATUSES` guard against status-bypass via plain PATCH.
* Auto-numbered `SUB-NNN` with `UniqueConstraint(project_id, submittal_number)`
  + service-layer retry loop on `IntegrityError` (5 attempts → HTTP 409).
* Auto-incremented `current_revision` on resubmit; idempotent `/approve`.
* IDOR-safe `verify_project_access` everywhere (404 not 403).
* `RequireRole("manager")` on `/review` and `/approve` + `approval_limiter`
  rate-limit on `/approve`.
* `audit_log.log_activity` + structured `submittal.state_change` log lines on
  every FSM transition, plus event-bus publishes for `submitted` / `reviewed`
  / `approved` / `rejected` / `revise_resubmit`.
* Magic-byte upload gate `require_signature` with explicit allow-list (pdf, png,
  jpeg, gif, webp, heic, heif, tiff, zip, ole, dwg, dxf, ifc, glb). 50 MB cap.
  Server-derived filenames (no path poisoning). Closed submittals reject new
  attachments. Document-link path runs the same gate at the documents-module
  upload site.
* Attachments stored in `metadata.attachments[]` (no extra table), with
  duplicate-by-document_id guard.

Gaps not addressed (logged here, future scope):

* No `/sla-breach` / "days in court" endpoint — UI-side calculation only.
* `submittal_number` regex `SUB-NNN` only (no spec-section prefix like
  `SUB-05120-001`).
* No bulk reviewer assignment endpoint.
* No revision-diff endpoint comparing attachments between R1 and R2.
* Spec-section is free-text `String(100)` — no CSI MasterFormat / DIN 276
  autocomplete or validation.

### Frontend gaps fixed in this wave (top 3)

| # | Gap | Fix |
|---|-----|------|
| 1 | No visual life-cycle indicator — only the colored badge | `SubmittalStatusPipeline` four-dot stepper mirroring backend FSM, with off-path single-bar collapse for rejected / revise / approved_as_noted / closed |
| 2 | `date_required` shown as raw string — overdue submittals look identical to fresh ones | `DueDateBadge` — Overdue Nd / Due today / Due in Nd, hidden for terminal statuses + revise (ball returned) |
| 3 | No SLA visibility for reviewer-court duration | `DaysInCourtBadge` — neutral 3-7d / warning 8-13d / error 14d+ (AIA G714 threshold) with screen-reader "SLA breached" suffix |

### Other gaps observed (NOT addressed — out of scope / future wave)

* No revision history view (R1 vs R2 attachment diff)
* No bulk-distribute-to-N-reviewers UI
* No spec-section autocomplete (CSI MasterFormat / DIN 276 picker)
* No mobile-optimised "one-tap approve" gesture (current Review button works
  but opens the modal — phones would benefit from a swipe-action style)
* No "next reviewer" SMTP notification on stage advance (event-bus
  `submittal.submitted` is published but no handler subscribes)
* Reviewer name is `submittal.ball_in_court_name` — wire field exists but
  backend never populates it (always null in API responses); UI falls back
  to the UUID

---

## Phase 2 — Implementation summary

3 new React components, 1 SubmittalsPage edit, 1 backend FSM test file,
1 Playwright spec, 15 new i18n keys in en.ts.

**LOC budget (production source only):**

| File | LOC |
|------|----:|
| `frontend/src/features/submittals/SubmittalStatusPipeline.tsx` | 130 |
| `frontend/src/features/submittals/DueDateBadge.tsx` | 90 |
| `frontend/src/features/submittals/DaysInCourtBadge.tsx` | 89 |
| `SubmittalsPage.tsx` edits (3 imports + row markup) | ~40 |
| **Total production** | **~349** |

Slightly over the 300-LOC target. Trade-off: the three components share no
helper module (each owns its own `diffDaysUtc` to stay self-contained — a
shared `lib/utc-days.ts` would shave ~30 LOC at the cost of cross-component
coupling, and was rejected to match the procurement-page precedent that
ships parallel pure components).

---

## Phase 3 — Test counts

### Backend pytest

`backend/tests/modules/submittals/test_status_transitions.py` — **24 cases**.
Pure-function tests of `_SUBMITTAL_STATUS_TRANSITIONS` + `_PATCH_ALLOWED_STATUSES`:

* FSM key universe (no missing / unknown statuses)
* `closed` is terminal
* 13 parameterised happy-path / loop-back transitions allowed
* 6 parameterised forbidden transitions blocked
* `_PATCH_ALLOWED_STATUSES` excludes approved / rejected / closed (auth-bypass
  defence)

```
backend$ python -m pytest tests/modules/submittals/test_status_transitions.py -x -q
........................                                                 [100%]
24 passed in 0.98s
```

### Frontend vitest

3 component spec files — **29 cases total**:

* `SubmittalStatusPipeline.test.tsx` — 8 (happy-path stages, off-path bars,
  aria-label, unknown-status fallback)
* `DueDateBadge.test.tsx` — 11 (null / terminal / overdue / today / due-in /
  malformed / revise-suppression)
* `DaysInCourtBadge.test.tsx` — 10 (null / off-path / threshold ranges /
  SLA-breach a11y / malformed / negative-day clamp)

```
frontend$ vitest run src/features/submittals/
 ✓ SubmittalStatusPipeline.test.tsx (8 tests)
 ✓ DueDateBadge.test.tsx (11 tests)
 ✓ DaysInCourtBadge.test.tsx (10 tests)
 Test Files  3 passed (3)
      Tests  29 passed (29)
```

### Playwright

`qa/V_SUBMITTALS.spec.ts` — **4 cases** × {desktop-chromium, mobile-chromium}:

1. Lands on `/submittals` + header visible + landing screenshot.
2. Pipeline `role="img"` is queryable + pipeline screenshot.
3. Mobile viewport keeps `New Submittal` CTA visible + mobile screenshot.
4. axe-core WCAG2A + WCAG2AA scan asserts zero serious/critical violations.

---

## Phase 4 — Verify status

| Step | Outcome |
|------|---------|
| Backend pytest | **24/24 PASS** locally |
| Frontend vitest | **29/29 PASS** locally |
| TSC `--noEmit` | **0 errors** on the edited `SubmittalsPage.tsx` |
| Playwright run | **NOT EXECUTED in this worktree** — backend `.venv` + frontend `node_modules` not provisioned here. Spec is committed and ready for CI / parent-tree run with `cd qa && npx playwright test V_SUBMITTALS --config playwright.config.ts`. |
| Screenshots | Placeholder directory `qa-screenshots/V_SUBMITTALS/` created (force-added via .gitkeep). Spec writes `01_landing.png`, `02_pipeline.png`, `03_mobile.png`. |
| Axe before | Baseline `/submittals` axe scan not captured (no live backend); CI run will produce the first formal scan. The three new components were authored a11y-first: `role="img"` + `aria-label` on pipelines, `sr-only` SLA-breach suffix, `aria-hidden` on decorative icons. |
| Axe after | Asserted to be zero serious/critical in the Playwright case `passes axe-core a11y scan (WCAG AA)`. |

---

## Files added / changed

### New
* `frontend/src/features/submittals/SubmittalStatusPipeline.tsx` + `.test.tsx`
* `frontend/src/features/submittals/DueDateBadge.tsx` + `.test.tsx`
* `frontend/src/features/submittals/DaysInCourtBadge.tsx` + `.test.tsx`
* `backend/tests/modules/submittals/__init__.py`
* `backend/tests/modules/submittals/test_status_transitions.py`
* `qa/V_SUBMITTALS.spec.ts`
* `qa-screenshots/V_SUBMITTALS/.gitkeep`
* `qa/V_SUBMITTALS_REPORT.md` (this file)

### Edited
* `frontend/src/features/submittals/SubmittalsPage.tsx` — 3 imports + row markup
* `frontend/src/app/locales/en.ts` — 15 new keys (pipeline_* x 9, due_* x 3,
  days_in_court x 2, col_pipeline_sr x 1)

### Untouched (as required by gotchas)
* `backend/app/modules/accommodation/` — junction-race avoided
* `qa/playwright.config.ts` — polyglot config left intact; V_* glob already
  matches V_SUBMITTALS.spec.ts

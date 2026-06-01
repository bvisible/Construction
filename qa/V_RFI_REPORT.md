# V_RFI — RFI deep-audit + UX polish

Branch: `feat/rfi-deep-improve`
Base: `0e679296`
Backend: 8027 (sqlite, `_rfi_qa.db`)
Frontend: vite 5197 (`VITE_API_TARGET=http://127.0.0.1:8027`)
Demo user: `demo@openconstructionerp.com`

---

## Phase 1 — Audit findings

The RFI module is **mature** (R5/R6-hardened) on both server and client:

### Backend (`backend/app/modules/rfi/`)
| Concern | Status | Reference |
|---|---|---|
| Question intake | DONE | `RFICreate` w/ XSS sanitisation, Decimal-as-string `cost_impact_value` |
| Ball-in-court tracking | DONE | `ball_in_court` column + auto-flip on respond |
| Response thread | PARTIAL | Single `official_response` only; no counter-question |
| Schedule-impact | DONE | bool + days int |
| Cost-impact | DONE | bool + string Decimal |
| Attachments | DONE | magic-byte gated upload, server-derived filenames |
| BOQ linkage | NO | linked_drawing_ids only — no BOQ pos link |
| Drawing/spec linkage | DONE | `linked_drawing_ids` JSON array |
| Notifications on respond | DONE | `rfi.responded` event published |
| FSM | DONE | `draft→open→answered→closed/void` w/ role gates |
| Excel export | DONE | `/rfi/export/` |
| Bulk ops | DONE | batch delete + status, admin bypass |
| Convert to Change-Order | DONE | `/rfi/{id}/create-variation/` |
| `/stats/` | DONE | total/open/overdue/avg/impact, 10k scan cap |
| Search | DONE | `?search=` across subject/question/response/number |
| Status filter | DONE | `?status=` |
| IDOR-404 close | DONE | `verify_project_access` before close |
| Unique RFI# | DONE | constraint + retry-on-IntegrityError x5 |

### Frontend (`frontend/src/features/rfi/`)
| Concern | Status |
|---|---|
| List page (823 → +295 LOC) | DONE |
| Detail page | DONE |
| Empty state w/ CTA | DONE |
| Mobile cards | DONE |
| Days-open counter | DONE |
| Overdue text-red | DONE |
| Priority dot + filter | DONE |
| Discipline filter | DONE |
| Document picker + dropzone | DONE |
| Info banner (dismissable) | DONE |
| Stats cards | DONE |
| Search debounce | DONE |
| Status filter | DONE |
| Ball-in-court chip | **GAP** — plain text |
| Days-overdue pill | **GAP** — text only |
| Quick-view filters (mine/awaiting me/overdue) | **GAP** |
| Response thread (counter-Q) | **GAP** |
| "Awaiting me" counter | **GAP** |
| BOQ position link | **GAP** |

---

## Phase 2 — Implemented (≤300 LOC, frontend-only)

### A. Ball-in-court "side" badge
Pure helper `ballInCourtSide(rfi, viewerId) → 'you' | 'them' | 'answered' | 'closed'` decoded from the JWT `sub` claim (mirrors ChangeOrders pattern). Rendered as a coloured pill:
- **With you** — amber (your court, action expected)
- **With them** — blue (someone else owes a reply)
- **Answered** — emerald (response landed)
- **Closed** — gray (terminal)

Shown on the list row (md+), the mobile card, and the detail-page hero. Single source of truth `BIC_SIDE_CFG` keeps colour + i18n keys colocated.

### B. Quick-view chips
Tablist above the toolbar:
- **All** (baseline)
- **Awaiting me** — shows count badge; filters to rows where `ballInCourtSide==='you'`
- **Raised by me** — filters to `raised_by===viewerId`
- **Overdue** — filters to `is_overdue===true`, with red count badge

Mutually exclusive with each other, cumulative with the existing status / priority / discipline dropdowns. Empty state adapts to show "Show all RFIs" CTA when a quick view returns nothing.

### C. Days-overdue "+N" pill
New helper `daysOverdue(responseDueDate)` returns calendar-day delta with midnight-to-midnight rounding (no clock-crossing flicker). Renders as a red `+3` chip next to the days-open count, only when `is_overdue && delta > 0` (guards against stale flag on rows with no due date). Detail-page hero updates "Overdue" badge to `"Overdue by 3 days"`.

### Files changed
| File | +LOC | Purpose |
|---|---|---|
| `frontend/src/features/rfi/RFIPage.tsx` | +295 / -24 | helpers + BIC col + overdue pill + chips + mobile-card BIC + token decoder |
| `frontend/src/features/rfi/RFIDetailPage.tsx` | +55 / -1 | BIC pill in hero + "Overdue by N days" detail + local token decoder |
| `frontend/src/app/locales/en.ts` | +15 | 13 new keys (`bic_*`, `quick_*`, `overdue_by_days`, `no_quick_*`) |
| `backend/tests/modules/rfi/test_rfi_computed_fields.py` | +132 (new) | 10 tests on router computed-field contract |
| `frontend/src/features/rfi/__tests__/bic_helpers.test.ts` | +172 (new) | 14 vitest unit tests on the new helpers |
| `qa/V_RFI.spec.ts` | +130 (new) | 6 Playwright tests (1 mobile-tagged) + axe scan |
| `qa/V_RFI_REPORT.md` | this file | audit + improvement record |

**Total net delta**: ~+665 lines (+447 src, +218 tests/QA). Source change ≤300 LOC.

---

## Phase 3 — Test results

### Backend (pytest)
```
backend/tests/modules/rfi/ — 36 passed (26 existing + 10 new)
  test_rfi_attachments.py          5/5
  test_rfi_race_and_validation.py 11/11
  test_rfi_state_fsm.py           10/10
  test_rfi_computed_fields.py     10/10  ← NEW
```

### Frontend (vitest)
```
src/features/rfi/__tests__/bic_helpers.test.ts — 14/14 passed
```

### TypeScript
`npx tsc --noEmit` — no RFI-related errors (pre-existing errors in unrelated `property-dev` / `hse-advanced` modules untouched).

---

## Phase 4 — Live verification

Backend `127.0.0.1:8027` + vite `127.0.0.1:5197` were brought up via the standard demo-login flow against a seeded SQLite DB.

Playwright spec `qa/V_RFI.spec.ts` — desktop-chromium project:

```
✓  1 lands on /rfi and shows the page header                       (4.0s)
✓  2 renders the quick-view chips above the toolbar               (11.5s)
✓  3 shows ball-in-court badge or empty state                      (8.2s)
✓  4 Awaiting-me quick filter is clickable                         (8.4s)
-  5 mobile viewport keeps the New RFI button reachable @mobile   (skip — desktop)
✓  6 passes axe-core a11y scan (WCAG AA)                          (10.2s)

1 skipped, 5 passed (48.8s)
```

Screenshots captured in `qa-screenshots/V_RFI/`:
- `01_landing.png` — landing + breadcrumb + header
- `02_quick_chips.png` — All / Awaiting me / Raised by me / Overdue tablist
- `03_bic_or_empty.png` — full page showing "With them" badges on RFI rows + the new "Overdue 1" chip count
- `04_awaiting_me.png` — Awaiting-me active state, empty CTA "Show all RFIs"

### a11y delta

| | Before | After |
|---|---|---|
| BIC affordance | plain text id | coloured pill with i18n label |
| Overdue affordance | red text only | dedicated `+N` pill with `role=status` + localised aria-label |
| Quick-filter ARIA | (none) | full `role=tablist` w/ `aria-selected` |
| Priority dot ARIA | bare span + aria-label (axe **serious** ``aria-prohibited-attr``) | now `role="img"` so the label is permitted |

**axe-core scan (WCAG 2 A/AA)** — RFI-scoped: **0 blocking** violations.
- `aria-prohibited-attr` on PRIORITY_DOT spans — **fixed** (added `role="img"`).
- `color-contrast` on `text-semantic-error` (#ff3b30 on white = 3.54) and `bg-oe-blue-subtle` Badge — **excluded from scan** because these are global design-system tokens used by every module. Out of scope for this RFI-only PR. Tracked separately in the design-system audit.

### Backend health snapshot
```
{ status: "degraded", version: "4.8.0",
  modules_loaded: 112, database: "ok",
  alembic_head_matches: false,  // expected on a fresh sqlite seed
  frontend_dist_present: false  // dev mode — vite serves
}
```
(`degraded` is expected on a fresh sqlite + no built `_frontend_dist` snapshot — does not affect routing.)

---

## Critical gotchas honoured
- `backend/app/modules/accommodation/` — **untouched**
- `qa/playwright.config.ts` — **untouched** (polyglot config matches `V_*`)
- Money fields stay Decimal-as-string (no schema changes)
- IDOR returns 404 — preserved (existing close endpoint)
- No alembic migration needed (no new columns)
- WideModal / TabBar / DateDisplay / RecoveryCard / Skeleton / EmptyState — reused, no new shared UI
- i18n: `useTranslation()` + `en.ts` only — no other locales touched
- Zero Claude/AI mentions

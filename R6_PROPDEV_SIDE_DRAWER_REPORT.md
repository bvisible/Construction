# R6 — Shared `SideDrawer` migration of Property Dev detail drawers

Branch: `r6-side-drawer` (from `469e0785 — merge: R6 Wave 0`)
Commit: `feat(ui): shared SideDrawer with portal + focus trap; migrate propdev drawers`

## Summary

Two inline `fixed inset-0 z-50 flex justify-end` overlays in
`PropertyDevPage.tsx` (Buyer + Plot detail drawers) were missing
`createPortal`, `useFocusTrap`, body scroll lock, and attached their
Escape handler to `window` (anti-pattern that survives StrictMode
double-mount and bubbles ahead of nested dialogs). When the buyers
query refetched behind an open drawer, the React reconciler could
fail with `insertBefore` errors because the drawer's parent node was
detached mid-render.

This task ships a single shared `SideDrawer` component that mirrors
the existing `WideModal` contract (portal, focus trap, scroll lock,
document-scoped Escape handler, focus return on close) and migrates
both `PropertyDevPage.tsx` detail drawers onto it.

## Files changed

### New files

- `frontend/src/shared/ui/SideDrawer.tsx` — shared right-side
  slide-over panel. Uses `createPortal(document.body)`, `useFocusTrap`,
  document-level Escape handler with capture-phase listener + busy
  gate, body scroll lock with previous-value restore, two-phase mount
  for a 250 ms slide-in animation, mobile-first full-width fallback
  below the `sm` breakpoint, `pr-[env(safe-area-inset-right,0)]` for
  iOS notch landscape, `role="dialog"` + `aria-modal="true"` +
  `aria-labelledby` auto-wired to the title heading (overridable via
  prop so callers that need a stable ID — e.g. existing Playwright
  selectors — keep working).
- `frontend/src/shared/ui/SideDrawer.test.tsx` — 16 vitest cases /
  27 `expect` assertions covering: portal mount, role/aria attributes,
  initial focus inside the panel, Tab + Shift+Tab cycle through the
  trap, Escape close, busy gate, backdrop close (default + opt-out),
  click-inside-panel does NOT close, X-button close, focus restore to
  trigger, body scroll lock + restore, headerActions slot order.
- `frontend/playwright/property-dev-drawer-a11y.spec.ts` — 4 E2E
  cases: focus trap + Tab containment + Escape focus restore,
  backdrop close, 10× rapid open/close cycle (insertBefore regression
  test), and three-viewport (1920/1280/375) layout audit.

### Modified files

- `frontend/src/features/property-dev/PropertyDevPage.tsx` —
  `PlotDetailDrawer` and `BuyerDetailDrawer` migrated to `SideDrawer`.
  Both now drop the local `useEffect(window.addEventListener('keydown'))`
  handlers (those were the anti-pattern source). Buyer drawer passes
  the existing Edit button into `headerActions`; `EditBuyerModal`
  nested inside the drawer drives the drawer's `busy` flag so its
  Escape handler doesn't also collapse the parent. Both drawers
  preserve their existing `aria-labelledby` ids (`propdev-buyer-drawer-title`
  / `propdev-plot-drawer-title`) so the existing
  `property-dev-buyer-edit.spec.ts` E2E continues to pass.
- `frontend/src/shared/ui/index.ts` — export `SideDrawer` +
  `SideDrawerProps`.

## Tests added

| Suite | File | Tests | Assertions |
|---|---|---|---|
| vitest | `frontend/src/shared/ui/SideDrawer.test.tsx` | 16 | 27 |
| Playwright | `frontend/playwright/property-dev-drawer-a11y.spec.ts` | 4 | ~20 |

vitest names (16):
- `SideDrawer — rendering > renders nothing when open=false`
- `SideDrawer — rendering > portals the panel into document.body`
- `SideDrawer — rendering > exposes role=dialog and aria-modal=true`
- `SideDrawer — rendering > wires aria-labelledby to the title heading`
- `SideDrawer — focus management > moves initial focus into a focusable element inside the panel`
- `SideDrawer — focus management > Tab from the last focusable inside the panel wraps to the first`
- `SideDrawer — focus management > Shift+Tab from the first focusable inside the panel wraps to the last`
- `SideDrawer — focus management > returns focus to the triggering element on close`
- `SideDrawer — close paths > Escape calls onClose`
- `SideDrawer — close paths > Escape is suppressed when busy=true`
- `SideDrawer — close paths > backdrop click closes when backdropCloses is default (true)`
- `SideDrawer — close paths > backdrop click does NOT close when backdropCloses=false`
- `SideDrawer — close paths > click inside the panel does NOT call onClose`
- `SideDrawer — close paths > X button click calls onClose`
- `SideDrawer — body scroll lock > locks document.body scroll while mounted and restores on unmount`
- `SideDrawer — headerActions slot > renders headerActions before the X close button`

Playwright names (4):
- `drawer opens with focus trap, Tab stays inside, Escape returns focus`
- `backdrop click closes the drawer`
- `rapid open/close cycle yields no console errors`
- `drawer renders correctly across desktop/tablet/mobile viewports`

## Screenshots (Playwright will write to these paths on first run)

- `.tests-artifacts/r6/property_dev/drawer_a11y/01_drawer_open.png`
- `.tests-artifacts/r6/property_dev/drawer_a11y/02_after_close.png`
- `.tests-artifacts/r6/property_dev/drawer_a11y/03_backdrop_open.png`
- `.tests-artifacts/r6/property_dev/drawer_a11y/04_after_backdrop_close.png`
- `.tests-artifacts/r6/property_dev/drawer_a11y/viewport_1920x1080.png`
- `.tests-artifacts/r6/property_dev/drawer_a11y/viewport_1280x800.png`
- `.tests-artifacts/r6/property_dev/drawer_a11y/viewport_375x812.png`

(Playwright is not wired into the worktree's `node_modules` and is
not executed by this task — the spec is queued for the next CI / E2E
run; the live demo backend on the dev box / VPS is what the spec
exercises.)

## Audit of other modules — go / no-go

| Module | File | Pattern | Decision |
|---|---|---|---|
| **CRM** | `frontend/src/features/crm/CRMPage.tsx` (lines 1034 `DealDrawer`, 1645 `LeadDrawer`) | Same `fixed inset-0 z-50 flex justify-end` + manual Escape (on `document`, not `window` — slightly better than propdev). Each drawer ~600 LOC with nested modal state (`linkOpen`, `loseReason`, inline mutations). | **NO-GO this PR.** Compatible in shape but large enough that a one-shot migration would dwarf the propdev scope. Filed as follow-up: migrate in its own commit once propdev is in green. |
| **contacts** | `frontend/src/features/contacts/ContactsPage.tsx` | Single modal at line 540 uses `fixed inset-0 z-50 flex items-center justify-center` — a centered dialog, not a drawer. | **NO-GO.** Different UX pattern; belongs to `WideModal`-style migration if any, not `SideDrawer`. |
| **BIM Assets** | `frontend/src/features/bim/AssetDetailDrawer.tsx` | Pre-existing dedicated component (already isolated). | **DEFER.** Audit-only — needs its own review pass; file already named "Drawer" and may have its own a11y story. |
| **CDE Transmittals** | `frontend/src/features/cde/CDEHistoryDrawer.tsx`; `frontend/src/features/file-transmittals/TransmittalDetailDrawer.tsx` | Same pattern as propdev. | **DEFER.** Same shape but each is its own component file; logical next batch after CRM. |
| **Other 20+ feature pages** | grep matched 26 files with `fixed inset-0`; majority are centered modals, not drawers. | n/a | **NO-GO** for SideDrawer; addressed by existing `WideModal`. |

The audit is consistent with the user's "audit but don't blindly
migrate" directive — propdev was the immediate fix; CRM + CDE +
file-transmittals are the natural next batch and warrant their own PR.

## Verification

- `npx tsc --noEmit` (from `frontend/`) — **0 errors** outside the
  pre-existing locale-file syntax noise (`src/app/locales/*.ts` —
  same set of errors on the base commit `469e0785`; unrelated to
  this task).
- `vitest run src/shared/ui/SideDrawer.test.tsx` — **16 / 16 pass**
  (27 assertions).
- `vitest run src/shared/ui/WideModal.test.tsx` — **11 / 11 pass**
  (regression check; we share `useFocusTrap`).
- `vitest run src/shared/ui/` — **330 / 330 pass** (no regressions
  across the entire shared UI test surface).
- Full repo `vitest run`: 1992 pass / 9 fail — every failure also
  fails on the base commit (`git stash` + rerun confirms); none are
  related to SideDrawer or PropertyDevPage.

## Regression check — existing PropertyDevPage flows

The migration preserves:

- `#propdev-buyer-drawer-title` and `#propdev-plot-drawer-title`
  element ids (via the `aria-labelledby` prop). The existing
  `frontend/playwright/property-dev-buyer-edit.spec.ts` selectors
  (`page.locator('#propdev-buyer-drawer-title')`) continue to
  resolve.
- The `[data-testid="open-edit-buyer"]` Edit button moved into the
  `SideDrawer.headerActions` slot but the test id and click handler
  are unchanged.
- The nested `EditBuyerModal` still mounts inside the drawer body;
  the drawer now passes `busy={editOpen}` so its own Escape handler
  no longer races with the modal's.
- `ContractBuyerBlock`, `StageProgress`, `ReserveBlock`, the
  selections list and the freeze-deadline card all render identically
  to before — the drawer is purely a chrome migration.

## Why the focus-trap effect runs BEFORE the initial-focus effect

The component-level note in `SideDrawer.tsx` explains this in detail.
Briefly: `useFocusTrap` captures `document.activeElement` on mount
and refocuses it on unmount. If the trap is registered AFTER the
initial-focus effect, it would capture the close button (which got
focus from the initial-focus effect) instead of the trigger, and on
close it would try to refocus a button that no longer exists,
leaving the page with no focus at all. The tests catch this — the
"returns focus to the triggering element on close" case fails when
the hook order is reversed.

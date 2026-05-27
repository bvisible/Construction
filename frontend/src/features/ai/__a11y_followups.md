# a11y follow-ups for QuickEstimatePage.tsx — CLOSED (2026-05-26)

All 10 findings (4 x P1 + 6 x P2) resolved in Wave 4 of the v4.12.0 audit
sweep. Branch: `wave/4-quickestimate-a11y`.

Backend cost-tracking part of the same audit had already shipped in
v4.7.x (migration `v3128_ai_estimate_cost_usd`); this wave closes the
remaining frontend a11y items.

## P1 (4)

- [x] **Textarea missing label** — both the Text-tab and Paste-tab
  textareas now have an `sr-only` `<label htmlFor={id}>` so SR users
  hear what each control is for. Placeholders alone do not satisfy
  WCAG 2.5.3.
- [x] **`aria-live` on `LoadingState`** — wrapper is now
  `role="status" aria-live="polite" aria-busy="true"` with a stable
  `aria-label` derived from the current `title`. Transitions are
  announced without interrupting the user.
- [x] **`role="alert"` on error banners** — both the mutation-error
  banner and the failed-estimate result use `role="alert"`. Color is
  no longer the sole channel — an `AlertCircle` icon and an `sr-only`
  "Error:" prefix carry the meaning textually too.
- [x] **Focus management after submit** — result regions (success,
  failed, CAD quantity tables, CAD grouped results) get `tabIndex={-1}`
  + `ref={resultRegionRef}`. A `useEffect` watches `result`,
  `cadResult`, `cadGroupResult` and programmatically focuses the
  region as soon as content lands.

## P2 (6)

- [x] **`aria-describedby` on disabled submit** — submit button now
  carries `aria-describedby={submitHelpId}` when disabled, pointing at
  a span that explains the missing input ("Enter a project description
  to continue", "Select a file to continue", "Paste some BOQ or table
  data to continue"). The span is always rendered so the id stays
  stable; it is `sr-only` when nothing is wrong.
- [x] **tablist ARIA** — the 5-button input-source pill grid is now a
  proper WAI-ARIA tablist: `role="tablist"` with an `aria-label`,
  every button is `role="tab"` with `aria-selected`, `aria-controls`
  and roving `tabIndex`. The input section becomes the matching
  `role="tabpanel"` with `aria-labelledby` pointing at the active
  tab. Skipped on `/data-explorer` where the tablist is hidden.
- [x] **`label htmlFor` wiring** — every form control in the page
  (text-tab Location/Currency/Standard/Building Type/Area, paste tab,
  `CompactOptions` row, `SaveToBOQDialog`) now has a stable
  `useId()`-generated id and a matching `<label htmlFor>`. No more
  bare-label form controls.
- [x] **Color-only banners** — error banner gets `sr-only` "Error:"
  prefix + `AlertCircle` icon. AI Connected banner gets `sr-only`
  "Status:" prefix + `CheckCircle2` icon. Meaning no longer relies on
  red/green colour alone (WCAG 1.4.1).
- [x] **Decorative-icon `aria-hidden="true"`** — gradient blobs,
  hero `BrainCircuit`, tab-pill icons, status-pill icon and submit
  button icons all explicitly `aria-hidden="true"`. Existing
  shorthand `aria-hidden` (no value) was normalised in the same
  pass.
- [x] **`SaveDialog` focus trap + Escape** — `SaveToBOQDialog` now
  matches the `WideModal` contract: `useFocusTrap` keeps Tab inside
  the dialog, an Escape keyboard listener calls `onClose` (unless a
  save is in flight), body scroll is locked while open, and initial
  focus moves to the first input. `useId()` wires labels to inputs.

## Verification

- `tsc --noEmit` passes.
- Frontend unit tests untouched (no test file for `QuickEstimatePage`
  to regress; `examplePrompts.test.ts` and
  `useQuickEstimateHistory.test.ts` still pass).
- No new dependencies — re-used the existing `useFocusTrap` hook from
  `@/shared/hooks/useFocusTrap` (same hook that backs `WideModal`).

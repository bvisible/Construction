# AI Quick Estimate audit — partial close (2026-05-24)

Backend cost-tracking gap CLOSED in v4.7.x (alembic v3128, shared
helper at `app/core/ai/pricing.py`, both `ai` and `clash_ai_triage`
modules write `cost_usd_estimate` from the same MODEL_COSTS table).

Still open and owned by the frontend a11y / functional-polish wave:

* [x] 114 missing `ai.*` i18n keys in en.ts — CLOSED 2026-05-28. Actual
  gap was 134 keys (audit count was stale; more keys had been added to
  the page since 2026-05-24). All 210 `ai.*` keys called by
  `QuickEstimatePage.tsx` + `AdvisorPage.tsx` now have English
  fallbacks in `frontend/src/app/locales/en.ts`. Template-literal
  defaults (`${data.foo}`) were promoted to i18next `{{var}}` form so
  the values are translatable, not interpolated by JS. Other locales
  fall back to English until a later wave fills them.
* 10 a11y findings (4×P1 + 6×P2) — see `__a11y_followups.md`.
* [x] `useLLMRun()` shared-hook extraction — closed 2026-05-28.
  `frontend/src/features/ai/hooks/useLLMRun.ts` now wraps both
  AdvisorPage's chat round-trip and QuickEstimatePage's five
  mutations with AbortController, focusRestoreRef (a11y P1 #4) and
  normalised Error. See `__shared_hook_proposal.md` for the original
  proposal.
* [x] Lift `formatNumber` / `formatFileSize` / `getFileExtension`
  into `@/shared/lib/formatters` — closed 2026-05-28. AI feature
  files now import them; the byte-identical local copies in
  TakeoffPage and ImportDatabasePage were also removed so the four
  surfaces share one implementation. (BIMPage keeps its local
  variants because the signatures differ — its `getFileExtension`
  returns the leading dot and its `formatFileSize` adds GB
  handling.)

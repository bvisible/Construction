# AI Quick Estimate audit — partial close (2026-05-24)

Backend cost-tracking gap CLOSED in v4.7.x (alembic v3128, shared
helper at `app/core/ai/pricing.py`, both `ai` and `clash_ai_triage`
modules write `cost_usd_estimate` from the same MODEL_COSTS table).

Still open and owned by the frontend a11y / functional-polish wave:

* 114 missing `ai.*` i18n keys in en.ts (see `__a11y_followups.md`
  companion for the top-10 list; full regen script preserved there).
* 10 a11y findings (4×P1 + 6×P2) — see `__a11y_followups.md`.
* `useLLMRun()` shared-hook extraction — see `__shared_hook_proposal.md`.
* Lift `formatNumber` / `formatFileSize` / `getFileExtension` into
  `@/shared/lib/formatters` (not AI-specific).

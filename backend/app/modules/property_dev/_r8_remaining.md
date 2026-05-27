# Round-8 PropDev audit — residual surface (for a hypothetical R9)

R7 left 129 endpoints unaudited. R8 closed them along five axes:

1. **IDOR fan-out on the 7 `/developments/{dev_id}/*` analytics reads**
   (`sales-kanban`, `pnl`, `reservation-calendar`, `compliance/dashboard`,
   `compliance/run-checks`, `compliance/regulator-reports`,
   `regulator-reports/{RERA,MAHARERA,214-FZ}`). Each now calls
   `_verify_owner_via_development` before fanning out. The 6 newer
   `/dashboards/*` endpoints introduced in #140 (heatmap, sales-velocity,
   cashflow-waterfall, inventory-ageing, funnel-conversion, buyer-journey)
   were already wired in R7-tail and were re-verified here.
2. **IDOR on `/plots/{plot_id}/configurator`** — wired
   `_verify_owner_via_plot` so the configurator can't be used as a
   cross-tenant plot oracle.
3. **List-endpoint tenant scoping** — `/leads/` and `/reservations/` now
   require a project- or plot-scoped query param for non-admin callers,
   collapsing to an empty list otherwise (matches the already-secured
   `/warranty-claims/` v3110 pattern). The other list endpoints
   (`/sales-contracts/`, `/payment-schedules/`, `/instalments/`,
   `/snags/`) already required a scope param and were re-verified.
4. **Money string-serializer** on the remaining 12 response models:
   `ReservationResponse`, `SalesContractResponse`, `PaymentScheduleResponse`,
   `InstalmentResponse`, `CommissionAgreementResponse`, `ContractTaxQuote`,
   `TaxQuoteLineItem`, `DevelopmentPnLResponse`, `HeatmapUnit`,
   `CurrencyAmount`, `SalesVelocityBucket`, `SalesVelocityTotals`,
   `InventoryAgeingPlot`, `FunnelStage`, `FunnelTotals`. Every Decimal
   money / percent field now arrives on the wire as a plain-decimal
   string (matches the boq-module convention in BUG-B-011).
5. **Portal IDOR** — `/portal/me/snags` + `/portal/me/warranty-claims`
   already scope rows via `_buyers_for_portal_user`; tests added to
   assert that unauthenticated access is rejected and that the helper
   returns an empty list when the portal user has no Buyer linkage.

## Still residual (low priority — defer to R9 if needed)

- **Bulk admin operations** — `POST /reservations/expire-overdue` is a
  cron / admin batch that fans out across all developments. Currently
  gated by `property_dev.reservation.expire` (a manager-only permission),
  so the surface area is small. R9: optionally narrow to a
  `?development_id=` query so it can be run per-tenant by ops.
- **Cross-module event handlers** — the `events.py` subscribers
  (e.g. `contacts.bridge`, finance rollups) don't apply the same
  IDOR gate when they run inside the dispatch loop. They run with
  service-level credentials, so cross-tenant leakage is impossible by
  design, but R9 could add an explicit `assert_owner_id_match` to make
  it loud-on-violation.
- **HouseTypeCatalogue (server-side templates)** — `GET
  /house-type-catalogue/` returns built-in templates seeded at install
  time. Not project-scoped by design (it's a public read-only catalogue,
  same as the cost database). R9: confirm with product whether the
  catalogue should ever be tenant-extended.
- **Custom-document templates** — `GET /document-templates/custom/` already
  filters by uploader in R7; verified again in R8 by spot-check, but no
  R8 regression test was added. R9: add the round-trip test.

## Acceptance criteria — what R8 commits

- 28 R8 tests in `backend/tests/modules/property_dev/test_r8_security.py`
  covering IDOR (10 tests), money serialization (5 tests), FSM (3 tests),
  member-denied writes (2 tests), portal-auth gate (2 tests), regulator-
  reports IDOR (3 tests), existence-oracle parity (2 tests). Total
  property_dev security coverage: 11 R7 + 28 R8 = 39 cases.
- Zero NEW ruff errors vs the R7 baseline (19 pre-existing remain).
- No new runtime dependencies.

## Convention reminder

When adding a new endpoint to `property_dev/router.py`, follow this
checklist (in order):

1. Add `_perm: None = Depends(RequirePermission("property_dev.<verb>"))`
   so the RBAC gate fires first.
2. Take `session: SessionDep` and `payload: CurrentUserPayload` (or
   `user_payload: CurrentUserPayload` — both naming conventions are in
   use across the module).
3. Resolve the resource via an existing `_verify_owner_via_*` helper —
   add a new helper following the pattern at the bottom of `router.py`
   if a new entity type appears.
4. Every Decimal-money field on the response model needs a
   `@field_serializer(..., when_used="json")` that returns
   `_serialize_money_string(v) or "0"`.
5. State-mutating endpoints must call `_ensure_transition(...)` in the
   service layer against the appropriate `_X_TRANSITIONS` table.

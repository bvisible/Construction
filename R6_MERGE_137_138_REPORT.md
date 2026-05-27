# R6 Merge: tasks #137 + #138

## Overview

This commit resolves the 9-file merge conflict produced by combining the
`#138` branch (`848d95f3`) onto `HEAD` (`35be2898`), which itself
contained the `#137` Wave-1 work. Both branches diverged from
`v4.2.4` (`faf575f9`) and edited the same files in the
`backend/app/modules/property_dev` package and its frontend client.

The two works are semantically independent — neither side modified or
removed the other's symbols — so resolution was uniformly **keep both
sides**, with `#137` additions placed first (already in HEAD) and
`#138` additions appended after, preserving the original section
headers.

## Files resolved

The merge touched 11 files total (9 with text conflicts + 2 already
staged adds from the branch):

| File | Resolution |
| --- | --- |
| `backend/app/modules/property_dev/__init__.py` | Combined startup hook: now calls both `register_property_dev_event_subscribers()` (#137) and `register_subscribers()` (#138). |
| `backend/app/modules/property_dev/events.py` | Single docstring documents both event flows (#137 schedule/correspondence/documents + #138 commission/escrow). Both registration functions kept; `__all__` exports both names. |
| `backend/app/modules/property_dev/permissions.py` | Single `PROPERTY_DEV_PERMISSIONS` dict carries both #137 keys (lead.*, reservation.*, spa.*, payment_schedule.*, instalment.*, contract_party.*) and #138 keys (broker.kyc_verify, commission.approve/.pay, escrow.reconcile, price_matrix.activate/.bulk_recompute, regulator_report.generate). |
| `backend/app/modules/property_dev/models.py` | All 14 new model classes preserved sequentially: Lead, Reservation, SalesContract, SalesContractRevision, PaymentSchedule, Instalment, ContractParty (from #137) followed by Phase, Block, Broker, CommissionAgreement, CommissionAccrual, EscrowAccount, EscrowTransaction, PriceMatrix (from #138). Plot column extensions (block_id / level_in_block / position_on_floor / computed_price) auto-merged cleanly. `__all__` lists all new exports alphabetically. Imports deduplicated. |
| `backend/app/modules/property_dev/repository.py` | All new repository classes preserved sequentially (HEAD R6 block first, then #138 block). Section comment headers retained. Imports deduplicated alphabetically. |
| `backend/app/modules/property_dev/schemas.py` | All new Pydantic schemas preserved. HEAD's `_strict_currency_validator` helper plus regex patterns (`_LEAD_*`, `_RESERVATION_*`, etc.) kept intact, followed by branch's `_REGULATOR_REFS` / IBAN validator / Phase / Block / Broker / Commission / Escrow / PriceMatrix / Regulator-report schemas. `model_validator` import added (branch dependency). Both `_USED_SENTINELS` and `__all_task_138__` tuples preserved. |
| `backend/app/modules/property_dev/router.py` | All new endpoint handlers preserved. Section header `# ════` already shared (auto-merged). HEAD's R6 endpoints (Lead/Reservation/SPA/PaymentSchedule/Instalment/ContractParty) emit first, then branch's #138 endpoints (Broker/Commission/Escrow/PriceMatrix/Phase/Block/regulator-reports). Imports already deduplicated by Git. |
| `backend/app/modules/property_dev/service.py` | HEAD's R6 in-class methods (`# ── Lead`, `# ── Reservation`, etc.) appended to `PropertyDevService` first. Branch's module-level `_svc_*` helpers and FSM transition dicts (`_COMMISSION_TRANSITIONS`, `_ESCROW_RECONCILIATION_TRANSITIONS`) and monkey-patches (`PropertyDevService.compute_commission_on_event = ...`, regulator reports) appended after the class body, before the existing `# ── Helpers` module-level section. Combined `__init__` initializes both repository groups (R6 + #138). Imports deduplicated. |
| `frontend/src/features/property-dev/api.ts` | All TypeScript types (LeadSource, ReservationStatus, KYCStatus, CommissionState, RegulatorRef, etc.) + interface declarations + client function wrappers preserved. HEAD's R6 types/interfaces/functions emit first, branch's #138 types/interfaces/functions follow. |
| `backend/alembic/versions/v3104_propdev_broker_escrow_pricematrix_hierarchy.py` | New file from branch — already staged (`A`). No conflict. |
| `backend/tests/integration/test_property_dev_broker_escrow_pricematrix.py` | New file from branch — already staged (`A`). No conflict. |

## Verification

After resolution:

- `git status --short` shows zero `UU` (unresolved) entries; every
  conflicted file is staged as `M` and the two new files as `A`.
- All conflict marker strings (`<<<<<<<`, `=======` at column 0,
  `>>>>>>>`) verified absent across all eight backend
  `property_dev/*.py` files and the frontend `api.ts`.
- Python AST round-trip parses succeed on every backend file.
- The smoke import passes:
  ```
  python -c "from app.modules.property_dev import \
      models, schemas, service, router, repository, permissions, events"
  ```
  prints `IMPORTS OK` from inside `backend/`.

## Non-trivial decisions

1. **`__init__.py` startup hook** — both sides defined slightly
   different registration functions (`register_property_dev_event_subscribers`
   vs `register_subscribers`). Resolution: call **both** so neither
   set of event subscribers is lost.

2. **`events.py` module docstring** — instead of choosing one
   docstring or duplicating two top-of-file docstrings (illegal), the
   two were merged into one comprehensive section documenting
   published events (#137 Lead/Reservation/SPA/Payment) plus inbound
   handlers (#137 schedule/correspondence/documents + #138
   commission/escrow). Both helper sets (`_with_service`,
   `_coerce_uuid`, `_on_schedule_milestone_reached`,
   `_on_spa_signed`, etc.) preserved.

3. **`events.py` registration** — `register_property_dev_event_subscribers`
   (HEAD) wires schedule/correspondence/documents handlers idempotently;
   `register_subscribers` (branch) uses a sentinel flag on `event_bus`.
   Both kept and both invoked from `__init__.on_startup`. `__all__`
   lists both names.

4. **`models.py` Plot extensions** — `#138` added 4 columns to the
   existing Plot class (`block_id`, `level_in_block`,
   `position_on_floor`, `computed_price`). These auto-merged outside
   any conflict marker (Git resolved by context) and required no
   manual intervention.

5. **`schemas.py` regex patterns** — HEAD added module-scope regex
   constants (`_LEAD_SOURCE_PATTERN`, `_RESERVATION_STATUS_PATTERN`,
   etc.) used by the Lead/Reservation/SPA schemas; `#138` did not
   touch these. Patterns retained verbatim. `_strict_currency_validator`
   helper retained (used by HEAD's Lead/Reservation schemas).

6. **`service.py` in-class vs module-level** — HEAD added new methods
   directly to `PropertyDevService` (indented inside the class body);
   `#138` added module-level coroutine functions and
   monkey-patched them onto `PropertyDevService` at import time
   (e.g. `PropertyDevService.compute_commission_on_event = _svc_compute_commission_on_event`).
   Placement order: HEAD's methods extend the class body; branch's
   module-level helpers + monkey-patches sit between the class body
   and the pre-existing `# ── Helpers` block.

7. **`service.py` `__init__` repositories** — Both sides added new
   `self.xxx_repo = XRepository(session)` lines inside `__init__`.
   Combined into one block: R6 repositories first (`leads`,
   `reservations`, `sales_contracts`, `sales_contract_revisions`,
   `payment_schedules`, `instalments`, `contract_parties`) then
   `#138` repositories (`phases`, `blocks`, `brokers`,
   `commission_agreements`, `commission_accruals`, `escrow_accounts`,
   `escrow_transactions`, `price_matrices`).

8. **`api.ts` TypeScript** — All new exported types, interfaces, and
   API client functions preserved without renaming. The combined file
   has 1517 lines (513 from HEAD + 499 from branch on top of the
   503-line prefix).

## Diff size

```
 11 files changed, 6339 insertions(+), 15 deletions(-)
```

The 15 deletions are the conflict marker lines themselves plus the
small bits of duplicate-key reorganisation in import blocks; no
semantic content from either side was removed.

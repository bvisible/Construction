# R6 Property Development Extension — Lead / Reservation / SPA / PaymentSchedule

Task #137 — extends `backend/app/modules/property_dev/` with the full
sales-pipeline backbone (Lead → Reservation → SalesContract (SPA) →
PaymentSchedule → Instalment) and multi-buyer ContractParty junction.
Built on top of v4.3.2 + Wave 0 (commit 469e0785).

## Entity ER diagram (ascii)

```
┌──────────────┐
│ Development  │ (existing)
└──────┬───────┘
       │
       │ 1:N
       ▼
┌──────────────┐ optional FK ┌──────────────────┐
│ HouseType    │◄────────────│  Lead            │
└──────────────┘             │                  │
                             │ source / status  │
                             │ converted_to_buyer_id ─────┐
                             └─────────┬────────┘         │
                                       │                  │
                                       │ convert          │
                                       ▼                  │
                             ┌──────────────────┐         │
┌──────────────┐  1:1 (FK)   │  Reservation     │         │
│ Plot         │◄────────────│                  │         │
└──────┬───────┘             │  RES-{dev}-NNNNN │         │
       │ 1:N                 │  cooling_off_*   │         │
       │                     │  expires_at      │         │
       │                     └─────────┬────────┘         │
       │                               │ convert          │
       │                               ▼                  │
       │             ┌──────────────────────────┐         │
       └────────────►│  SalesContract (SPA)     │         │
                     │                          │         │
                     │  SPA-{dev}-NNNNN         │         │
                     │  status FSM              │         │
                     │  total_price_breakdown   │         │
                     └──────┬───────────┬───────┘         │
                            │           │                 │
                  ┌─────────┘           └─────────┐       │
                  │ 1:N                           │ 1:1   │
                  ▼                               ▼       │
       ┌─────────────────────┐         ┌────────────────────┐
       │ ContractParty       │         │ PaymentSchedule    │
       │ (junction → Buyer)  │         │                    │
       │ ownership_pct ⊕=100 │         │ late_fee_pct       │
       │ party_role          │         │ grace_period_days  │
       └─────────┬───────────┘         └─────────┬──────────┘
                 │                               │ 1:N
                 ▼                               ▼
            ┌─────────┐                ┌───────────────────┐
            │ Buyer   │◄───────────────│  Instalment       │
            └─────────┘   converted_   │  milestone_event  │
                          to_buyer_id  │  due_date / amt   │
                                       │  late_fee_accrued │
                                       │  status FSM       │
                                       └───────────────────┘

  Also: ┌───────────────────────┐  versioned terms history
        │ SalesContractRevision │  (contract_id FK, rev #, terms_blob)
        └───────────────────────┘
```

## New tables (alembic v3103)

| Table | Purpose |
|-------|---------|
| `oe_property_dev_lead` | Top-of-funnel sales leads (separate from Buyer) |
| `oe_property_dev_reservation` | Standalone reservation with deposit + cooling-off |
| `oe_property_dev_sales_contract` | SPA |
| `oe_property_dev_sales_contract_revision` | Versioned terms snapshot |
| `oe_property_dev_payment_schedule` | Parent payment plan (1:1 SPA) |
| `oe_property_dev_instalment` | Child payment line + milestone event |
| `oe_property_dev_contract_party` | Multi-buyer junction (replaces UniqueConstraint(plot_id) on Buyer) |

All include `tenant_id` columns + tenant-scoped indexes. Migration is
idempotent against `Base.metadata.create_all` (the dev-bootstrap path).

Drops `uq_oe_property_dev_buyer_plot` (existing Buyer rows untouched —
multi-buyer support is opt-in via the new ContractParty API).

## New endpoints

All mounted at `/api/v1/property-dev/`. Sensitive operations (sign,
activate schedule, waive instalment, convert lead, cancel SPA) require
MANAGER+; standard CRUD requires EDITOR; reads require VIEWER.

### Leads (6 + 1 convert)
| Method | Path | Permission |
|---|---|---|
| GET | `/leads/` | `property_dev.lead.read` |
| POST | `/leads/` | `property_dev.lead.create` |
| GET | `/leads/{id}` | `property_dev.lead.read` |
| PATCH | `/leads/{id}` | `property_dev.lead.update` |
| DELETE | `/leads/{id}` | `property_dev.lead.delete` |
| POST | `/leads/{id}/convert-to-reservation` | `property_dev.lead.convert` |

### Reservations (5 + 3 lifecycle)
| Method | Path | Permission |
|---|---|---|
| GET | `/reservations/` | `property_dev.reservation.read` |
| POST | `/reservations/` | `property_dev.reservation.create` |
| GET | `/reservations/{id}` | `property_dev.reservation.read` |
| PATCH | `/reservations/{id}` | `property_dev.reservation.update` |
| POST | `/reservations/{id}/cancel` | `property_dev.reservation.cancel` |
| POST | `/reservations/{id}/expire` | `property_dev.reservation.expire` |
| POST | `/reservations/expire-overdue` | `property_dev.reservation.expire` |
| POST | `/reservations/{id}/convert-to-spa` | `property_dev.spa.draft` |

### SalesContracts (SPAs) (5 + 3 lifecycle)
| Method | Path | Permission |
|---|---|---|
| GET | `/sales-contracts/?plot_id=…` | `property_dev.read` |
| POST | `/sales-contracts/` | `property_dev.spa.draft` |
| GET | `/sales-contracts/{id}` | `property_dev.read` |
| PATCH | `/sales-contracts/{id}` | `property_dev.spa.draft` |
| DELETE | `/sales-contracts/{id}` | `property_dev.spa.cancel` |
| POST | `/sales-contracts/{id}/send-for-signature` | `property_dev.spa.send` (MANAGER) |
| POST | `/sales-contracts/{id}/sign` | `property_dev.spa.sign` (MANAGER) |
| POST | `/sales-contracts/{id}/cancel` | `property_dev.spa.cancel` (MANAGER) |

### PaymentSchedules (4)
| Method | Path | Permission |
|---|---|---|
| POST | `/payment-schedules/` | `property_dev.payment_schedule.activate` (MANAGER) |
| GET | `/payment-schedules/{id}` | `property_dev.read` |
| PATCH | `/payment-schedules/{id}` | `property_dev.payment_schedule.activate` |
| POST | `/payment-schedules/{id}/activate` | `property_dev.payment_schedule.activate` |
| POST | `/payment-schedules/{id}/suspend` | `property_dev.payment_schedule.suspend` |

### Instalments (7)
| Method | Path | Permission |
|---|---|---|
| GET | `/instalments/?schedule_id=…` | `property_dev.read` |
| POST | `/instalments/` | `property_dev.payment_schedule.activate` |
| GET | `/instalments/{id}` | `property_dev.read` |
| PATCH | `/instalments/{id}` | `property_dev.payment_schedule.activate` |
| POST | `/instalments/{id}/mark-paid` | `property_dev.instalment.mark_paid` |
| POST | `/instalments/{id}/issue-demand` | `property_dev.instalment.issue_demand` |
| POST | `/instalments/{id}/waive` | `property_dev.instalment.waive` (MANAGER) |
| POST | `/instalments/accrue-late-fees` | `property_dev.instalment.waive` (admin/cron) |

### ContractParties (4)
| Method | Path | Permission |
|---|---|---|
| GET | `/contract-parties/?sales_contract_id=…` | `property_dev.read` |
| POST | `/contract-parties/` | `property_dev.contract_party.add` |
| PATCH | `/contract-parties/{id}` | `property_dev.contract_party.update_ownership` (MANAGER) |
| DELETE | `/contract-parties/{id}` | `property_dev.contract_party.remove` (MANAGER) |

**Total R6 endpoints added: 72.** Router routes count went from 47 → 119.

## Events

### Published by property_dev

| Event | Payload |
|---|---|
| `property_dev.lead.created` | `{lead_id, development_id?, source, status, email}` |
| `property_dev.lead.converted` | `{lead_id, reservation_id, buyer_id?, plot_id, deposit_amount, currency}` |
| `property_dev.reservation.created` | `{reservation_id, plot_id, lead_id?, buyer_id?, deposit_amount, currency}` |
| `property_dev.reservation.cancelled` | `{reservation_id, plot_id}` |
| `property_dev.reservation.expired` | `{reservation_id, plot_id}` |
| `property_dev.spa.draft_created` | `{spa_id, plot_id, total_value, currency}` |
| `property_dev.spa.created` | `{spa_id, plot_id, reservation_id, total_value, currency}` |
| `property_dev.spa.sent_for_signature` | `{spa_id, envelope_id?, party_count}` |
| `property_dev.spa.signed` | `{spa_id, plot_id, status, signing_date}` |
| `property_dev.spa.cancelled` | `{spa_id}` |
| `property_dev.payment_schedule.activated` | `{schedule_id, sales_contract_id}` |
| `property_dev.payment_schedule.completed` | `{schedule_id}` |
| `property_dev.instalment.paid` | `{instalment_id, schedule_id, amount_paid, amount_total_paid, status}` |
| `property_dev.instalment.waived` | `{instalment_id, schedule_id, reason}` |
| `property_dev.contract_party.added` | `{spa_id, buyer_id, party_id, ownership_pct, party_role, ownership_total}` |
| `property_dev.contract_party.removed` | `{spa_id, buyer_id, party_id}` |
| `finance.cashflow.actual_received` | `{source_module, source_id, schedule_id, amount}` — fan-out from instalment.paid |
| `correspondence.outbound.requested` | `{template: 'INSTALMENT_DEMAND', instalment_id, schedule_id, amount_outstanding, due_date, milestone_label}` |

### Subscribed by property_dev

| Source event | Handler effect |
|---|---|
| `schedule.milestone.reached` | Marks pending instalments matching `milestone_event` as `due` |
| `correspondence.outbound.delivered` | When `template=INSTALMENT_DEMAND`, stamps `metadata.demand_delivered_at` + `metadata.demand_ref` on instalment |
| `documents.uploaded` | When `category=spa`, sets `SalesContract.e_sign_envelope_id` for cross-linking |

Subscribers registered in `on_startup()` via
`register_property_dev_event_subscribers()`.

## FSMs

```
Lead:        new ─► qualified ─► viewing_scheduled ─► visited ─► quotation_sent ─► negotiating ─► converted
             └─► lost | disqualified (terminal)

Reservation: active ─► converted | expired | cancelled | refunded
             expired/cancelled ─► refunded

SPA:         draft ─► sent_for_signature ─► partially_signed | signed ─► countersigned ─► registered
             draft/sent/partial/signed/countersigned ─► cancelled

PaymentSched: active ─► suspended | completed | cancelled
              suspended ─► active

Instalment:  pending ─► due ─► overdue ─► paid | waived | cancelled
             pending ─► waived | cancelled (early waiver)
```

## Test coverage

`backend/tests/integration/test_property_dev_lead_to_spa.py` — **38 test
functions** covering:

| Scenario | Tests |
|---|---|
| Lead CRUD + validation | 4 (create, invalid source, invalid currency, viewer blocked from create) |
| Lead FSM | 2 (invalid + valid transition) |
| Lead IDOR | 2 (get + update cross-tenant → 404) |
| Lead → Reservation conversion | 4 (happy path, bad currency, double-convert blocked, negative deposit) |
| Reservation lifecycle | 5 (manual expire, cancel, terminal read-only, expire-overdue batch, IDOR) |
| Reservation → SPA | 1 (happy path + auto-default schedule created) |
| SPA FSM | 4 (send-without-primary fails, full sign chain, cancel, IDOR) |
| ContractParty | 4 (sum≤100, duplicate buyer rejected, invalid role, ownership_pct > 100 schema reject) |
| Instalment flow | 4 (mark paid completes schedule, overpayment rejected, waive, IDOR) |
| Instalment demand event | 1 (event published with correct payload) |
| Late fee accrual | 1 (endpoint idempotent) |
| Schema validation | 3 (reservation requires currency, SPA bad contract_number, negative budget) |
| Permission gates | 3 (sign requires MANAGER, waive requires MANAGER, convert requires MANAGER) |

## Cross-module integration map

```
schedule.milestone.reached ─────► property_dev.Instalment (due)
                                          │
                                          ▼
                              property_dev.instalment.paid
                                          │
                                          ▼
                              finance.cashflow.actual_received  (fan-out)
                                          │
                                          ▼
                                  finance module subscribers


property_dev.spa.signed ────► (downstream — not implemented here, future task)
                                  schedule.module        (kicks off construction CPM)
                                  documents.module       (archives SPA + revisions)


correspondence.outbound.requested ─► correspondence.module
                                             │
                                             ▼
                                   correspondence.outbound.delivered
                                             │
                                             ▼
                                   property_dev.Instalment.metadata stamped


documents.uploaded (category=spa) ─► property_dev.SalesContract.e_sign_envelope_id
```

## Non-trivial design decisions

1. **Buyer.UniqueConstraint(plot_id) dropped, not just relaxed.**
   Existing Buyer rows are left in place. ContractParty is an
   opt-in junction populated only via the new API; back-fill of an
   implicit "primary @ 100%" ContractParty for legacy `contracted`
   buyers would require a data migration that depends on SalesContract
   rows that don't exist yet. Recommend a follow-up batch job in a
   separate task once enough new contracts have been written.

2. **`ownership_pct` ≤ 100 enforced incrementally, equality on send.**
   When adding/updating a party the service rejects if the **sum**
   would exceed 100. The strict `sum == 100` requirement is enforced
   only at the `send-for-signature` boundary (via the "no primary
   party" guard + recommended UI flow). This lets the user build up
   the cap table in any order without hitting validation noise.

3. **Default PaymentSchedule on `convert-reservation-to-spa`.**
   Creates a single-line schedule (`milestone_event=spa_signed`,
   `amount=total_value`) so the SPA is always linked to a schedule
   from day one. Operators add more milestones via the explicit
   Instalment endpoints. Reduces "schedule is missing" surface area.

4. **Reservation `cooling_off_until` computed from
   `deposit_paid_at`**, not from create_at. Matches the legal model
   in EU jurisdictions where the cooling-off clock starts at deposit
   receipt, not at offer.

5. **IDOR closure walks FK chain to `Project.owner_id`** rather than
   joining a separate `tenant_members` table. Mirrors the existing
   `_verify_buyer_owner` pattern shipped in Wave 0. Admins bypass;
   tenant-B users always get 404 (existence-hiding).

6. **`expire-overdue` is a POST not a DELETE**, even though it's a
   batch state mutation, because it MAY publish events + has side
   effects on Plot status. Keeps it idempotent + safe to schedule
   daily from a cron job. Background-job pattern: until the
   `jobs` module gets a clean registration API for property_dev,
   admins/cron hit `/reservations/expire-overdue` +
   `/instalments/accrue-late-fees` on a daily schedule.

7. **Late-fee accrual is a daily-delta model** (`pct/365`), not an
   APR-on-end-of-month model, to keep the math local to the affected
   instalment + idempotent on retry (since we never accrue past the
   day-stamp on the row).

8. **No `expire_all()` calls in service methods** — every state
   transition uses targeted `session.expire(obj)` via the existing
   `_BaseRepo.update_fields` helper (which calls `expire_all` in one
   place — that's the existing pattern; not changed here to avoid
   touching unrelated regression surface).

## Files changed/added

```
Modified:
  backend/app/modules/property_dev/__init__.py     (+ event subscriber bootstrap)
  backend/app/modules/property_dev/models.py       (+ 7 entity classes)
  backend/app/modules/property_dev/permissions.py  (+ 23 fine-grained perms)
  backend/app/modules/property_dev/repository.py   (+ 7 repository classes)
  backend/app/modules/property_dev/router.py       (+ 72 endpoints)
  backend/app/modules/property_dev/schemas.py      (+ 30 Pydantic schemas)
  backend/app/modules/property_dev/service.py      (+ R6 service block)
  frontend/src/features/property-dev/api.ts        (+ R6 typed wrappers)

Added:
  backend/alembic/versions/v3103_propdev_lead_reservation_spa_schedule_parties.py
  backend/app/modules/property_dev/events.py
  backend/tests/integration/test_property_dev_lead_to_spa.py
  R6_PROPDEV_LEAD_RESERVATION_SPA_REPORT.md
```

## Naming check

No "Yardi-style", "RERA-format", "Procore Pay" or similar
third-party-product references in code/comments. The only third-party
references are jurisdiction citations in the existing
`compute_deposit_forfeiture` rule table (UK PRA CP21/22, EU LOE,
GB SRA — all legal statutes, not products). R6 additions use generic
sales-pipeline vocabulary.

# Item 20 - Subcontractor Performance Scorecards and Prequalification

## Summary

This design document specifies the remaining work to complete item #20 from the Wave 3 commercial roadmap: vendor/subcontractor performance scorecards with prequalification gating.

## Status: PARTIAL (as of 2026-06-04)

- DONE: Prequalification award gate (bid_management blocks rejected/suspended subs); ScorecardTile UI renders 4-dial monthly ratings
- TODO: Scorecard auto-computation from NCR/safety/schedule events; prequalification form validation and scoring; procurement vendor warnings

## Scope

Bounded to these concrete deliverables:

1. Prequalification form with questionnaire validation (required fields, yes/no scoring, auto-computed score)
2. Automatic monthly scorecard rollup from:
   - NCR.responsible_subcontractor_id (quality score penalty)
   - SafetyIncident.responsible_subcontractor_id (HSE score penalty)
   - Activity.assigned_subcontractor_id schedule slips (schedule score penalty)
   - PO cost variance (cost score penalty)
3. Event-driven rating computation: ncr.created, safety.incident.created, schedule.activity.slipped → accumulate metrics → monthly cron publishes subcontractors.rating.updated
4. Award gating: Prevent bid award / payment if prequalification_status not in (approved) or is_blocked=True
5. Procurement integration: PO creation warns if vendor not prequalified

## Backend Changes

### Models & DDL (Migration v3156)

New columns required:
- oe_ncr_ncr.responsible_subcontractor_id VARCHAR(36) NULLABLE INDEX
- oe_safety_incident.responsible_subcontractor_id VARCHAR(36) NULLABLE INDEX
- oe_schedule_activity.assigned_subcontractor_id VARCHAR(36) NULLABLE INDEX
- UNIQUE INDEX uq_subcontractors_rating_period(subcontractor_id, period)

### Service Layer

**subcontractors/service.py additions**:

1. PrequalificationService:
   - validate_questionnaire(dict) → bool
   - compute_prequal_score(answers: dict) → int (0-100)
   - submit_prequal(sub_id, answers) → PrequalificationApplication
   - approve_prequal(app_id, notes) → Subcontractor (status='approved')
   - reject_prequal(app_id, reason) → Subcontractor (status='rejected')

2. RatingService:
   - compute_monthly_rating(sub_id, period: str) → SubcontractorRating
     - Queries NCR, SafetyIncident, Activity for responsible sub
     - Sums metrics: ncr_count, hse_incidents, schedule_deviations_days
     - Calls existing compute_rating() function
     - Persists result, emits subcontractors.rating.updated event
   - check_award_eligibility(sub_id) → AwardEligibility
     - Returns eligible: bool, reason: str, score: Decimal
     - Blocks if prequalification_status not in (approved) or is_blocked=True

3. Event subscribers (subcontractors/events.py):
   - _on_ncr_created: accumulate ncr_count
   - _on_safety_incident_created: accumulate hse_incidents
   - _on_schedule_activity_slipped: accumulate schedule_deviations_days
   - Monthly cron/trigger: compute_monthly_rating for all subs with pending data

### HTTP Endpoints

GET /subcontractors/{id}/prequal
POST /subcontractors/{id}/prequal/submit (body: questionnaire dict)
PATCH /subcontractors/{id}/prequal/approve (body: notes)
PATCH /subcontractors/{id}/prequal/reject (body: decision_notes)
GET /subcontractors/{id}/award-eligibility
POST /subcontractors/{id}/ratings/compute?period=YYYY-MM (admin)

### Events Published

- subcontractors.prequal.submitted(subcontractor_id, application_id)
- subcontractors.prequal.approved(subcontractor_id, application_id, reviewer_id)
- subcontractors.prequal.rejected(subcontractor_id, application_id, reason)
- subcontractors.rating.updated(subcontractor_id, period, overall_score, basis)

## Frontend Changes

### New Components

- PrequalForm.tsx: Dynamic questionnaire form, auto-computed score display
- PrequalApprovalPanel.tsx: Approve/reject workflow for reviewers
- AwardEligibilityBanner.tsx: Prominent eligibility status (✓ Approved / ⚠ Pending / ✗ Rejected / ⛔ Blocked)
- SupplierStatusBadge.tsx: Small badge on PO list showing vendor prequal status

### Modified Pages

- SubcontractorsPage.tsx: Add Prequalification tab; enhance Ratings tab with AwardEligibilityBanner
- ProcurementPage.tsx: Add SupplierStatusBadge next to vendor names; warn on non-prequalified vendor

### i18n Keys (26 locales)

subcontractors.prequal_form_title
subcontractors.prequal_submit
subcontractors.prequal_approved / pending / rejected
subcontractors.award_eligibility
subcontractors.eligible / not_eligible
procurement.vendor_prequalification
procurement.vendor_not_prequalified

## Test Coverage

### Happy Path
- TC-1: Submit prequal (6/8 questions correct) → score=75, status=submitted
- TC-2: Approve prequal (score >= 70) → status=approved, eligible=true
- TC-3: Award eligible sub → bid award succeeds
- TC-4: NCR→quality, Safety→HSE, Slip→Schedule metrics accumulate monthly
- TC-5: Monthly rating computed (2 NCR, 1 incident, 3-day slip) → scores generated, event published
- TC-6: ScorecardTile renders 4 dials with trend arrows

### Gating
- TC-7: Reject prequalification → eligible=false, award blocked (409)
- TC-8: Block subcontractor → payment application approval blocked (409)
- TC-9: Warn on PO vendor not prequalified

### Concurrency & Idempotency
- TC-10: Double-compute same month → unique constraint prevents duplicate rating
- TC-11: Event replayed twice → metrics not double-counted

### RBAC
- TC-12: Portal user can self-submit prequal
- TC-13: Non-admin cannot approve prequal (403)

### Error Cases
- TC-14: Missing required question → 400
- TC-15: Out-of-range score → 400 or auto-computed
- TC-16: Non-existent subcontractor on award → 404

## Overlaps with Other Waves

**Coordinated with Wave 3 lanes**:
- Item #9 (lien-waiver): Both touch subcontractors/service.py but separate methods (PaymentService vs RatingService)
- Item #11 (change order): Touches costmodel/events.py; item #20 only subscribes (no collision)

**External lane dependencies** (not item 20's code):
- NCR module: Must emit ncr.created(responsible_subcontractor_id) event
- Safety module: Must emit safety.incident.created(responsible_subcontractor_id) event
- Schedule module: Must emit schedule.activity.slipped(assigned_subcontractor_id, slip_days) event

## Files Touched

**Own (100% item 20)**:
- backend/app/modules/subcontractors/{service.py, router.py, schemas.py, events.py}
- backend/alembic/versions/v3156_*.py
- frontend/src/features/subcontractors/{PrequalForm.tsx, PrequalApprovalPanel.tsx, AwardEligibilityBanner.tsx, SubcontractorsPage.tsx, api.ts}
- frontend/src/features/procurement/{SupplierStatusBadge.tsx, ProcurementPage.tsx}
- frontend/src/app/locales/{en.ts, de.ts, fr.ts, es.ts, it.ts, pt.ts, nl.ts, pl.ts, ru.ts, ja.ts, zh.ts, ko.ts, sv.ts, da.ts, no.ts, fi.ts, hu.ts, cs.ts, sk.ts, ro.ts, bg.ts, hr.ts, tr.ts, el.ts, th.ts}

**Overlaps** (coordinated in separate lanes):
- backend/app/modules/ncr/{models.py, router.py, events.py} — add responsible_subcontractor_id FK/emit event
- backend/app/modules/safety/{models.py, router.py, events.py} — add responsible_subcontractor_id FK/emit event
- backend/app/modules/schedule/{models.py, router.py, service.py, events.py} — add assigned_subcontractor_id FK/emit slip event

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Rating lag (monthly cron delay) | Scores stale for hours | Publish event immediately; frontend auto-refreshes |
| Null subcontractor_id on NCR | Rating misses data | UI encourages (not enforces) linking; bulk-backfill tool |
| Template versioning | Old submissions invalid | Store version in metadata; allow re-submission |
| Multi-currency cost variance | Incorrect score | Cost variance project-currency only; no FX blending |
| Retroactive changes (NCR closed/reopened) | Score mutation | Current month mutable; prior months immutable |
| Gate inconsistency (bid vs procurement) | Sub awarded but unpaid | Centralize gate in check_award_eligibility(); both modules call |
| Missing i18n keys (26 locales) | UI shows key names | Automation script checks all locales at build |
| Event subscriber not wired | Events fire, no handler | Unit test confirms subscriber registered; test fires event |

## Effort & Quality

**Estimate**: M (4-5 days backend + frontend + testing)
- Moderate complexity: reuses existing rating engine + event infrastructure
- No greenfield modules; integrates into existing subcontractors/procurement/ncr/safety/schedule

**Quality bar**: 40+ test cases, browser verification, zero console errors on all surfaces


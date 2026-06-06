# Item 22 - Subcontractor Portal Invoice Submission

## Current State (Verified Against Code)

The portal module (ackend/app/modules/portal/) exists with:
- **Models**: PortalUser, PortalAccessRule, PortalSession, PortalMagicLink, PortalNotification, PortalDocumentAccessLog — all tables present, no schema changes needed.
- **Service**: PortalService handles auth (magic-link login), notifications, access-rule enforcement (RLS), and document audit logging. No payment-application specific methods exist yet.
- **Router**: Internal-admin endpoints (user invite, access grants, audit log) and portal-user-facing endpoints (/me, /me/notifications, /me/accessible, /me/tickets, /me/change-orders) all implemented. **Payment-application endpoints are NOT present.**
- **Frontend**: PortalPage.tsx is the internal-admin UI (manage users, access rules, audit log). No payment-application UI components exist.

The subcontractors module (ackend/app/modules/subcontractors/) already has:
- **Models**: PaymentApplication, PaymentApplicationLine, WorkPackage, Agreement, Subcontractor — all tables present.
- **Service**: Full CRUD for payment applications (create, list, get, update, approve, reject) with foreman and finance approval workflows.
- **Router**: Internal endpoints /payment-applications/ (create, list, get, patch, approve, reject) exist; these are NOT portal-facing (they require internal user session).

**Gap**: Portal-facing subcontractor endpoints to submit/view payment applications do not exist. The digest item remains **partial** — only the internal workflows are implemented.

---

## Scope of This Increment (Demonstrable & Testable)

A **bounded, single-increment** portal-payment feature:

1. **Backend**: Add portal-facing read/submit endpoints for payment applications scoped to the subcontractor's accessible agreements (via PortalAccessRule).
2. **Frontend**: Build two mobile-responsive React components: a list showing outstanding/submitted applications, and a form to submit a new application with work-package line items.
3. **Migration**: None required (all tables exist; use existing metadata_ JSON column to store submission metadata if needed).
4. **Test**: Browser test with magic-link login → payment form submission → verification in admin UI.
5. **NOT in this increment**: Lien-waiver upload, payment-status notifications, cost-model integration, finance approval UI enhancements, or payroll integration. These are separate items or future scope.

### Key Design Principles
- **LIGHTWEIGHT**: Reuse existing models and schemas; store minimal new state.
- **RLS-enforced**: Portal subcontractor can only view/submit applications for agreements they have submit or iew permission on.
- **Mobile-first**: Single-column form layout, touch-friendly inputs, sticky submit button.
- **Deterministic**: No AI or manual steps in submission; portal user fills form, submits, foreman/finance approve via existing internal workflows.

---

## Backend Changes

### Endpoints (FastAPI, mounted at /api/v1/portal/me/payment-applications/)

`
GET  /me/payment-applications?agreement_id=...&status=...&offset=0&limit=50
  → PaymentApplicationListResponse (items: [], total: int)
  → RLS: subcontractor sees only applications for agreements they have access to

GET  /me/payment-applications/{id}
  → PaymentApplicationDetailResponse
  → RLS: subcontractor sees only if application belongs to accessible agreement

POST /me/payment-applications
  → Request: PaymentApplicationSubmitPayload (agreement_id, period_start, period_end, lines: [{work_package_id, claimed_amount}, ...])
  → Response: PaymentApplicationResponse (id, application_number, status=submitted)
  → RLS: subcontractor must have submit permission on agreement
  → Creates new PaymentApplication row with status=submitted, submitted_at=now()
`

### Files Touched

**backend/app/modules/portal/router.py**
- Add @router.get("/me/payment-applications", ...) → portal_me_payment_applications_list
- Add @router.get("/me/payment-applications/{id}", ...) → portal_me_payment_application_detail
- Add @router.post("/me/payment-applications", ...) → portal_me_payment_application_submit
- All three endpoints require RequirePortalSession auth.
- All enforce RLS via PortalService.enforce_rls(user.id, "payment_application", application_id) (for GET detail) or by filtering list to accessible agreement_ids.

**backend/app/modules/portal/service.py**
- Add list_payment_applications_for_user(user_id, agreement_id=None, status=None, offset, limit) -> (items, total) 
  - Query PaymentApplication rows where agreement_id is in the user's accessible agreement IDs.
  - Filter by status if provided.
  - Return paginated list.
- Add get_payment_application(id, user_id) -> PaymentApplication | None
  - Enforce RLS: verify user can access the payment_application's agreement.
  - Return row or None.
- Add submit_payment_application(user_id, agreement_id, period_start, period_end, lines) -> PaymentApplication
  - Verify user has submit permission on agreement.
  - Create PaymentApplication row (status=submitted, submitted_at=now()).
  - Create PaymentApplicationLine rows for each line item.
  - Emit event: payment_application.submitted (for future notification flow).
  - Return created application.

**backend/app/modules/portal/schemas.py**
- Add PaymentApplicationListItem: id, agreement_id, application_number, period_start, period_end, gross_amount, net_amount, status, submitted_at.
- Add PaymentApplicationListResponse: items: [], total: int.
- Add PaymentApplicationLineDetail: work_package_id, work_package_name, planned_value, claimed_amount, certified_amount (display), approved_amount (display).
- Add PaymentApplicationDetailResponse: id, agreement_id, application_number, period_start, period_end, gross_amount, retention_amount, net_amount, status, lines: [], submitted_at.
- Add PaymentApplicationSubmitPayload: agreement_id, period_start, period_end, lines: [{work_package_id: UUID, claimed_amount: Decimal}].

**backend/app/modules/portal/repository.py** (or reuse subcontractors.repository)
- Add list_payment_applications(session, filters) -> (items, total) helper for querying via agreement_id, status, pagination.
- (May reuse existing subcontractors repository if cross-module; see Conflicts below.)

**backend/app/modules/subcontractors/repository.py** (NO changes needed)
- PaymentApplication CRUD already exists; portal service will import and reuse if needed.

### Models (DDL)

**No new migrations required.** All tables exist:
- oe_subcontractors_payment_application (has agreement_id FK, status, submitted_at)
- oe_subcontractors_payment_application_line (has work_package_id FK, claimed_amount)
- oe_subcontractors_agreement (has all work packages)

**Optional**: Store submission metadata in the metadata_ JSON column (e.g., { "submitted_via_portal": true, "portal_user_id": "...", "submitted_ip": "..." }). This is purely informational and requires no schema change.

---

## Frontend Changes

### New Routes

- /portal/payments — Payment Application list and submission entry point (requires portal session)

### New Components

**frontend/src/features/portal/PaymentApplicationList.tsx**
- Displays paginated list of payment applications accessible to the logged-in subcontractor.
- Columns: Agreement name, Application #, Period, Gross Amount, Status, Actions.
- Status badges: submitted (blue), foreman_approved (yellow), finance_approved (green), paid (success), rejected (error).
- Row click → open detail modal or navigate to detail view.
- "Submit New" button → open submission form.
- Uses useQuery to fetch from portal API.
- Mobile: Single-column stacked cards instead of table.

**frontend/src/features/portal/PaymentApplicationForm.tsx**
- Form to create and submit a new payment application.
- Inputs:
  - Agreement selector (dropdown, pre-filtered to user's accessible agreements)
  - Period start/end date pickers
  - Work-package line-item grid: (work_package_name, planned_value [readonly], claimed_amount [editable], certified_amount [readonly], approved_amount [readonly])
  - Retention calculator: auto-computes retention % as user types claimed amounts
  - Gross/Net summary (read-only, auto-calculated)
  - Submit button → POST to portal API
  - Success toast + redirect to list
- Mobile: Single-column, touch-friendly number inputs, collapse/expand work-package sections.

### File Changes

**frontend/src/features/portal/api.ts**
- Add listPaymentApplications(params?: { agreement_id?: UUID; status?: string; offset?: number; limit?: number }): Promise<PaymentApplicationListResponse>
- Add getPaymentApplication(id: UUID): Promise<PaymentApplicationDetailResponse>
- Add submitPaymentApplication(data: PaymentApplicationSubmitPayload): Promise<PaymentApplicationResponse>
- Add TypeScript interfaces for all response schemas.

**frontend/src/features/portal/PortalPage.tsx**
- Add /portal/payments sub-route; dispatch to PaymentApplicationList + PaymentApplicationForm components.

**frontend/src/app/App.tsx**
- Ensure route <Route path="/portal/payments" element={...} /> is registered.

**frontend/src/app/locales/en.ts** (and all 26 other locale files)
- Add i18n keys for payment-application UI (title, form labels, status badges, messages).
- Translations auto-populated by i18n-sweep skill.

---

## Migration

**DDL**: None required.

**Data**: None required.

---

## File Touch List

### Backend
1. ackend/app/modules/portal/router.py — Add 3 endpoints
2. ackend/app/modules/portal/service.py — Add 3 methods
3. ackend/app/modules/portal/schemas.py — Add 5 schemas
4. ackend/app/modules/portal/repository.py — Add 1 helper (optional)
5. ackend/tests/modules/portal/test_payment_applications.py — NEW file

### Frontend
1. rontend/src/features/portal/PaymentApplicationList.tsx — NEW component
2. rontend/src/features/portal/PaymentApplicationForm.tsx — NEW component
3. rontend/src/features/portal/api.ts — Add 3 functions + 5 interfaces
4. rontend/src/features/portal/PortalPage.tsx — Add payment route
5. rontend/src/app/App.tsx — Register /portal/payments route
6. rontend/src/app/locales/en.ts — Add i18n keys
7. rontend/src/app/locales/*.ts (25 other locales) — Translations via i18n-sweep

---

## Conflicts / Sequencing

### Shared Modules
- ackend/app/modules/portal/router.py — Shared by all portal features. Low conflict risk.
- ackend/app/modules/portal/service.py — Shared core logic. Medium risk if RLS differs. Design uses standard enforce_rls pattern.
- rontend/src/features/portal/api.ts — Shared API layer. Low conflict risk.

### Wave 4 Items
- **Finance module** — No conflict; this increment does NOT post to GL.
- **Payroll module** — No conflict; this increment does NOT create payroll entries.
- **Documents module** — No conflict; separate data flow.

**Sequencing**: Implement independently. Future increments can integrate with finance/payroll.

---

## Test Plan

### Browser Test (Mobile 375px, Chrome DevTools)

1. **Login**: Magic-link flow → portal session
2. **List Applications**: GET list loads with seeded applications
3. **View Detail**: Click row, modal shows application details
4. **Submit New**: Fill form, submit, verify 201 response, application appears in list
5. **RLS**: Verify subcontractor cannot see inaccessible agreements' applications
6. **Desktop**: Verify layout expands to two-pane on desktop view
7. **Responsive**: Screenshot mobile list/form and desktop layout

### Unit Tests (backend/tests/modules/portal/test_payment_applications.py)

- 	est_list_empty() — Empty list when no applications
- 	est_list_filters_by_access_rule() — RLS filtering works
- 	est_submit_creates_application_and_lines() — Creates PaymentApplication + lines
- 	est_submit_enforces_rls() — 403 on inaccessible agreement
- 	est_get_detail_enforces_rls() — None returned for inaccessible app
- 	est_get_list_endpoint() — API endpoint 200 response
- 	est_post_submit_endpoint() — API endpoint 201 response

---

## Risks

1. **RLS Implementation**: Incorrect access control could expose other subcontractors' applications. **Mitigation**: Enforce RLS at every endpoint; unit tests verify denial; integration tests with multi-user seeded data.

2. **Concurrency**: Race conditions in application_number sequencing. **Mitigation**: Database constraints; transactional inserts.

3. **Calculation Precision**: Frontend/backend amount mismatch due to decimal handling. **Mitigation**: Backend recalculates on POST; frontend is display-only.

4. **Mobile UX**: Number/date inputs may not work reliably on older devices. **Mitigation**: HTML5 native pickers with fallback; test on iOS/Android.

5. **Translation**: Missing i18n keys in some locales. **Mitigation**: Use i18n-sweep skill to auto-translate.

6. **Scope Creep**: Users expect lien waivers, notifications, cost integration. **Mitigation**: Clearly documented "NOT in this increment" section.

---

## Summary

This increment delivers **subcontractor portal payment-application submission**: login via magic link, view applications, submit new applications with work-package line items. All endpoints enforce RLS. No database migrations required. Mobile-responsive frontend with auto-calculated amounts and 26-locale support. Independent of Wave 4; future increments can layer on lien waivers and finance integration.

**Effort**: **L** (light) — 3-4 days full-stack pair work.
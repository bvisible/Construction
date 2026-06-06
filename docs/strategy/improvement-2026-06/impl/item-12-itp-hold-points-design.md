# Item 12 - Inspection and Test Plan (ITP) workflow with hold points and quality gates

## Current state (verified against code)

**Backend (backend/app/modules/qms/):**
- `ITPPlan` (oe_qms_itp_plan) — header with project_id, name, work_type, wbs_ref, status (draft/active/archived), version
- `ITPItem` (oe_qms_itp_item) — control point with sequence, control_point_name, criteria, frequency, method, acceptance_criteria, `hold_witness_point` (enum: hold/witness/review), responsible_role, signatories_required
- `QMSInspection` (oe_qms_inspection) — scheduled/performed inspection with itp_item_id FK, status (scheduled/in_progress/passed/failed), notes, `photos_json` (sparse array, not files)
- `QMSInspectionSignature` (oe_qms_inspection_signature) — multi-signature per inspection with signer_user_id, signer_role, signed_at, signature_method (electronic), comments
- `QMSAuditLog` (oe_qms_audit_log) — append-only FSM audit trail (added May 2026) with entity_type/entity_id/action/actor_user_id/old_status/new_status
- `Document` module exists (documents/) with file versioning, but no direct FK from QMS to documents yet

**Frontend (frontend/src/features/qms/):**
- `QMSPage.tsx` — unified page with ITP plans, inspections, NCRs, punch items, audits tabs
- Routes: `/qms` (main page)
- Current ITP UI: list plans, list items, create plan, add item; inspection scheduling, signature collection; basic notes
- No: spec linkage visualization, attachments UI, hold-point dependency tree, responsible-role gating, compliance export

**Gaps per digest (remaining items 1-10):**
1. ✗ No FK from ITPItem to BOQ positions, drawing specs, BIM requirements
2. ✗ photos_json is sparse/orphaned; need proper document attachment with hash/audit trail
3. ✗ Inspection results don't gate downstream workflows (tasks, cost commits, approvals)
4. ✗ No integration with approval_routes for inspection-triggered approvals
5. ✗ No predecessor_itp_item_id sequencing (hold-point dependencies)
6. ✗ No signer role validation against actual project roles
7. ✗ No compliance-export endpoint (PDF/XML with audit trail, signatures)
8. ✗ No qms.inspection.hold_point_failed event publishing to punchlist/NCR/notifications
9. ✗ No signature non-repudiation (timestamp_utc, signer_ip, signer_user_agent, signature_token)
10. ✗ No hold-point release/unlock workflow with event publishing

---

## Scope of this increment (demonstrable + testable)

**Goal:** Implement a **bounded, browser-testable MVP** of ITP hold-point workflow that covers the critical path for real-world QA:
1. **Spec linkage** — link ITPItem to BOQ line (via boq_position_id), drawing reference, BIM element
2. **Evidence permanence** — replace photos_json with file attachments via documents module (with hash verification)
3. **Hold-point sequencing** — add predecessor_itp_item_id FK, enforce predecessor passed before scheduling dependent inspection
4. **Responsible-role validation** — gate signature collection to users matching signer_role (or higher authority)
5. **Basic event publishing** — emit qms.inspection.hold_point_failed/passed for downstream subscribers (punchlist, notifications)
6. **Hold-point release** — add POST /inspections/{id}/release endpoint with role-based auth, event publishing, audit trail

**Out of scope (Phase 2):**
- Full compliance-export PDF/XML with FIDIC/ISO 19650 formatting
- Signature non-repudiation (digital signing, JWT tokens, IP/user-agent capture) — handled in later security phase
- Automated approval-route integration (inspection-triggered approvals) — deferred pending approval_routes maturation
- Batch hold-point release management UI

**Why this scope?**
- **Demonstrable:** Hold a real inspection at a control point, verify predecessor block, sign it, release it, see event in logs
- **Testable:** E2E browser test covers spec link, attachment upload, sequencing guard, signature, release
- **Unblocks:** downstream modules (punchlist, notifications) can subscribe to hold_point_failed/passed events
- **Realistic:** aligns with site QA practice (hold point → inspect → pass/fail → sign → release → proceed)

---

## Backend changes (files, functions, endpoints, models/DDL)

### Models (backend/app/modules/qms/models.py)

**ITPItem — add spec linkage + predecessor dependency:**

- boq_position_id: Mapped[uuid.UUID | None] — FK to BOQ position
- csi_section_ref: Mapped[str | None] — CSI section reference
- drawing_ref: Mapped[str | None] — Drawing reference
- bim_element_id: Mapped[str | None] — BIM element identifier
- predecessor_itp_item_id: Mapped[uuid.UUID | None] — self-referential FK for hold-point sequencing

**QMSInspection — replace photos_json with attachment FK:**

- attachment_document_ids: Mapped[list[str]] — JSON array of document IDs from documents module

**QMSInspectionSignature — add non-repudiation fields:**

- timestamp_utc: Mapped[str | None] — ISO 8601 UTC timestamp
- signer_ip: Mapped[str | None] — Signer IP address
- signer_user_agent: Mapped[str | None] — Signer browser user-agent
- signature_token: Mapped[str | None] — Optional JWT or HMAC token (Phase 2)

**NEW: QMSInspectionAttachment:**

- inspection_id: FK to QMSInspection
- document_id: Soft FK to documents.Document
- caption: Optional metadata
- file_hash_sha256: SHA256 hash for verification
- uploaded_by, attached_at: Audit trail

**NEW: QMSHoldPointRelease:**

- inspection_id: Unique FK to QMSInspection
- released_by, released_at: Who released it and when
- justification: Why released
- approval_route_id: Optional approval reference

### DDL (Alembic migration)

File: `backend/alembic/versions/v3XXX_itp_hold_points_sequence_attachments.py`

Key changes:
- ALTER TABLE oe_qms_itp_item ADD (boq_position_id, csi_section_ref, drawing_ref, bim_element_id, predecessor_itp_item_id)
- ALTER TABLE oe_qms_inspection ADD attachment_document_ids TEXT
- ALTER TABLE oe_qms_inspection_signature ADD (timestamp_utc, signer_ip, signer_user_agent, signature_token)
- CREATE TABLE oe_qms_inspection_attachment (6 columns, 2 indexes)
- CREATE TABLE oe_qms_hold_point_release (6 columns, 1 index)

All columns have server_default values for backward compat.

### Service layer (backend/app/modules/qms/service.py)

**New functions:**

- `link_itp_item_to_spec(itp_item_id, boq_position_id, csi_section_ref, drawing_ref, bim_element_id)` — link ITPItem to spec sources
- `add_inspection_attachment(inspection_id, document_id, caption, file_hash_sha256, uploaded_by_user_id)` — link document to inspection
- `check_hold_point_predecessor_status(itp_item_id)` — check if predecessor inspection passed
- `schedule_inspection_with_predecessor_guard(itp_item_id, scheduled_at, ...)` — schedule, blocking if predecessor not passed
- `validate_signer_role(inspection_id, user_id, user_project_roles)` — gate signature collection by role
- `sign_inspection_with_non_repudiation(inspection_id, signer_user_id, signer_role, signer_ip, signer_user_agent, comments)` — sign with audit fields
- `release_hold_point(inspection_id, released_by_user_id, justification)` — release hold, emit event
- `complete_inspection_and_publish_hold_event(inspection_id, result)` — complete + emit qms.inspection.hold_point_failed/passed

### Router (backend/app/modules/qms/router.py)

**New endpoints:**

- `POST /inspections/{inspection_id}/attach-evidence` — link document to inspection (201)
- `GET /inspections/{inspection_id}/hold-point-status` — check predecessor status
- `POST /inspections/{inspection_id}/release` — release hold point (201, requires qms:inspections:release_hold)
- `POST /inspections/{itp_item_id}/schedule-with-guard` — schedule with predecessor guard (201 or 409)

### Repository (backend/app/modules/qms/repository.py)

- `create_inspection_attachment(attachment)` — persist attachment
- `list_inspection_attachments(inspection_id)` — fetch all attachments for inspection
- `create_hold_point_release(release)` — persist release
- `get_hold_point_release(inspection_id)` — fetch release record

### Schemas (backend/app/modules/qms/schemas.py)

- `ITPItemLinkSpec` — spec linkage input
- `QMSInspectionAttachmentRead` — attachment output
- `QMSHoldPointReleaseRead` — release output
- `QMSInspectionSignatureEnhancedRead` — signature with non-repudiation fields

### Events (backend/app/modules/qms/events.py)

- Emit `qms.inspection.hold_point_failed` when inspection fails
- Emit `qms.inspection.hold_point_passed` when inspection passes
- Emit `qms.inspection.hold_point_released` when hold is released
- Register subscriber stub for Phase 2 (punchlist integration)

---

## Frontend changes (route, components, UX)

### Routes

- `/qms/inspections/{inspection_id}` — Inspection detail page (new)
- `/qms/itp-plans/{plan_id}/items` — ITP plan editor (enhanced with dependency UI)

### New Components

- `InspectionDetailPage.tsx` — inspection view with spec linkage, attachments, predecessor status, signature form, release button
- `HoldPointDependencyTree.tsx` — dependency visualization (tree or swimlane)
- `AttachmentEvidenceGallery.tsx` — attachment preview, upload, hash verification
- Enhanced `ITPItemForm.tsx` — spec linkage fields, predecessor selector
- Enhanced `QMSPage.tsx` — Hold Point Sequencing tab

### API Functions (frontend/src/features/qms/api.ts)

- `linkITPItemToSpec(planId, itemId, linkage)` — PATCH item with spec
- `attachInspectionEvidence(inspectionId, documentId, caption)` — POST attachment
- `listInspectionAttachments(inspectionId)` — GET attachments
- `checkHoldPointPredecessor(inspectionId)` — GET predecessor status
- `scheduleInspectionWithGuard(itemId, inspection)` — POST schedule with guard (409 on block)
- `releaseHoldPoint(inspectionId, justification)` — POST release

### UX Principles

- **Simplicity:** 🔴 blocked, 🟡 pending, 🟢 passed (hold-point traffic light)
- **Clarity:** Inline blocking reason (e.g. "Blocked: Predecessor not passed")
- **Speed:** One-click sign + one-click release (if authorized)
- **Audit:** "Signed by [name] at [ISO timestamp] from [IP]" in muted text
- **Mobile:** Signature via biometric/PIN (Phase 2)

---

## Migration (DDL or "none")

**Required:** Yes, single Alembic migration adding columns and 2 new tables.

**Idempotent:** Yes — all ALTER TABLE statements have IF NOT EXISTS, server_default on every column.

**Downtime:** None — PostgreSQL handles online DDL.

**Rollback:** Forward-only (can drop columns if needed, but tables persist for audit trail).

---

## File touch list

**Backend (9 files):**
1. backend/app/modules/qms/models.py — add 4 models/columns
2. backend/app/modules/qms/service.py — add 8 functions
3. backend/app/modules/qms/router.py — add 4 endpoints
4. backend/app/modules/qms/repository.py — add 4 methods
5. backend/app/modules/qms/schemas.py — add 4 schemas
6. backend/app/modules/qms/events.py — add event publishing + subscriber
7. backend/alembic/versions/v3XXX_itp_hold_points_sequence_attachments.py — new migration
8. (implicit) backend/app/modules/qms/permissions.py — may add qms:inspections:release_hold permission
9. (implicit) backend/app/core/exceptions.py — add BlockedByPredecessor, InvalidInspectionStatus, InvalidControlPointType

**Frontend (7 files):**
1. frontend/src/features/qms/QMSPage.tsx — enhance with Hold Point Sequencing tab
2. frontend/src/features/qms/InspectionDetailPage.tsx — new component
3. frontend/src/features/qms/HoldPointDependencyTree.tsx — new component
4. frontend/src/features/qms/AttachmentEvidenceGallery.tsx — new component
5. frontend/src/features/qms/ITPItemForm.tsx — enhance with spec + predecessor fields
6. frontend/src/features/qms/api.ts — add 6 functions
7. (implicit) frontend/src/features/qms/index.ts — export new components

**Total: 16 files touched**

---

## Conflicts / sequencing

**Wave 4 modules (concurrent, no shared files):**
- Item #2 (Payroll) — fieldreports, field_diary, costmodel, finance, payroll
- Item #3 (Live EVM) — reporting, bi_dashboards, costmodel, schedule, risk, safety, finance
- Item #4 (ERP connectors) — finance
- Item #5 (Portfolio capacity) — schedule_advanced, resources
- Item #6 (Schedule dependencies) — schedule
- Item #7 (AI photos) — documents (soft FK only), ai
- Item #9 (Lien waiver) — subcontractors, finance, approval_routes
- Item #10 (Commitment) — procurement, costmodel, finance
- Item #11 (Tendering) — procurement, bid_management

**No conflicts identified.** Item #12 is fully isolated to QMS module.

**Sequencing recommendation:**
1. Ship item #12 first (foundational hold-point workflow)
2. Ship item #1 extensions (punchlist subscribes to qms.inspection.hold_point_failed)
3. Wave 4 items in parallel (independent)

---

## Test plan (browser + unit)

**Unit tests:** Predecessor check, role validation, attachment CRUD, hold-point release, event emission

**E2E browser test:** Schedule → Block → Sign (role-gated) → Complete → Release → Unblock

**API contract tests:** 409 status codes when blocked, event publishing verified

**Pass criteria:**
- Predecessor blocks scheduling (409)
- Signature gated by role (button disabled if insufficient)
- Attachment hash verified (green badge)
- Release creates record + emits event
- Dependency tree shows correct status (passed/blocked)

---

## Risks

1. **Predecessor lookup performance** — mitigated by database view + caching on plan activation
2. **Document attachment orphaning** — mitigated by Phase 2 cascade delete or soft-delete flag
3. **Signature non-repudiation incomplete** — Phase 2 implements digital signature (JWT/HMAC)
4. **Role hierarchy hardcoded** — defer to app.core.permissions (Phase 2)
5. **Event subscriber no-op** — clear Phase 2 acceptance criteria; infrastructure-only this phase
6. **Hold-point release authorization** — add IDOR guard + project role check
7. **Attachment upload size cap** — pull documents module max_upload_size, show frontend error

---

## Summary

Item #12 scopes ITP hold-point workflow into a bounded, testable, demonstrable increment:
- **7 new endpoints, 1 new table, 3 table columns**
- **4 service functions, 3 React components**
- **1 Alembic migration (online DDL)**
- **Unblocks Phase 2 punchlist/notification subscribers**

**Effort: M (40-50 hours)** — straightforward CRUD + FSM guard, moderate UI for dependency tree visualization.


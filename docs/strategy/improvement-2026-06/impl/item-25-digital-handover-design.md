# Item 25 - Digital Handover and Closeout Package Assembly

## Current State (Verified Against Code)

The property_dev module backend has complete handover and handover document infrastructure:
- Handover ORM model with all required fields (scheduled_at, completed_at, keys_handed_over_at, customer_signature_ref, snag_count_at_handover, final_check_passed)
- HandoverDoc ORM model (oe_property_dev_handover_doc table) with doc_type, title, file_url, is_required, is_delivered, delivered_at, metadata
- All CRUD service methods: create/get/update/delete for both handovers and handover docs
- handover_bundle() service method returns aggregated response with docs list + delivered_count + required_count + missing_required + ready_for_handover
- Full router endpoints (GET /handovers/, POST /handovers/, GET /handovers/{h_id}, PATCH /handovers/{h_id}, DELETE /handovers/{h_id}, POST /handovers/{h_id}/complete, GET /handovers/{h_id}/docs, POST /handover-docs/, PATCH /handover-docs/{doc_id}, DELETE /handover-docs/{doc_id})
- Frontend HandoversTab and HandoverPlotRow components render handover list with certificate generation buttons
- SnagsBlock component renders below handovers

**Missing:**
1. Frontend API layer (TypeScript interfaces/functions for HandoverDoc and HandoverBundle)
2. Frontend UI component to display and manage handover documents (HandoverDocumentsSection)
3. Backend export endpoint (GET /handovers/{h_id}/export) to create ZIP with all delivered docs + certificates
4. Validation on complete_handover() to check ready_for_handover flag
5. Localization for handover doc type labels and UI strings

## Scope of This Increment

Build bounded, end-to-end handover document management:

**Backend:**
- Add export_handover_package() service method to generate ZIP with: docs/, certificates/, snags/ folders
- Add GET /handovers/{h_id}/export endpoint returning StreamingResponse with ZIP
- Modify complete_handover() to validate ready_for_handover before completion (409 if missing)

**Frontend:**
- Add HandoverDocResponse and HandoverBundleResponse TypeScript interfaces to api.ts
- Add getHandoverBundle(), createHandoverDoc(), updateHandoverDoc(), deleteHandoverDoc(), exportHandoverPackage() functions
- Create HandoverDocumentsSection component: Card with doc list, status badge, add/edit/delete modals, export button
- Mount HandoverDocumentsSection in HandoverPlotRow after certificate buttons, before SnagsBlock
- Add i18n keys for handover doc types and UI strings

## Backend Changes

### Files to modify:

**backend/app/modules/property_dev/service.py**
- Add method: `export_handover_package(handover_id: UUID) -> bytes`
  - Fetch handover + all delivered docs
  - Render handover_certificate.pdf, warranty_certificate.pdf via document_templates
  - Collect snag photos from linked snags
  - Create ZIP: handover_{plot_number}_{iso_date}.zip with docs/, certificates/, snags/ folders
  - Return ZIP bytes

- Modify: `complete_handover(h_id: UUID, data: HandoverCompleteRequest) -> Handover`
  - Before state change, call `bundle = await self.handover_bundle(h_id)`
  - If `bundle['ready_for_handover'] == False`, raise HTTPException(409, detail={"missing_required": bundle['missing_required']})
  - Else proceed with existing logic

**backend/app/modules/property_dev/router.py**
- Add endpoint: `GET /handovers/{h_id}/export`
  - Permission: property_dev.read
  - Response: StreamingResponse with application/zip MIME type
  - Filename header: handover_{plot_number}_{iso_date}.zip
  - Calls service.export_handover_package()

## Frontend Changes

### Files to modify/create:

**frontend/src/features/property-dev/api.ts**
- Add interfaces: HandoverDocResponse, HandoverBundleResponse
- Add functions: getHandoverBundle(), createHandoverDoc(), updateHandoverDoc(), deleteHandoverDoc(), exportHandoverPackage()

**frontend/src/features/property-dev/HandoverDocumentsSection.tsx** (NEW)
- Component displays HandoverBundleResponse with doc list, status badge, action buttons
- Fetch bundle on mount, render table (Document Type | Title | Status | Actions)
- Delivery status as checkbox + timestamp
- Add Document modal (doc_type dropdown, title input, file_url, is_required)
- Export Package button (primary when ready_for_handover=true)

**frontend/src/features/property-dev/PropertyDevPage.tsx**
- Import HandoverDocumentsSection
- Mount in HandoverPlotRow after certificate buttons (line ~4318), before SnagsBlock

**frontend/src/app/locales/en.ts and 25 other locales**
- Add i18n keys for doc types: propdev.doc_type.warranty, .manual, .key_receipt, .hs_file, .epc, .nhbc, .inspection_cert, .certificate_completion, .insurance, .other
- Add UI keys: propdev.handover_package, .handover_package.ready, .missing_docs, .delivered_count, .add_document, .export_package

## Migration

**None** - HandoverDoc table already exists with all required columns.

## File Touch List

Backend:
- backend/app/modules/property_dev/service.py
- backend/app/modules/property_dev/router.py

Frontend:
- frontend/src/features/property-dev/api.ts
- frontend/src/features/property-dev/HandoverDocumentsSection.tsx (NEW)
- frontend/src/features/property-dev/PropertyDevPage.tsx
- frontend/src/app/locales/en.ts (and 25 other locales)

## Conflicts / Sequencing

**No conflicts.** Item 25 is property_dev-only, does not touch Wave 4 modules (bim_hub, equipment, documents, ai, fieldreports, field_diary, costmodel, finance, payroll). Independent scheduling.

## Test Plan

**Browser Tests:**
1. Handover Package section displays below certificate buttons
2. Add document (select doc_type, enter title, toggle is_required)
3. Mark document delivered (checkbox updates status, timestamp)
4. All required docs delivered → badge "Ready" (green), Export button primary
5. Export Package → downloads ZIP with docs/, certificates/, snags/ structure
6. Validation on mark completed: if required docs missing, show error with missing list
7. Edit/delete documents in modals
8. All UI strings localized in de/fr/es/ja (no raw i18n keys)

**Unit Tests:**
- export_handover_package() creates valid ZIP
- complete_handover() blocks with 409 if ready_for_handover=false
- HandoverDocumentsSection renders and handles add/edit/delete/export

**Screenshots Required:**
- Handover Package card with doc table
- Status badge (Ready or Missing)
- At least one delivered doc (checked + timestamp)
- Missing docs warning (if applicable)
- Export button visible
- All strings localized

## Risks

1. File URL handling: validate/download external URLs, skip broken links, stream large files
2. Certificate rendering: pre-validate required fields, provide defaults for missing data
3. Performance: large exports with many docs + photos may timeout, use streaming/background job
4. Snag photo paths: validate for directory traversal, skip invalid paths
5. Buyer portal access: verify permission gates work for portal tokens
6. Localization: auto-translate 26 locales via i18n-sweep, validate in 3+ languages
7. Backward compatibility: old handovers without docs are OK (empty docs list), no migration
8. Data integrity: deletion is final, no soft-delete audit trail (can add later)

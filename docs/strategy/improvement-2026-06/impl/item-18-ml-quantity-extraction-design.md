# Item 18 - ML quantity extraction / symbol recognition

## Current state (verified against code)

### What exists:
- **Backend ImageSourceAdapter** (`backend/app/modules/match_elements/sources/image_adapter.py`): Fully implemented. Accepts photo/drawing via `MatchSession.metadata_["image"]`, calls Claude/GPT-4V vision API, parses structured JSON of visible elements (name, ifc_class_guess, qty_estimate, unit_estimate, material, confidence).
- **EXIF GPS extractor** (`backend/app/core/match_service/extractors/photo.py`): Fully implemented. Hand-parses JPEG APP1 / TIFF EXIF blocks to extract geotags (lat/lon) without Pillow.
- **Takeoff service** (`backend/app/modules/takeoff/service.py`): Has `extract_tables()` method using pdfplumber to extract table cells. No symbol detection; only reads table headers + rows.
- **TakeoffDocument model** (`backend/app/modules/takeoff/models.py`): Has `page_data` (JSON list of per-page tables), `analysis` (JSON for AI results), `metadata_` for extensibility.

### What is MISSING:
1. **Frontend image upload UI**: MatchWizard.tsx has tabs for BIM/Excel/PDF/Text, but NO "Photo/Drawing" tab.
2. **YOLO symbol detector**: `services/cv-pipeline/` directory is empty. No symbol detection service exists.
3. **Dimension OCR**: takeoff.extract_tables() uses only pdfplumber table detection (no symbol bounds, no dimension text extraction).
4. **Symbol→rate matching**: No logic to auto-suggest rate codes based on detected symbol type + dimensions.
5. **UI overlays**: No bounding boxes, confidence badges, or dimension annotations on photo/PDF preview.

---

## Scope of this increment (demonstrable + testable)

**Goal**: Ship ONE bounded slice that is immediately useful and testable end-to-end.

### What this increment DELIVERS:

1. **Frontend image tab** in MatchWizard (step 2)
   - New UI tab "Photo/Drawing" (drag-drop file picker, PNG/JPG/WebP)
   - Preview pane showing uploaded image
   - Calls existing backend `/sessions` endpoint with `source="image"`
   
2. **API image endpoint** (backend-only, minimal)
   - New `POST /sessions/from-image` multipart endpoint
   - Wire image to ImageSourceAdapter via metadata
   - Return session with extracted elements (via existing LLM call)

3. **Element grouping visualization**
   - Show extracted elements in the existing grouping panel (step 4)
   - Display quantity/unit from LLM (qty_estimate, unit_estimate) as metadata
   - NO symbol detection needed yet; pure vision-LLM only

4. **Browser test proof**
   - Upload a site photo → AI extracts elements + estimates quantities
   - Group by ifc_class → see results in chip-bar + table
   - NO BOQ auto-population in this slice

### What this increment DOES NOT include:
- Symbol detection (YOLO)
- Dimension OCR via PaddleOCR
- Auto-rate matching
- PDF symbol overlays
- Batch image upload

---

## Backend changes (files, functions, endpoints, models/DDL)

### Files touched:
1. `backend/app/modules/match_elements/router.py` — NEW `POST /sessions/from-image` endpoint
2. `backend/app/modules/match_elements/schemas.py` — ensure ImageDict export
3. `backend/app/modules/match_elements/service.py` — no changes (create_session already handles image at line 1451)

### New endpoint:

```
POST /api/v1/match-elements/sessions/from-image
Content-Type: multipart/form-data

Fields:
  - project_id: UUID
  - image: File (PNG/JPG/WebP, max 10MB)
  - name: str (optional)
  - group_by: list[str] (optional)
  - filters: dict (optional)
  - excluded_categories: list[str] (optional)
  - construction_stage: str (optional)
  - catalogue_id: str (optional)
  - auto_confirm_threshold: float (optional)
  
Response: 201
  SessionRead (same as POST /sessions, but source="image")
```

**Implementation**: Similar to `create_session_from_excel()` at router.py:109
- Save uploaded file to temp location
- Call existing `service.create_session()` with `spec.source="image"` + image dict
- Return session JSON

### No DDL needed

The image dict lives in `MatchSession.metadata_` (JSON column), already exists.

---

## Frontend changes (route, components, UX)

### Files touched:
1. `frontend/src/features/match-elements/MatchWizard.tsx` — add "Photo/Drawing" tab
2. `frontend/src/features/match-elements/api.ts` — add `createSessionFromImage()` function
3. `frontend/src/features/match-elements/components/ImageSourceSelector.tsx` (NEW file)
4. `frontend/src/app/locales/en.ts` (and other locales) — add i18n keys

### Route:
- No new route; existing `/match-elements` is the page
- Step 2 (source selection) adds new image tab

### Integration into MatchWizard.tsx:

1. Add image tab to tabs array: `{ id: 'image', icon: Image, label: 'Photo/Drawing' }`
2. Extend tab state type: `'bim' | 'excel' | 'pdf' | 'text' | 'image'`
3. Add image selection type: `| { kind: 'image'; file: File }`
4. Render image tab with ImageSourceSelector component

### New component: ImageSourceSelector.tsx

- Drag-drop zone with file input picker
- Accept PNG/JPG/WebP only
- Show preview thumbnail + filename
- Drag-over visual feedback
- Max file size: 10MB (client + server validated)
- Clear button to deselect

### API function: createSessionFromImage()

```typescript
export async function createSessionFromImage(
  projectId: string,
  file: File,
  options?: {
    name?: string;
    groupBy?: string[];
    filters?: Record<string, string[]>;
    excludedCategories?: string[];
    constructionStage?: string;
    catalogueId?: string;
    autoConfirmThreshold?: number;
  }
): Promise<SessionRead>
```

Sends FormData to POST `/sessions/from-image`

---

## Migration (DDL or "none")

**None.** Image dict stored in existing `MatchSession.metadata_` JSON column.

---

## File touch list

### Backend (3 files):
- `backend/app/modules/match_elements/router.py`
- `backend/app/modules/match_elements/schemas.py`
- `backend/app/modules/match_elements/service.py` (no actual changes, already handles image)

### Frontend (4 files):
- `frontend/src/features/match-elements/MatchWizard.tsx`
- `frontend/src/features/match-elements/api.ts`
- `frontend/src/features/match-elements/components/ImageSourceSelector.tsx` (NEW)
- `frontend/src/app/locales/en.ts` (and other locale files)

**Total: 7 files**

---

## Conflicts / sequencing

### No conflicts with Wave 4 items:
- **bim_hub**: Operates on BIM models (IFC), independent
- **equipment**: Resource management, independent
- **documents**: Photo storage (different use), independent
- **ai**: Already used by ImageSourceAdapter, no new dependency
- **fieldreports / field_diary**: Different modules, independent
- **costmodel / finance / payroll**: Cost domain, independent

### Internal sequencing:
1. **This increment**: Image tab + LLM extraction (M effort)
2. **Later increment**: YOLO symbol detector + OCR + auto-rate matching (XL)
3. **Later increment**: Takeoff PDF symbol overlays + batch upload (L)

---

## Test plan (browser + unit)

### Manual browser test:

1. Navigate to `/match-elements`
2. Step 1: Select a project
3. Step 2: Click "Photo/Drawing" tab (new)
4. Drag-drop or file-pick a JPG/PNG file
5. File validation passes, thumbnail appears
6. Click "Next" → POST `/sessions/from-image` endpoint
7. Step 4: Grouping panel shows extracted IFC classes in chip-bar
8. Table rows show qty_estimate + unit_estimate from LLM
9. Step 5: Click "Run Match" → system searches catalogue
10. See match results (same as other sources)
11. **Proof**: Image tab visible, thumbnail shown, grouping panel populated, zero console errors

### Unit tests:

```python
# Backend - router.py
test_create_session_from_image__success():
    # POST /sessions/from-image with multipart file
    # Verify SessionRead returned with source="image"
    # Verify image dict in metadata_

test_create_session_from_image__file_too_large():
    # File > 10MB → expect 413

test_create_session_from_image__invalid_mime():
    # .exe/.zip file → expect 400
```

```typescript
// Frontend - api.ts
test("createSessionFromImage sends multipart form-data", async () => {
    const file = new File(["dummy"], "test.jpg", { type: "image/jpeg" });
    await createSessionFromImage("project-id", file);
    // Verify POST /sessions/from-image, FormData with 'image' field
});

// Frontend - ImageSourceSelector.tsx
test("renders drag-drop zone");
test("accepts image files on drop");
test("rejects non-image files");
test("shows preview after file selection");
test("clears selection on clear button click");
```

### Assertions:
- Zero errors in DevTools > Console
- All POST/GET XHR calls return 200/201/4xx (no 5xx)
- No network timeouts
- Image tab renders and is clickable
- File upload succeeds and image dict persisted

---

## Risks

### Risk 1: Large image files cause memory issues
- **Mitigation**: Enforce 10MB max on client + server; use streaming if needed later

### Risk 2: LLM vision API not available or rate-limited
- **Mitigation**: Backend gracefully degrades to [] when API fails; UI shows "no elements extracted"

### Risk 3: Cross-browser drag-drop support
- **Mitigation**: Use standard HTML5 drag-drop API + fallback to file input picker

### Risk 4: Inconsistent element extraction across image quality
- **Mitigation**: LLM confidence always "low", user must review and confirm manually

### Risk 5: File upload endpoint name collision
- **Mitigation**: New endpoint `/sessions/from-image` is distinct from `/sessions` and `/sessions/{id}/`

---

## Effort estimate

- **Backend**: 1 day (endpoint + multipart handling, reuse existing service logic)
- **Frontend**: 1.5 days (component creation, tab integration, API function)
- **Testing**: 0.5 days (browser test, unit tests)
- **Polish**: 0.5 days (i18n, accessibility, mobile responsiveness)

**Total: M (4 days)**


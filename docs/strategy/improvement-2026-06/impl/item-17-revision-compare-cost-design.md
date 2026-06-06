# Item 17 - Auto drawing/BIM revision compare with cost delta

## Current state (verified against code)

**Backend modules:**
- `backend/app/modules/dwg_takeoff/` with DwgDrawing, DwgDrawingVersion, DwgAnnotation models
- `backend/app/modules/takeoff/` with TakeoffDocument, TakeoffMeasurement models
- `backend/app/modules/boq/` with _resolve_project_fx() and compareBoqs()
- Frontend: DwgTakeoffPage.tsx, BOQCompareDrawer.tsx pattern as reference
- Data precision: Numeric(18, 6) for measurements, BOQ uses Decimal

**Missing:**
1. No version comparison endpoint
2. No diff response schema
3. No DwgDrawingCompareDrawer.tsx component
4. No cost-impact calculation for annotation deltas

---

## Scope of this increment

**Bounded increment:** Revision comparison for DWG + PDF with cost impact when annotations linked to BOQ.

**What ships:**
1. Backend endpoint POST /dwg_takeoff/drawings/{id}/compare/{other_version_id}
2. Cost-impact calculation: (new_measurement - old_measurement) * unit_rate
3. Frontend drawer (Entities | Annotations | Summary tabs)
4. Compare button on drawing cards
5. Visual overlay mode (onion-skin opacity slider)
6. Unit tests for diff logic

**Not in scope:**
- Symbol detection (item #20)
- BIM element comparison
- Batch comparison
- Canvas highlighting

---

## Backend changes

### New schemas in dwg_takeoff/schemas.py:

```python
class DwgEntityDiffRow(BaseModel):
    change_type: Literal['added', 'removed', 'modified', 'unchanged']
    entity_id: str
    entity_type: str
    layer: str

class DwgAnnotationDiffRow(BaseModel):
    change_type: Literal['added', 'removed', 'modified', 'unchanged']
    annotation_id: str
    old_measurement: float | None = None
    new_measurement: float | None = None
    linked_boq_position_id: str | None = None
    cost_impact: str | None = None  # Decimal string

class DwgDrawingDiffResponse(BaseModel):
    entity_rows: list[DwgEntityDiffRow]
    annotation_rows: list[DwgAnnotationDiffRow]
    summary: dict[str, Any]
```

### New functions in dwg_takeoff/service.py:

- `list_drawing_versions(drawing_id, db)` 
- `compare_drawing_versions(drawing_id, v1_id, v2_id, project_id, db)`
- `_compute_entity_diff(v1_layers, v2_layers)`
- `_compute_annotation_delta(drawing_id, v1_id, v2_id, project_id, db)` — cost impact calculation
- `_calculate_cost_impact(delta, unit_rate, project_id, db)`

### New router endpoints in dwg_takeoff/router.py:

- `GET /drawings/{drawing_id}/versions/` — list versions
- `POST /drawings/{drawing_id}/compare/{other_version_id}` — compare and return diff

### Similar for takeoff module (PDF comparison)

### No DDL migration

All columns exist: version_number, measurement_value (Numeric 18,6), linked_boq_position_id

---

## Frontend changes

### New component: DwgDrawingCompareDrawer.tsx

Right-side panel (z-50) with:
- Version selector dropdown
- Three tabs: Entities, Annotations, Summary
- Each tab has table showing change type, old/new values
- Cost impact shown in green/red for linked annotations
- Toggle: Hide unchanged
- Toggle: Visual overlay (opacity slider)

### Integration into DwgTakeoffPage.tsx:

- Add Compare button (GitCompare icon) to drawing card
- Click opens DwgDrawingCompareDrawer
- Pass drawing_id, project_id, version info

### New in dwg_takeoff/api.ts:

- `fetchDrawingVersions(drawing_id, projectId)`
- `compareDrawings(drawing_id, other_version_id, projectId)`
- Types: DwgEntityDiffRow, DwgAnnotationDiffRow, DwgDrawingDiffResponse

### Update AnnotationOverlay.tsx:

- Add diffMode prop
- Support opacity slider

### Similar for takeoff (PDF):

- PdfCompareDrawer.tsx
- TakeoffPage.tsx Compare button integration

---

## Migration

**None.** All columns exist. Query-based on existing data.

---

## File touch list

**Backend:**
- `backend/app/modules/dwg_takeoff/schemas.py` (ADD)
- `backend/app/modules/dwg_takeoff/service.py` (ADD)
- `backend/app/modules/dwg_takeoff/router.py` (ADD)
- `backend/app/modules/takeoff/schemas.py` (ADD)
- `backend/app/modules/takeoff/service.py` (ADD)
- `backend/app/modules/takeoff/router.py` (ADD)

**Frontend:**
- `frontend/src/features/dwg-takeoff/api.ts` (ADD)
- `frontend/src/features/dwg-takeoff/DwgDrawingCompareDrawer.tsx` (NEW)
- `frontend/src/features/dwg-takeoff/DwgTakeoffPage.tsx` (MODIFY)
- `frontend/src/features/dwg-takeoff/components/AnnotationOverlay.tsx` (MODIFY)
- `frontend/src/features/takeoff/PdfCompareDrawer.tsx` (NEW)
- `frontend/src/features/takeoff/TakeoffPage.tsx` (MODIFY)
- `frontend/src/app/locales/en.ts` (ADD i18n)

**Tests:**
- `backend/app/modules/dwg_takeoff/tests/test_compare.py` (NEW)

---

## Conflicts / sequencing

**BOQ module:** Reuses _resolve_project_fx() (existing, no conflict)

**Item #20 (ML extraction):** Both use takeoff tables but no write conflicts. Item #17 ships first, #20 builds on top.

**Wave 4 core modules:** No collisions. DWG/takeoff are standalone.

**Safe to parallel:** Items #1, #2, #20 (dependency only)

---

## Test plan

### Backend unit tests:

1. Entity diff classifies additions/removals/modifications correctly
2. Cost impact: (55m - 50m) * $100/m = $500.00
3. Cost impact null when annotation unlinked
4. Decimal precision and FX conversion respected

### Browser test:

1. Upload DWG V1: 10 entities, 5 annotations (50m linked to BOQ P1 @ $100/m)
2. Upload DWG V2: 12 entities, 6 annotations (55m linked to P1)
3. Click Compare → drawer opens
4. Select V1 → diff loads
5. Entities tab: shows Added/Removed/Modified counts
6. Annotations tab: shows "50m → 55m", BOQ link, "+$500.00" (green)
7. Summary tab: displays totals
8. Toggle Hide unchanged → filters correctly
9. Toggle Overlay → opacity slider works, onion-skin blends
10. Escape closes drawer

**Verification:**
- Cost = (55-50) * 100 = 500 USD ✓
- BOQ identified ✓
- Currency respected ✓
- Decimal precision ✓
- No errors ✓

---

## Risks

1. **Entity diff accuracy** → Unit tests with fixtures
2. **Cost precision** → Use Decimal throughout, reuse BOQ _resolve_project_fx
3. **Large drawing performance** → Add DB index, can optimize in Phase 2
4. **Annotation consistency** → Cost only when same annotation in both versions
5. **PDF versioning** → Use updated_at as surrogate, or user-selected baseline
6. **Mobile UI complexity** → Responsive drawer/modal, Hide unchanged toggle
# Item 21 - ISO 19650 CDE suitability state propagation

## Current state (verified against code)

As of 2026-06-04, the OpenConstructionERP codebase has ISO 19650 infrastructure partially in place:

### What exists:
1. **CDEStateMachine** - State machine enforcing one-way forward transitions (wip -> shared -> published -> archived) with role-based gates. No backtracking allowed.

2. **CDE Container lifecycle** - Full implementation with structural validation, role-based gates, signature validation, audit trail, and suitability validation.

3. **Suitability codes** - ISO 19650 code lookup:
   - WIP: S0
   - SHARED: S1, S2, S3, S4, S6, S7
   - PUBLISHED: A1, A2, A3, A4, A5
   - ARCHIVED: AR

4. **Document model fields** - Columns already added in oe_documents_document table

5. **Document schema** - Update and Response schemas have state/suitability fields

6. **Frontend display** - Badge already renders cde_state color-coded

### What is broken or missing:

1. **CRITICAL: Backtrack transitions allowed** (service.py:618-623)
   - "shared" can backtrack to "wip" (invalid)
   - "published" can backtrack to "wip" (invalid)
   - "archived" can backtrack to "wip" (invalid, terminal)

2. **No suitability validation on Documents PATCH** - Invalid combos accepted

3. **No gate enforcement on Documents PATCH** - Roles and signatures not checked

4. **Frontend suitability_code not displayed** - Only cde_state shown

5. **No DocumentUpdate.model_validator** - No schema validation

## Scope of this increment

Unifies Documents and CDE state-transition rules. Fixes backtracking bug and establishes suitability-code validation.

### Demonstrable outcomes:
1. Invalid backtrack transitions return 400 error
2. Invalid suitability codes return 400 error
3. Promotions without proper role/signature return 400 error
4. Frontend displays suitability_code inline badge
5. All transitions align with CDEStateMachine rules

## Backend changes

### Files touched:

1. **backend/app/modules/documents/service.py** - THREE CHANGES:
   - Remove backtrack transitions from VALID_CDE_TRANSITIONS
   - Add gate enforcement in update_document()
   - Import CDEStateMachine and add _iso_role_for()

2. **backend/app/modules/documents/schemas.py** - ONE CHANGE:
   - Add model_validator to DocumentUpdate

3. **backend/app/modules/documents/router.py** - ONE CHANGE:
   - Pass user_role to update_document()

### No DDL changes required

## Frontend changes

### Files touched:

1. **frontend/src/features/documents/DocumentsPage.tsx** - TWO CHANGES:
   - Display suitability_code alongside cde_state badge
   - Add neutral-gray badge with code

## Migration

**None** - All columns exist.

## File touch list

Backend:
- backend/app/modules/documents/service.py
- backend/app/modules/documents/schemas.py
- backend/app/modules/documents/router.py

Frontend:
- frontend/src/features/documents/DocumentsPage.tsx

Core (unchanged):
- backend/app/core/cde_states.py
- backend/app/modules/cde/suitability.py

## Conflicts / sequencing

**No conflicts.** Isolated to Documents module.

## Test plan

### Browser test:

**Test 1 - No backtrack**:
1. Create document, promote to shared
2. Try PATCH with cde_state=wip -> expect 400

**Test 2 - Suitability validation**:
1. Try PATCH with cde_state=shared, suitability_code=A1 -> expect 400
2. Retry with suitability_code=S1 -> expect 200

**Test 3 - Gate B enforcement**:
1. As editor, try PATCH to published -> expect 400
2. As manager, try without signature -> expect 400
3. With signature -> expect 200

**Test 4 - Frontend display**:
1. Document with cde_state=shared, suitability_code=S1
2. Verify two badges: "SHARED" and "S1"

**Test 5 - Gate C enforcement**:
1. As manager, try PATCH to archived -> expect 400
2. As admin, try PATCH -> expect 200

### Unit tests:
- No backtrack
- Suitability validation
- Gate B enforcement
- Gate C enforcement
- Archived terminal

## Risks

1. Breaking change for backtrack workflows (Mitigation: Bug-exploits)
2. Signature format (Mitigation: MVP accepts any non-empty string)
3. Role mapping edge cases (Mitigation: Safe fail-closed)
4. Metadata collision (Mitigation: Use scoped keys)
5. No concurrent edit guard (Mitigation: Rare operation)
6. i18n missing (Mitigation: MVP shows codes only)

---

**Design document version**: 1.0  
**Date**: 2026-06-04  
**Status**: Ready for implementation  
**Effort estimate**: M (3-4 days)

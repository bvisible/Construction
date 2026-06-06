# Item 27 - Compliance Rule Engine Enforced at Gates (Workflow-Level Enforcement)

## Current state (verified against code)

**Existing compliance infrastructure:**
- `backend/app/core/validation/engine.py`: Full ValidationEngine with RuleRegistry, ValidationRule, and ValidationReport (error/warning/info severity levels, quality scoring)
- `backend/app/modules/compliance/models.py`: ComplianceDSLRule ORM for user-authored validation rules stored as YAML
- `backend/app/modules/compliance/service.py` + `router.py`: Compliance rule CRUD and validation report querying
- `backend/app/modules/projects/models.py`: Project model has `validation_rule_sets` JSON field (defaults to `["boq_quality"]`)
- `backend/app/modules/contracts/models.py`: Contract with `status` field (draft → active → suspended/completed/terminated)
- `backend/app/modules/contracts/service.py`: `transition_contract()` method (lines 880–912) that validates FSM transitions but does NOT call validation engine

**What's missing:**
1. No compliance gate enforcement in contract state transitions (draft→active)
2. No rule-pack concept (jurisdiction-scoped rule bundles stored in DB/seed data)
3. No compliance validation blocking HTTP 422 errors on state transitions
4. No audit trail logging which rule packs were applied
5. No ComplianceGate.tsx UI component to show validation results before transition
6. No project-level rule-pack assignment (projects can select which packs to enforce)

**Partial status notes:**
- ValidationEngine exists but is only called manually from BOQ import workflows
- Contract transitions exist but only check FSM rules, not compliance rules
- No event-based compliance checking on SCO creation (SCOs are in subcontractors module, not fully wired)

---

## Scope of this increment (demonstrable + testable)

**Bounded increment (M effort, ~4–5 days):**

1. **Create rule-pack infrastructure** (seed data + DB model):
   - Add `compliance_rule_packs.py` seed with 4 jurisdiction packs (ae_compliance, in_compliance, ru_compliance, sa_compliance) each with a manifest of rule IDs and metadata
   - Optional: ComplianceRulePack ORM table if packs need to be managed dynamically; for this increment, seed data is sufficient

2. **Wire compliance validation to contract state transitions**:
   - Modify `contracts/service.py::transition_contract()` to call `validation_engine.validate()` before allowing draft→active
   - On has_errors=true, raise HTTP 422 Unprocessable Entity with structured error list
   - Store audit trail in contract.metadata_

3. **Add compliance gate UI component**:
   - New `frontend/src/features/contracts/ComplianceGate.tsx` modal showing validation report
   - Display active rule packs, grouped validation results (errors red, warnings yellow)
   - Show passed rules count
   - Disable "Sign Contract" button if errors exist

4. **Project-level rule-pack selection** (lightweight):
   - Extend project schema to include `compliance_rule_packs` (JSON list)
   - Projects default to region-matched pack

5. **Test plan**:
   - Integration test: Attempt draft→active with compliance violations, verify 422
   - Browser test: ComplianceGate modal blocks transition, user fixes data, gate clears

---

## Backend changes (files, functions, endpoints, models/DDL)

### New/Modified ORM Models

**contracts/models.py** — Contract model (no new columns; use metadata_):
- Audit trail stored in `contract.metadata_["compliance_validation"]`

**projects/models.py** — Project model (add new field):
```python
compliance_rule_packs: Mapped[list] = mapped_column(
    JSON,
    nullable=False,
    default=lambda: ["universal"],
    server_default='["universal"]',
)
```

### New Seed Data

**backend/app/core/compliance_rule_packs.py** (new file):
```python
"""Pre-defined compliance rule packs for jurisdictions."""

RULE_PACKS = {
    "universal": {
        "id": "universal",
        "name": "Universal Compliance",
        "description": "Basic quality and structure checks",
        "jurisdiction": None,
        "enforced_workflows": ["contract_signature"],
        "rule_ids": ["boq.no_zero_quantities", "boq.required_classification"],
    },
    "ae_compliance": {
        "id": "ae_compliance",
        "name": "UAE Compliance",
        "jurisdiction": "AE",
        "enforced_workflows": ["contract_signature"],
        "rule_ids": ["ae.required_uae_nationals", "boq.no_zero_quantities"],
    },
    "in_compliance": {
        "id": "in_compliance",
        "name": "India Compliance",
        "jurisdiction": "IN",
        "enforced_workflows": ["contract_signature"],
        "rule_ids": ["in.epf_contribution_clause"],
    },
    "ru_compliance": {
        "id": "ru_compliance",
        "name": "Russia Compliance",
        "jurisdiction": "RU",
        "enforced_workflows": ["contract_signature"],
        "rule_ids": ["ru.russian_language_required"],
    },
    "sa_compliance": {
        "id": "sa_compliance",
        "name": "Saudi Arabia Compliance",
        "jurisdiction": "SA",
        "enforced_workflows": ["contract_signature"],
        "rule_ids": ["sa.saudi_content_percentage"],
    },
}

def get_rule_pack(pack_id: str) -> dict | None:
    """Fetch rule pack definition by ID."""
    return RULE_PACKS.get(pack_id)
```

### Service Layer Changes

**contracts/service.py::transition_contract()** — Add compliance validation (simplified):
- Call `validation_engine.validate()` before draft→active
- On has_errors, raise HTTP 422 with violation list
- Store audit trail in contract.metadata_["compliance_validation"]

**projects/service.py** — Add method:
```python
async def set_compliance_rule_packs(self, project_id: UUID, rule_pack_ids: list[str]):
    """Set the active compliance rule packs for a project."""
    await self.repo.update_fields(project_id, compliance_rule_packs=rule_pack_ids)
    return await self.get_project(project_id)
```

### Router Endpoints

**projects/router.py** — Add PATCH endpoint:
```python
@router.patch("/{project_id}/compliance-rule-packs")
async def update_project_rule_packs(
    project_id: UUID,
    rule_pack_ids: list[str],
):
    """Set the compliance rule packs enforced for this project."""
```

### DDL / Migrations

**Migration: `alembic/versions/v*_add_compliance_rule_packs.py`:**
```python
"""Add compliance_rule_packs field to projects."""

def upgrade():
    op.add_column(
        'oe_projects_project',
        sa.Column('compliance_rule_packs', sa.JSON(), 
                  nullable=False, server_default='["universal"]'),
    )

def downgrade():
    op.drop_column('oe_projects_project', 'compliance_rule_packs')
```

---

## Frontend changes (route, components, UX)

### New Component: ComplianceGate.tsx

**frontend/src/features/contracts/ComplianceGate.tsx** (new file):
- Modal showing compliance violations grouped by severity
- Red/yellow badges for errors/warnings
- "Proceed" button disabled if errors exist
- Shows passed rules count for transparency

### Modified: ContractWorkflow.tsx
- Integrate ComplianceGate modal
- On transitionContract() 422 error, display modal
- User fixes data and retries

### API Layer: contracts/api.ts
- transitionContract() already exists; update to handle 422 errors

---

## Migration (DDL or "none")

**Required:**
- Add `compliance_rule_packs` JSON column to `oe_projects_project` table
- Alembic file: `alembic/versions/v*_add_compliance_rule_packs.py`

---

## File touch list

### Backend:
1. `backend/app/modules/contracts/service.py` — Add compliance validation to transition_contract()
2. `backend/app/modules/contracts/router.py` — Update response schema
3. `backend/app/modules/projects/models.py` — Add compliance_rule_packs field
4. `backend/app/modules/projects/service.py` — Add set_compliance_rule_packs() method
5. `backend/app/modules/projects/router.py` — Add PATCH endpoint
6. `backend/app/core/compliance_rule_packs.py` — NEW: Rule pack definitions
7. `backend/alembic/versions/v*_add_compliance_rule_packs.py` — NEW: Migration

### Frontend:
1. `frontend/src/features/contracts/ComplianceGate.tsx` — NEW: Modal component
2. `frontend/src/features/contracts/ContractWorkflow.tsx` — Integrate gate
3. `frontend/src/features/contracts/api.ts` — Update error handling

### Tests:
1. `backend/tests/integration/test_contracts_compliance_enforcement.py` — NEW
2. `backend/tests/integration/test_compliance_rule_packs.py` — NEW

---

## Conflicts / sequencing

**No direct conflicts** with Wave 4 items (equipment, documents, bim_hub, ai, fieldreports, field_diary, costmodel, finance, payroll):
- This increment only touches contracts + projects
- Reuses validation engine (Wave 1 item)
- No file collisions with other W4 items

**Depends on:** Wave 1 completion (validation engine already built)

---

## Test plan (browser + unit)

### Unit Tests

**test_contracts_compliance_enforcement.py:**
- Test 1: draft→active with compliance errors → 422 raised
- Test 2: draft→active with compliance passed → success, audit trail set
- Test 3: Project rule pack assignment

### Browser Integration Test

**Route:** `/contracts`

1. Create draft contract with missing required field
2. Click "Sign Contract"
3. Verify ComplianceGate modal appears with red error banner
4. Verify "Proceed" button disabled
5. Fill missing field
6. Click "Sign Contract" again
7. Verify modal shows green success, "Proceed" enabled
8. Click "Proceed"
9. Verify contract transitions to "active", signed_at set

**Screenshot must show:** Compliance Gate modal with error list, red banner, disabled button

---

## Risks

- **Risk 1:** Performance on large contracts — validation could be slow. Mitigation: Cache rules, async validation deferred to future.
- **Risk 2:** Backward compatibility — existing active contracts won't have audit trail. Mitigation: Correct behavior (forward-only).
- **Risk 3:** Rule pack changes mid-project cause confusion. Mitigation: Document this is enforcement-at-transition only.
- **Risk 4:** 422 responses unexpected by old clients. Mitigation: Standard code, documented.
- **Risk 5:** Rule ID typos in seed data. Mitigation: Validate rule IDs exist during pack loading.

---

## Summary

**Item #27 delivers:**
✅ Compliance gate enforcement on contract draft→active transitions
✅ 4 jurisdiction rule packs wired to projects by region
✅ HTTP 422 blocking errors + audit trail
✅ React modal showing violations before state change
✅ Project-level rule-pack selection REST API

**Bounded scope:** 1 migration, ~15 files touched, integration + browser test coverage. Ready for parallel W4 implementation.

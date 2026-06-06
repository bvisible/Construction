# Item 23 — Persistent clash detection profiles and multi-property clash grouping

## Current state (verified against code)

**Clash module status (as of v6.7, 2026-06-04):**
- Backend: ClashRun (oe_clash_run) fully modeled with configuration columns: `name`, `description`, `model_ids` (JSON), `clash_type`, `ignore_same_model`, `tolerance_m`, `clearance_m`, `mode`, `discipline_filter`, `set_a`, `set_b`, `rules` (JSON), `spatial_grid_mm`
- ClashResult (oe_clash_result) has discipline matrix, severity, signature, watchers, history, comments
- ClashIssue (oe_clash_issue) persists clash identity across re-runs with smart status (new/persisted/resolved/ignored/archived)
- ClashCluster (oe_clash_cluster) provides spatial grouping with DBSCAN
- Router endpoints: GET/POST /projects/{id}/runs/, PATCH /rules, list_clusters, list_rule_suggestions
- **Missing: ClashProfile model, CRUD endpoints, profile application, frontend profile manager**

**Frontend:**
- ClashDetectionPage.tsx handles run config form, results table, filters
- ClashRuleEditor.tsx manages per-run rules (live editing in ClashRunResponse)
- No profile picker, save-as-profile button, or profile manager page yet
- Filter persistence via localStorage (clashFilterPersistence.ts) — filters only, not full run config

**Grouping status:**
- `_build_summary()` in service currently generates discipline×discipline matrix (2D only)
- No multi-dimensional grouping support (e.g., level + discipline + system)
- No element_system tracking in ClashResult

**Database migrations:**
- Latest clash migration: v3047_clash_severity_delta (adds severity, signature, due_date, comments)
- No profile table exists

---

## Scope of this increment (demonstrable + testable)

This increment implements **persistent, reusable clash detection profiles** and adds **multi-dimensional clash grouping** to the summary generation. The feature allows coordinators to:

1. **Save clash run configurations as named profiles** (template library per project) with all parameters (tolerance, clearance, mode, discipline filters, selection sets, rules)
2. **Quick-launch new runs from profiles** (pre-populated form, one-click "Apply")
3. **Apply profiles to existing runs** (copy profile config onto a run, re-evaluate if needed)
4. **Group clash results by multiple dimensions** (discipline pair + level + optional system/property)

**Out of scope for this increment:**
- AI-driven rule suggestions across profiles (existing per-run; cross-profile analysis is a future slice)
- Profile versioning / rollback (profiles are mutable; history audit is post-MVP)
- Profile sharing across projects (each project has its own library)
- Automatic profile application on model re-import (manual trigger only)

---

## Backend changes (files, functions, endpoints, models/DDL)

### 1. **New Model: ClashProfile** (backend/app/modules/clash/models.py)

Add new ORM class representing a reusable run configuration:

```python
class ClashProfile(Base):
    """Reusable clash run configuration template per project.
    
    Tables: oe_clash_profile
    """
    
    __tablename__ = "oe_clash_profile"
    __table_args__ = (
        Index("ix_clash_profile_project", "project_id"),
    )
    
    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Run configuration fields (snapshot all parameters)
    clash_type: Mapped[str] = mapped_column(String(16), nullable=False, default="both", server_default="both")
    ignore_same_model: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    tolerance_m: Mapped[float] = mapped_column(Float, nullable=False, default=0.01, server_default="0.01")
    clearance_m: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0.0")
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="cross_discipline", server_default="cross_discipline")
    discipline_filter: Mapped[list | None] = mapped_column(JSON, nullable=True)
    set_a: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    set_b: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    rules: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    spatial_grid_mm: Mapped[int] = mapped_column(Integer, nullable=False, default=500, server_default="500")
    
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
```

### 2. **Add element_system to ClashResult** (backend/app/modules/clash/models.py)

Add two columns to support system-based grouping:

```python
# In ClashResult class, add:
a_element_system: Mapped[str] = mapped_column(String(100), nullable=False, default="", server_default="")
b_element_system: Mapped[str] = mapped_column(String(100), nullable=False, default="", server_default="")
```

### 3. **New Schemas** (backend/app/modules/clash/schemas.py)

Add profile-related Pydantic models:

```python
class ClashProfileCreate(BaseModel):
    name: str = Field(..., max_length=255, min_length=1)
    description: str | None = Field(default=None, max_length=2000)
    clash_type: str = Field(default="both")
    ignore_same_model: bool = Field(default=False)
    tolerance_m: float = Field(default=0.01, ge=0.0, le=10.0)
    clearance_m: float = Field(default=0.0, ge=0.0, le=10.0)
    mode: str = Field(default="cross_discipline")
    discipline_filter: list | None = Field(default=None)
    set_a: ClashSelectionSet | None = Field(default=None)
    set_b: ClashSelectionSet | None = Field(default=None)
    rules: list[ClashRule] = Field(default_factory=list, max_length=500)
    spatial_grid_mm: int = Field(default=500, ge=100, le=5000)

class ClashProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str | None = None
    clash_type: str
    ignore_same_model: bool
    tolerance_m: float
    clearance_m: float
    mode: str
    discipline_filter: list | None = None
    set_a: ClashSelectionSet | None = None
    set_b: ClashSelectionSet | None = None
    rules: list[ClashRule] = Field(default_factory=list)
    spatial_grid_mm: int
    created_by: str
    created_at: datetime
    updated_at: datetime
```

Also update ClashRunCreate to accept optional profile_id field for pre-population.

### 4. **Repository Methods** (backend/app/modules/clash/repository.py)

Add profile CRUD methods:

```python
async def create_profile(self, project_id: uuid.UUID, data: dict) -> ClashProfile
async def list_profiles(self, project_id: uuid.UUID) -> list[ClashProfile]
async def get_profile(self, project_id: uuid.UUID, profile_id: uuid.UUID) -> ClashProfile | None
async def update_profile(self, project_id: uuid.UUID, profile_id: uuid.UUID, data: dict) -> ClashProfile
async def delete_profile(self, project_id: uuid.UUID, profile_id: uuid.UUID) -> bool
```

### 5. **Service Methods** (backend/app/modules/clash/service.py)

Implement high-level profile operations:

```python
async def create_profile(self, project_id: uuid.UUID, data: ClashProfileCreate, user_id: str) -> ClashProfile
async def list_profiles(self, project_id: uuid.UUID) -> list[ClashProfile]
async def get_profile(self, project_id: uuid.UUID, profile_id: uuid.UUID) -> ClashProfile
async def update_profile(self, project_id: uuid.UUID, profile_id: uuid.UUID, data: ClashProfileUpdate, user_id: str) -> ClashProfile
async def delete_profile(self, project_id: uuid.UUID, profile_id: uuid.UUID) -> None

async def apply_profile_to_new_run(
    self, project_id: uuid.UUID, profile_id: uuid.UUID, model_ids: list[uuid.UUID],
    user_id: str, run_name: str | None = None
) -> ClashRunResponse
"""Create and execute a new run using profile as template."""

async def _build_summary_multi_dimensional(
    self, run: ClashRun, grouping_dimension: str | None = None
) -> dict
"""Generate summary with optional multi-dimensional grouping (level, discipline_pair, level_discipline, etc.)."""
```

### 6. **New Router Endpoints** (backend/app/modules/clash/router.py)

Add 6 endpoints for profile CRUD + application:

```
GET    /projects/{project_id}/profiles              → list profiles
POST   /projects/{project_id}/profiles              → create profile
GET    /projects/{project_id}/profiles/{profile_id} → get one profile
PATCH  /projects/{project_id}/profiles/{profile_id} → update profile
DELETE /projects/{project_id}/profiles/{profile_id} → delete profile
POST   /projects/{project_id}/profiles/{profile_id}/apply → apply profile to new/existing run

GET    /projects/{project_id}/runs/{run_id}/summary → get summary with optional grouping_dimension query param
```

All endpoints IDOR-guarded via _require_project_access(), using clash.read/create/delete permissions.

---

## Frontend changes (route, components, UX)

### 1. **New Page: /clash/profiles** (frontend/src/features/clash/ClashProfileManager.tsx)

Full profile manager component with:
- Profile list (left sidebar with cards showing name, rule count, created_at)
- Profile detail panel (right side, read-only view or edit form)
- Actions: Create, Edit, Delete (with confirm), Duplicate, Apply
- Apply modal to select models + optional run name

### 2. **Updates to ClashDetectionPage.tsx**

Add three UX enhancements:
1. **Profile picker dropdown** in run config form (optional, pre-populates all fields)
2. **Save-as-profile button** (appears after run created, opens modal to name the profile)
3. **Profile badge** on run card (linked to profile manager for traceability)
4. **Grouping selector dropdown** (Discipline Pair / Level / Level×Discipline / Discipline×System)

### 3. **API Layer** (frontend/src/features/clash/api.ts)

Add method signatures:

```typescript
clashApi.listProfiles(projectId: uuid)
clashApi.createProfile(projectId: uuid, data: ClashProfileCreate)
clashApi.getProfile(projectId: uuid, profileId: uuid)
clashApi.updateProfile(projectId: uuid, profileId: uuid, data: ClashProfileUpdate)
clashApi.deleteProfile(projectId: uuid, profileId: uuid)
clashApi.applyProfile(projectId: uuid, profileId: uuid, data: ApplyRequest)
clashApi.getSummary(projectId: uuid, runId: uuid, groupingDimension?: string)
```

### 4. **Route Registration**

Add to frontend router: `/clash/profiles?project={projectId}` → ClashProfileManager

---

## Migration (DDL or "none")

**Required: Yes**

### File: backend/alembic/versions/v3100_clash_profiles_grouping.py

Migration creates oe_clash_profile table and adds element_system columns to oe_clash_result:

**CREATE TABLE oe_clash_profile:**
- id (UUID PK)
- project_id (UUID FK, ondelete CASCADE)
- name, description (String, Text)
- clash_type, ignore_same_model, tolerance_m, clearance_m, mode (String, Boolean, Float)
- discipline_filter, set_a, set_b, rules (JSON)
- spatial_grid_mm (Integer)
- created_by (String)
- created_at, updated_at (DateTime with timezone)
- Indexes: project_id
- Constraint: UNIQUE(project_id, name)

**ALTER TABLE oe_clash_result:**
- ADD COLUMN a_element_system (String 100, default "")
- ADD COLUMN b_element_system (String 100, default "")

Idempotent, inspector-guarded (safe for dev auto-migrate + prod alembic).

---

## File touch list

**Backend:**
- backend/app/modules/clash/models.py (ClashProfile class + element_system columns)
- backend/app/modules/clash/schemas.py (ClashProfileCreate, ClashProfileRead, update ClashRunCreate)
- backend/app/modules/clash/repository.py (profile CRUD methods)
- backend/app/modules/clash/service.py (profile lifecycle + apply + multi-dim grouping)
- backend/app/modules/clash/router.py (6 new endpoints + summary endpoint)
- backend/alembic/versions/v3100_clash_profiles_grouping.py (new migration)

**Frontend:**
- frontend/src/features/clash/ClashProfileManager.tsx (new)
- frontend/src/features/clash/ClashDetectionPage.tsx (profile picker, save-as, grouping selector)
- frontend/src/features/clash/api.ts (profile methods + getSummary)
- frontend/src/app/router.tsx or routing module (add /clash/profiles route)

**No changes to:** notifications, punchlist, NCR, or other modules.

---

## Conflicts / sequencing

**No conflicts:**
- Item #0 (clash lifecycle + notifications) is orthogonal (profiles are metadata templates)
- Wave 4 items (field, payroll, EVM, connectors, portfolio, dependencies, AI photos, tendering, liens, commitment) touch different modules
- Profiles are project-scoped, use only clash module tables
- Can ship independently in parallel

**Sequencing:** None required. Can implement + ship standalone.

---

## Test plan (browser + unit)

### Unit tests (backend/app/modules/clash/test_profiles.py)

- test_create_profile: save config as profile, verify name + tolerance
- test_duplicate_name_fails: unique(project_id, name) constraint
- test_apply_profile_to_new_run: profile → new run with matching config
- test_apply_profile_to_existing_run: overwrite run config with profile
- test_delete_profile: profile removed from list
- test_multi_dimensional_summary_discipline_pair: default grouping
- test_multi_dimensional_summary_by_level: group by storey
- test_multi_dimensional_summary_level_discipline: 2D matrix per level

### Browser test (manual QA, Chrome DevTools)

**Scenario 1: Profile CRUD**
1. Navigate to /clash/profiles?project={id}
2. Click "+ New Profile"
3. Fill: name="MEP-Struct", tolerance=0.02, clearance=0.1, mode=cross_discipline
4. Save → profile appears in list
5. Click "Edit" → change tolerance to 0.05 → Save → verify updated_at changes
6. Delete → confirm dialog → profile gone from list
7. Verify HTTP 201/200/204/404 responses, no console errors

**Scenario 2: Apply to new run**
1. Profile detail → click "Apply"
2. Modal: select 2 models, run name="Test from Profile"
3. Click "Create Run" → engine executes
4. Verify run detail shows tolerance=0.05, clearance=0.1
5. Badge on run links back to profile

**Scenario 3: Save run as profile**
1. Create run with custom config (tolerance=0.03, rules=[...])
2. Run detail → "Save Config as Profile"
3. Modal: name="Custom Tune", description
4. Save → verify in /clash/profiles list
5. Profile has all run config fields

**Scenario 4: Multi-dimensional grouping**
1. Execute run with 50+ clashes (multiple levels, disciplines, systems)
2. Results table → grouping selector
3. Select "Level × Discipline" → summary recomputes, shows level tabs + matrix
4. Select "Discipline × System" → new grouping renders
5. Filter counts update for new grouping
6. No console errors, XHR 200s

**Assertions:**
- All XHR calls return 200/201/204/404 as expected
- Zero console errors
- Profile list matches schema
- Grouping selector responsive
- Profile name unique per project
- Delete actually removes (soft or hard)

---

## Risks

1. **Migration safety:** Additive columns + new table. Inspector-guarded, safe for SQLite auto-create + Postgres alembic.
2. **Profile uniqueness:** Enforced at DB constraint level (UNIQUE) + service validation.
3. **Element_system extraction:** If BIM has no system metadata, columns stay empty. Grouping selector hides "Discipline×System" when data absent. Graceful degradation.
4. **Multi-dim summary perf:** Grouping 25k+ clashes on high-cardinality dims could be slow. Mitigation: cap limit + 60s client-side cache.
5. **Backward compat:** Old runs stay unchanged. New runs optionally link profile_id for breadcrumb. Fully backward-compatible.
6. **i18n:** Add profile UI labels to en.ts + run i18n-sweep. No hardcoded strings in components.

---
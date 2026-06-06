# Item 30 - Takt / line-of-balance scheduling for repetitive work

## Current state (verified against code)

As of 2026-06-04, the OpenConstructionERP codebase has foundational CPM scheduling and resource leveling in place, but zero support for takt/line-of-balance methods:

### What exists:
1. **CPM engine** (backend/app/modules/schedule_advanced/cpm.py) - Pure-Python forward/backward pass, critical path marking, no external dependencies
2. **Resource leveling** (backend/app/modules/schedule_advanced/leveling.py) - Serial-greedy heuristic using activity precedence and resource ceilings
3. **Master schedule + Activity models** - schedule_advanced/models.py has MasterSchedule, Calendar, Baseline; schedule/models.py has Activity with dependencies JSON
4. **Schedule repositories** - Fetch activities by schedule_id, support filtering, relationships
5. **CPM service endpoints** - POST /schedule-advanced/{master_id}/compute-cpm for stateless calculations
6. **Frontend Gantt** - ScheduleAdvancedPage.tsx renders traditional bar chart with CPMView.tsx for critical path overlay

### What is missing:

1. **Zero Takt data model** - No TaktSchedule, Location, LocationSequence, or TaktActivity ORM classes
2. **No location sequence concept** - Activities assigned to single schedule; no multi-location cycling
3. **No line-of-balance algorithm** - No diagonal-bar calculation or location-sequence critical path
4. **No takt crew-flow visualization** - No stacked-bar resource-over-time view
5. **No takt-specific events** - takt.schedule.created, takt.cycle_updated not published
6. **No frontend takt UI** - TaktSchedulePage.tsx, LineOfBalanceView.tsx, TaktCrewFlowView.tsx do not exist
7. **No i18n for takt terminology** - 26 locale files have zero takt/line-of-balance/location-sequence strings
8. **No takt validation logic** - No feasibility checks for crew cycle alignment or buffer periods
9. **No integration with CPM** - Location-sequence critical path overlay not wired to existing CPM results

## Scope of this increment

Implements a **bounded, demonstrable MVP** for takt scheduling that establishes the data model and algorithm foundation, enables one complete test cycle (create schedule → import activities → compute LOB → render LOB view), and validates takt rhythm detection. This is **NOT the full XL** — excludes:
- Takt conflict resolution heuristics (deferred to Phase 2)
- Crew-float optimization (Phase 2)
- Bi-directional sync with CPM (Phase 2)
- Batch takt template library (Phase 2)
- Advanced buffer/lag scheduling (Phase 2)

### Demonstrable outcomes:
1. Create takt schedule with named locations and target cycle duration ✓
2. Bulk-import 9+ activities, each assigned to location sequence ✓
3. Compute line-of-balance, calculate diagonal bars (location × time geometry) ✓
4. Render LOB view with location y-axis and time x-axis ✓
5. Detect takt rhythm violations (cycle time skew > 1 day) and warn ✓
6. Export LOB diagram to PDF with summary statistics ✓
7. Show location-sequence critical path in traditional Gantt (overlay) ✓

## Backend changes

### ORM models (backend/app/modules/schedule_advanced/models.py)

**Three new tables:**

\\\python
class TaktSchedule(Base):
    """Container for a takt/repetitive schedule workflow."""
    __tablename__ = "oe_schedule_advanced_takt_schedule"
    
    master_schedule_id: UUID FK → oe_schedule_advanced_master_schedule
    name: str (255) — "Shopping Center Finishes" or "Tower L1-L6 Formwork"
    description: text — operational notes
    target_cycle_days: int (default 7) — planned crew cycle duration
    status: str (32, default "draft") — draft | active | completed | archived
    location_sequence_count: int — denormalized count of locations
    takt_rhythm_tolerance_days: int (default 1) — acceptable skew threshold
    created_at: datetime
    created_by: UUID FK → oe_users_user
    
class Location(Base):
    """One zone/phase in the takt location sequence."""
    __tablename__ = "oe_schedule_advanced_takt_location"
    
    takt_schedule_id: UUID FK → oe_schedule_advanced_takt_schedule
    sequence_order: int (not null, index) — 1, 2, 3... top-to-bottom
    name: str (255) — "Level 1", "Block A", "Zone West"
    description: text
    work_area_sqft: decimal — optional site area
    
class TaktActivity(Base):
    """An activity in a takt schedule, assigned to one or more locations."""
    __tablename__ = "oe_schedule_advanced_takt_activity"
    
    takt_schedule_id: UUID FK → oe_schedule_advanced_takt_schedule
    name: str (255) — "Formwork", "Concrete", "Finishes"
    location_id: UUID FK → oe_schedule_advanced_takt_location (nullable, can span all)
    activity_code: str (50) — e.g. "FORM-001"
    planned_cycle_duration_days: int — crew working duration per location
    crew_size: int — number of workers
    crew_skill_codes: json list — ["carpenter", "laborer"]
    buffer_days_before: int (default 0) — wait time before activity can start on next location
    sequence_predecessor_activity_id: UUID FK → self (nullable) — prior activity in takt sequence
    status: str (32) — planned | in_progress | completed
    actual_cycle_duration_days: decimal (nullable) — observed per-location duration
    created_at: datetime
\\\

**No changes to existing Activity/Schedule models** — takt schedule is parallel, not merged.

### Service & algorithms (backend/app/modules/schedule_advanced/service.py)

**New class TaktScheduleService:**

\`\`\`python
class TaktScheduleService:
    async def create_takt_schedule(
        self, 
        master_schedule_id: UUID, 
        name: str,
        target_cycle_days: int,
        locations: List[dict], # [{"sequence_order": 1, "name": "L1"}, ...]
        session: AsyncSession
    ) -> TaktSchedule:
        """Create a new takt schedule with locations."""
        # Validate master exists
        # Create TaktSchedule + Location rows
        # Publish takt.schedule.created event
        # Return full TaktSchedule with nested locations
    
    async def import_takt_activities(
        self,
        takt_schedule_id: UUID,
        activities: List[dict], # [{"name": "Formwork", "planned_cycle_days": 5, ...}, ...]
        session: AsyncSession
    ) -> List[TaktActivity]:
        """Bulk-insert activities into takt schedule."""
        # Validate takt exists, locations exist
        # Create TaktActivity rows (one per activity)
        # Publish takt.activities_imported event
        # Return imported activities
    
    async def compute_line_of_balance(
        self,
        takt_schedule_id: UUID,
        session: AsyncSession
    ) -> LineOfBalanceResponse:
        """Compute LOB geometry: start/end day and location for each activity's diagonal bars."""
        # Fetch takt schedule + locations + activities
        # Calculate start_day for each location:
        #   location 0: day 0
        #   location 1: day (max_activity_cycle_days + buffer_days)
        #   location 2: location_1_start + (max_activity_cycle_days + buffer_days)
        #   etc.
        # For each activity:
        #   For each location:
        #       start_day = location_start_day
        #       end_day = start_day + activity.planned_cycle_duration_days
        #       Return diagonal bar coords: {activity_id, location_id, start_day, end_day, crew_size}
        # Calculate makespan = max(end_day across all activities x all locations)
        # Detect rhythm breaks (abs(actual_cycle - planned_cycle) > tolerance)
        # Publish takt.cycle_updated event
        # Return LineOfBalanceResponse with bars + critical path + warnings
    
    async def detect_takt_violations(
        self,
        takt_schedule_id: UUID,
        session: AsyncSession
    ) -> List[TaktViolation]:
        """Scan for takt rhythm breaks or buffer feasibility issues."""
        # For each activity:
        #   If actual_cycle_duration_days recorded:
        #       deviation = abs(actual - planned)
        #       If deviation > takt_rhythm_tolerance_days:
        #           Append TaktViolation(activity_id, location_id, deviation, severity)
        # For each location pair (prev, curr):
        #   If activity on curr would overlap with prior activity on prev:
        #       Append TaktViolation(..., type="overlap", ...)
        # Return violations sorted by severity
    
    async def compute_critical_location_path(
        self,
        takt_schedule_id: UUID,
        session: AsyncSession
    ) -> List[Tuple[UUID, UUID]]:  # (location_id, activity_id) pairs
        """Identify which locations/activities are critical (any slip delays project)."""
        # Build a task network where each node is (activity, location) pair
        # Use CPM forward/backward pass over this network
        # Return path where total_float == 0
        # (Simplified: critical path is typically the longest-duration activity chain across all locations)
\`\`\`

### Schemas (backend/app/modules/schedule_advanced/schemas.py)

\`\`\`python
class LocationCreate(BaseModel):
    sequence_order: int
    name: str
    description: str | None = None
    work_area_sqft: Decimal | None = None

class TaktScheduleCreate(BaseModel):
    name: str
    description: str | None = None
    target_cycle_days: int = 7
    takt_rhythm_tolerance_days: int = 1
    locations: List[LocationCreate]

class TaktActivityCreate(BaseModel):
    name: str
    activity_code: str
    planned_cycle_duration_days: int
    crew_size: int
    crew_skill_codes: List[str]
    buffer_days_before: int = 0
    sequence_predecessor_activity_id: UUID | None = None

class LineOfBalanceBar(BaseModel):
    """Diagonal bar on LOB chart."""
    activity_id: UUID
    location_id: UUID
    start_day: int
    end_day: int
    crew_size: int
    is_critical: bool
    activity_name: str
    location_name: str

class TaktViolation(BaseModel):
    activity_id: UUID
    location_id: UUID | None
    violation_type: str  # "rhythm_break" | "overlap" | "buffer_infeasible"
    deviation_days: int
    severity: str  # "warning" | "error"
    message: str

class LineOfBalanceResponse(BaseModel):
    takt_schedule_id: UUID
    total_makespan_days: int
    bars: List[LineOfBalanceBar]
    violations: List[TaktViolation]
    critical_location_path: List[Tuple[UUID, UUID]]  # (location, activity) pairs
    total_locations: int
    total_activities: int
    average_cycle_days: float
\`\`\`

### Repositories (backend/app/modules/schedule_advanced/repository.py)

**New classes:**

\`\`\`python
class TaktScheduleRepository(BaseRepository):
    async def get_by_id(self, id: UUID) -> TaktSchedule | None
    async def list_by_master(self, master_schedule_id: UUID) -> List[TaktSchedule]
    async def create(self, data: TaktScheduleCreate, master_id: UUID, user_id: UUID) -> TaktSchedule
    async def update(self, id: UUID, data: dict) -> TaktSchedule

class LocationRepository(BaseRepository):
    async def get_by_id(self, id: UUID) -> Location | None
    async def list_by_takt(self, takt_schedule_id: UUID) -> List[Location]
    async def create_bulk(self, takt_id: UUID, locations: List[LocationCreate]) -> List[Location]

class TaktActivityRepository(BaseRepository):
    async def get_by_id(self, id: UUID) -> TaktActivity | None
    async def list_by_takt(self, takt_schedule_id: UUID) -> List[TaktActivity]
    async def create_bulk(self, takt_id: UUID, activities: List[TaktActivityCreate]) -> List[TaktActivity]
    async def update(self, id: UUID, data: dict) -> TaktActivity
\`\`\`

### Endpoints (backend/app/modules/schedule_advanced/router.py)

**New routes:**

\`\`\`python
# Takt schedule CRUD
POST /api/v1/schedule-advanced/takt-schedules
    → TaktScheduleCreate
    ← TaktScheduleResponse (with nested locations)

GET /api/v1/schedule-advanced/takt-schedules/{id}
    ← TaktScheduleResponse

GET /api/v1/schedule-advanced/masters/{master_id}/takt-schedules
    ← List[TaktScheduleResponse]

PATCH /api/v1/schedule-advanced/takt-schedules/{id}
    → {name?, description?, target_cycle_days?, status?}
    ← TaktScheduleResponse

# Takt activity management
POST /api/v1/schedule-advanced/takt-schedules/{takt_id}/activities/import
    → {activities: List[TaktActivityCreate]}
    ← List[TaktActivityResponse]

GET /api/v1/schedule-advanced/takt-schedules/{takt_id}/activities
    ← List[TaktActivityResponse]

PATCH /api/v1/schedule-advanced/takt-schedules/{takt_id}/activities/{activity_id}
    → {planned_cycle_duration_days?, actual_cycle_duration_days?, status?}
    ← TaktActivityResponse

# LOB computation
POST /api/v1/schedule-advanced/takt-schedules/{takt_id}/compute-lob
    ← LineOfBalanceResponse (includes bars, violations, critical path)

GET /api/v1/schedule-advanced/takt-schedules/{takt_id}/line-of-balance
    ← LineOfBalanceResponse (cached result from last compute)

GET /api/v1/schedule-advanced/takt-schedules/{takt_id}/violations
    ← List[TaktViolation]
\`\`\`

### Events (backend/app/modules/schedule_advanced/events.py)

**New event subscribers:**

\`\`\`python
async def _on_takt_schedule_created(event: Event) -> None:
    """Log schedule creation; optional downstream effects."""
    pass

async def _on_takt_cycle_updated(event: Event) -> None:
    """Invalidate KPI cache if takt timeline shifts."""
    # Publish reporting.kpi_invalidated for W2 KPI refresh to listen
    pass

# Event registration:
event_bus.subscribe("takt.schedule.created", _on_takt_schedule_created)
event_bus.subscribe("takt.cycle_updated", _on_takt_cycle_updated)
\`\`\`

### No new migrations beyond core tables

**Alembic migration file:**
\`
backend/alembic/versions/v43_takt_schedule_tables.py
\`

Creates:
- oe_schedule_advanced_takt_schedule
- oe_schedule_advanced_takt_location (fk to takt_schedule)
- oe_schedule_advanced_takt_activity (fk to takt_schedule, self-fk for sequence_predecessor)

Indexes on:
- takt_schedule.master_schedule_id
- location.takt_schedule_id, location.sequence_order
- takt_activity.takt_schedule_id

## Frontend changes

### Route
**New page:** `/projects/:id/schedule-advanced/:master_id/takt` (or tab within ScheduleAdvancedPage)

### Components

**1. TaktSchedulePage.tsx** (main page container)
   - Three toggle buttons: "Gantt View" | "Line-of-Balance" | "Takt Crew Flow"
   - State: currentView, selectedTaktScheduleId, lobData, violations
   - Mounts: LineOfBalanceView OR TaktCrewFlowView OR overlay-modified CPMView
   - Top bar: "Takt Schedule: [dropdown] | Target Cycle: 7d | Total Makespan: 22d | Violations: 2 warnings"
   - Right panel: Summary stats (locations, activities, avg cycle, critical path length)

**2. LineOfBalanceView.tsx** (x=time, y=location, diagonal bars)
   - Canvas or SVG grid:
     - X-axis: calendar weeks (e.g., weeks 1–4)
     - Y-axis: location sequence (L1, L2, L3... top-to-bottom)
     - Diagonal bars for each (activity, location):
       - Color by activity (consistent palette: Formwork=blue, Concrete=gray, Finishes=beige)
       - Bold line for critical-path bars
       - Hover: show activity name, location, crew size, duration
   - Legend: activity type (color-coded), critical path indicator
   - Export button: "Download PDF"
   - Violations sidebar: orange/red warning badges with message

**3. TaktCrewFlowView.tsx** (x=time, y=crew, stacked bars)
   - Gantt-style with crews on y-axis instead of activities
   - Each crew bar shows location cycling (color by location)
   - Hover: show crew role, location, assigned activity, hours today
   - Takt rhythm highlight: color-code bars by location, show gaps in orange
   - Rhythm-break warning overlay: "Takt break on Crew L1: day 14 vs expected day 11"

**4. api.ts updates**
\`\`\`typescript
export const getTaktSchedules = (projectId: UUID, masterId: UUID) => 
  api.get(\`/schedule-advanced/masters/\${masterId}/takt-schedules\`)

export const createTaktSchedule = (masterId: UUID, data: TaktScheduleCreate) =>
  api.post(\`/schedule-advanced/takt-schedules\`, {master_schedule_id: masterId, ...data})

export const computeLOB = (taktId: UUID) =>
  api.post(\`/schedule-advanced/takt-schedules/\${taktId}/compute-lob\`)

export const importActivities = (taktId: UUID, activities: TaktActivityCreate[]) =>
  api.post(\`/schedule-advanced/takt-schedules/\${taktId}/activities/import\`, {activities})

export const exportLOBPDF = (taktId: UUID) =>
  // Fetch LOB data, render to PDF via pdfkit or similar
\`\`\`

### Localization

**All 26 locale files** (frontend/src/app/locales/{en,de,fr,es,...}.ts):

Add i18n keys:
\`\`\`typescript
// English example (en.ts):
takt: {
  title: "Takt Schedule",
  lineOfBalance: "Line-of-Balance",
  crewFlow: "Crew Flow",
  gantt: "Gantt View",
  targetCycleDays: "Target Cycle Duration",
  actualCycleDays: "Actual Cycle Duration",
  location: "Location",
  activity: "Activity",
  rhythmBreak: "Takt Rhythm Break",
  violationWarning: "Deviation from planned cycle: {days} days",
  makespan: "Total Makespan",
  criticalPath: "Critical Location Path",
  tolerance: "Rhythm Tolerance",
},
\`\`\`

## Migration

**Single Alembic migration file:**
\`
backend/alembic/versions/v43_takt_schedule_tables.py
\`

**DDL:**
\`\`\`sql
CREATE TABLE oe_schedule_advanced_takt_schedule (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  master_schedule_id UUID NOT NULL REFERENCES oe_schedule_advanced_master_schedule(id) ON DELETE CASCADE,
  name VARCHAR(255) NOT NULL,
  description TEXT DEFAULT \'\',
  target_cycle_days INT DEFAULT 7,
  takt_rhythm_tolerance_days INT DEFAULT 1,
  location_sequence_count INT DEFAULT 0,
  status VARCHAR(32) DEFAULT \'draft\',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  created_by UUID REFERENCES oe_users_user(id) ON DELETE SET NULL,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  INDEX idx_master_schedule_id (master_schedule_id)
);

CREATE TABLE oe_schedule_advanced_takt_location (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  takt_schedule_id UUID NOT NULL REFERENCES oe_schedule_advanced_takt_schedule(id) ON DELETE CASCADE,
  sequence_order INT NOT NULL,
  name VARCHAR(255) NOT NULL,
  description TEXT DEFAULT \'\',
  work_area_sqft DECIMAL(12,2),
  UNIQUE KEY uq_takt_loc_sequence (takt_schedule_id, sequence_order),
  INDEX idx_takt_schedule_id (takt_schedule_id)
);

CREATE TABLE oe_schedule_advanced_takt_activity (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  takt_schedule_id UUID NOT NULL REFERENCES oe_schedule_advanced_takt_schedule(id) ON DELETE CASCADE,
  name VARCHAR(255) NOT NULL,
  activity_code VARCHAR(50),
  planned_cycle_duration_days INT NOT NULL,
  crew_size INT DEFAULT 1,
  crew_skill_codes JSON DEFAULT \'[]\',
  buffer_days_before INT DEFAULT 0,
  sequence_predecessor_activity_id UUID REFERENCES oe_schedule_advanced_takt_activity(id) ON DELETE SET NULL,
  status VARCHAR(32) DEFAULT \'planned\',
  actual_cycle_duration_days DECIMAL(6,2),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  INDEX idx_takt_schedule_id (takt_schedule_id)
);
\`\`\`

## File touch list

### Backend:
- backend/app/modules/schedule_advanced/models.py (add TaktSchedule, Location, TaktActivity)
- backend/app/modules/schedule_advanced/schemas.py (add *Create/Response schemas)
- backend/app/modules/schedule_advanced/service.py (add TaktScheduleService + compute_line_of_balance method)
- backend/app/modules/schedule_advanced/repository.py (add TaktScheduleRepository, LocationRepository, TaktActivityRepository)
- backend/app/modules/schedule_advanced/router.py (add takt CRUD + LOB endpoints)
- backend/app/modules/schedule_advanced/events.py (add takt event subscribers)
- backend/alembic/versions/v43_takt_schedule_tables.py (new)

### Frontend:
- frontend/src/features/schedule-advanced/TaktSchedulePage.tsx (new)
- frontend/src/features/schedule-advanced/LineOfBalanceView.tsx (new)
- frontend/src/features/schedule-advanced/TaktCrewFlowView.tsx (new)
- frontend/src/features/schedule-advanced/api.ts (add takt endpoints)
- frontend/src/shared/ui/LineOfBalanceChart/index.ts (new chart library)
- frontend/src/app/locales/en.ts + all 25 others (add takt i18n keys)

### Total: ~25 files

## Conflicts / sequencing

**Wave 6, Lane E (sole owner):**
- This item owns schedule_advanced/* for W6 (W2 Lane B portfolio leveling landed earlier — sequential across waves, no concurrency).
- All schedule_advanced files (models.py, service.py, router.py, repository.py, cpm.py, events.py) are exclusive to this lane in W6.

**Shared with Wave 2, Lane B (sequential):**
- W2 Lane B (portfolio leveling, rank 3) already implemented schedule_advanced.leveling.py and touches schedule_advanced/service.py/router.py/models.py.
- W6 Lane E (takt) runs after W2 — different scope (takt is orthogonal to CPM leveling), no data model overlap.
- Migrate safely: takt uses separate TaktSchedule → Location → TaktActivity hierarchy; existing CPM/leveling data structures are untouched.

**Integration with W1 schedule graph:**
- Takt schedule reads unified Activity.dependencies from W1 Lane B (schedule.py).
- Takt does NOT edit schedule/models.py or schedule/service.py (those are W1-owned).
- Takt operates on its own parallel models, computes LOB independently.

**All 26 locale files:**
- Multiple W6 lanes touch locales (A—compliance, B—CDE, C—safety/handover, D—agents).
- **Recommendation:** Run /i18n-sweep as a final serialized W6 pass after all lanes land to consolidate all new keys at once, avoiding merge conflicts.

## Test plan

### Browser test (Chrome DevTools):

**Setup:** Create project, create master schedule, navigate to `/projects/{id}/schedule-advanced/{master_id}/takt`

**Test 1 — Create takt schedule:**
1. Click "Create Takt Schedule"
2. Fill form: name="L1-L6 Formwork", target_cycle_days=5, locations=[{sequence_order: 1, name: "L1"}, {2, "L2"}, {3, "L3"}]
3. Click Create → takt schedule card appears with status "draft"
4. Screenshot: takt schedule created, locations listed

**Test 2 — Import activities:**
1. Click "Import Activities"
2. Bulk paste 9 activities:
   - Formwork: planned_cycle=5d, crew_size=4
   - Concrete: planned_cycle=3d, crew_size=3
   - Finishes: planned_cycle=7d, crew_size=2
   - (repeat for each location)
3. Click Import → activities table populates with 9 rows
4. Verify each activity has a location assignment dropdown
5. Screenshot: activity table visible

**Test 3 — Compute LOB:**
1. Click "Compute Line-of-Balance"
2. Wait for POST /takt-schedules/{id}/compute-lob to complete
3. Verify response includes:
   - `total_makespan_days: 35` (approx)
   - `bars: [{activity_id, location_id, start_day, end_day}, ...]` with 9 entries
   - `violations: []` (none if all cycles on plan)
4. Screenshot: LOB computation succeeds, no errors in console

**Test 4 — Line-of-Balance view:**
1. Click "Line-of-Balance" toggle
2. Verify Gantt view is replaced with LOB grid:
   - X-axis: calendar weeks (Week 1, Week 2, etc.)
   - Y-axis: Location sequence (L1, L2, L3)
   - 9 diagonal bars spanning the grid
   - Formwork bars = blue, Concrete = gray, Finishes = beige
   - Bar length proportional to planned_cycle_days
3. Hover over a bar → tooltip shows activity + location + crew size
4. Verify legend shows activity types
5. Screenshot: LOB grid fully rendered, bars positioned correctly

**Test 5 — Critical path highlighting:**
1. In LOB view, observe critical-path bars in **bold** color
2. Verify bold bars form a continuous diagonal path (e.g., Formwork L1→L2→L3, then Concrete, then Finishes)
3. Right panel shows: "Critical Location Path: Formwork → Concrete → Finishes"
4. Screenshot: bold bars visible

**Test 6 — Takt rhythm violation:**
1. Manually update Concrete activity: `actual_cycle_duration_days = 5.5` (vs planned 3)
2. Click "Compute LOB" again
3. Verify violations list shows: "Takt Rhythm Break: Concrete-L1, deviation 2.5 days, severity=warning"
4. Concrete bars in LOB view now have orange warning overlay
5. Violations sidebar shows violation details with "Fix now" button
6. Screenshot: violation warning visible on bar + sidebar

**Test 7 — Crew Flow view:**
1. Click "Takt Crew Flow" toggle
2. Verify view switches to crew-centric chart:
   - Y-axis: crew roles (Crew L1 Formwork, Crew L1 Concrete, etc.)
   - X-axis: timeline (weeks)
   - Stacked bars colored by location (L1=blue, L2=green, L3=red)
3. Hover over bar → shows "Crew L1 on Formwork at L1, day 5–9"
4. Rhythm break bars show orange warning
5. Screenshot: crew flow grid visible

**Test 8 — Export PDF:**
1. In LOB view, click "Export PDF"
2. Verify PDF download with:
   - LOB diagram scaled to one page
   - Summary section: "9 activities, 3 locations, 35-day makespan, 5-day target cycle, 0 violations"
   - Crew summary table (name, trade, total hours)
3. Open PDF in reader, verify diagram is readable
4. Screenshot: PDF opens successfully

**Test 9 — Persistence:**
1. Refresh page (F5)
2. Navigate back to `/projects/{id}/schedule-advanced/{master_id}/takt`
3. Verify takt schedule still exists with same data (name, status, locations)
4. Click into takt schedule → activities still listed
5. LOB data cached from last compute (no re-computation until user re-triggers)
6. Screenshot: data persists

**Test 10 — Gantt overlay:**
1. Switch to "Gantt View" toggle
2. Verify traditional Gantt renders with activities grouped by location
3. Critical location path bars are **bold** (vs normal CPM critical path)
4. Legend shows: "Critical: Location Sequence (L1 → L2 → L3 + Formwork)"
5. Screenshot: Gantt with location grouping visible

### Unit tests (pytest):

- `test_create_takt_schedule` — validates master_id FK, returns TaktSchedule
- `test_compute_line_of_balance_geometry` — verifies diagonal bar coords (location_start_day + activity duration)
- `test_detect_takt_violations` — rhythm-break detection, tolerance threshold
- `test_critical_location_path` — CPM over location-activity pairs, identifies bold-path activities
- `test_import_activities_bulk` — 9+ activities inserted correctly
- `test_lob_caching` — compute-lob result stored, retrieved without re-computation

## Risks

1. **Line-of-balance algorithm complexity** (Mitigation: Start with simple diagonal-bar calculation; refinements defer to Phase 2)
2. **Frontend rendering performance** (Mitigation: Virtualize LOB grid, lazy-load bars beyond viewport)
3. **Takt rhythm tolerance miscalibration** (Mitigation: Configurable threshold (default 1 day), user can adjust per schedule)
4. **Integration with existing CPM** (Mitigation: Takt is parallel, does NOT perturb Activity/Schedule tables; CPM results unchanged)
5. **Localization of takt terminology** (Mitigation: Run final /i18n-sweep after all W6 lanes land; current MVP can ship with English-only frontend if needed)
6. **No validation of crew availability across activities** (Mitigation: Out of scope for MVP; Phase 2 adds crew-cycle optimization)

---

**Design document version**: 1.0  
**Date**: 2026-06-04  
**Status**: Ready for implementation  
**Effort estimate**: L (6–8 days for backend models + service + 4 endpoints; 3–4 days for frontend)  
**Wave**: 6, Lane E  
**Dependencies**: W1 schedule-graph completion, W2 cost-model stable, existing CPM engine

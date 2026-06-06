# Item 13 - LTIFR/TRIR computed + safety trend analytics

## Current state (verified)

**Backend (backend/app/modules/safety/):**

- SafetyIncident model (oe_safety_incident) with incident_date (ISO YYYY-MM-DD), days_lost, treatment_type, metadata_
- SafetyObservation model (oe_safety_observation) with created_at, severity, likelihood, risk_score
- SafetyService.get_stats() computes LTIFR/TRIR globally (lines 488-492):
  - LTIFR = lost_time_incidents * 1_000_000 / total_hours_worked (ILO/AS-1885 per 1M hours)
  - TRIR = recordable_incidents * 200_000 / total_hours_worked (OSHA per 200k hours)
  - **Limitation:** Only point-in-time global rate, not rolling time series
- SafetyService.get_trends() returns time-series incident/observation counts (lines 510-582)
  - **Limitation:** No LTIFR/TRIR rates per period; only raw counts and days_lost

**Frontend (frontend/src/features/safety/):**

- SafetyPage.tsx with incidents, observations, export tabs
- QualityDashboardSummary widget showing open incidents, inspections, NCRs, defects
- **Limitation:** No LTIFR/TRIR chart; no trend visualization; no early-warning threshold alerts

**Current gaps:**
1. No rolling 12-month LTIFR/TRIR time series
2. No period-over-period trend detection (improving vs declining)
3. No threshold alert mechanism (green/yellow/red status)
4. No crew/department-level LTIFR/TRIR breakdown
5. No frontend trends chart visualization
6. No trend direction heuristic (improving/stable/declining)

---

## Exact bounded scope (demonstrable)

**Goal:** Implement rolling 12-month LTIFR/TRIR trends with threshold alerts and a trends chart on SafetyPage.

**What ships:**

1. **New endpoint: GET /trends/extended**
   - Query: project_id, period (monthly|weekly, default=monthly)
   - Response: SafetyTrendsExtendedResponse with LTIFR/TRIR per period, rolling 12-month avg, trend direction
   - Calculation: For each period bucket, sum man_hours_total and compute LTIFR/TRIR
   - Example: "2025-12" → 2 LTI + 40k hours → LTIFR=50.0; "2026-01" → 1 LTI + 50k hours → LTIFR=20.0

2. **New endpoint: GET /threshold-alert**
   - Query: project_id, baseline_ltifr (default=2.5), baseline_trir (default=3.0)
   - Response: SafetyThresholdAlertResponse with current LTIFR/TRIR, baseline, delta, status
   - Logic: status=green if current ≤ baseline; yellow if 120%-150% of baseline; red if >150%

3. **New schemas:**
   - SafetyTrendEntryExtended: period, incident_count, observation_count, days_lost, ltifr, trir, man_hours_total, recordable_incidents, lost_time_incidents
   - SafetyTrendsExtendedResponse: period_type, entries[], rolling_12_month_ltifr, rolling_12_month_trir, current_period_ltifr, current_period_trir, trend_direction
   - SafetyThresholdAlertResponse: current_ltifr, current_trir, baseline_ltifr, baseline_trir, ltifr_delta, trir_delta, ltifr_status, trir_status, message

4. **Frontend: SafetyTrendsChart.tsx**
   - ComposedChart (Recharts) with dual Y-axes
   - Left: Incident count (BarChart, stacked)
   - Right: LTIFR/TRIR (LineChart, two lines)
   - Legend toggle, tooltip, loading/error states

5. **Frontend: SafetyThresholdWidget.tsx**
   - Compact status card: "LTIFR: 2.1 (Baseline: 2.5) Safe"
   - Green/yellow/red badge
   - Expandable to show delta, % above baseline, 3-month trend sparkline

6. **Integration: SafetyPage.tsx**
   - Add "Trends" tab
   - Render SafetyThresholdWidget + SafetyTrendsChart

**Out of scope (Phase 2):**
- Crew/department-level breakdown
- AI forecasting (ARIMA)
- PDF compliance export
- Root-cause correlation
- Multi-project comparison

---

## Backend (files, endpoints, models/DDL)

### Models — NO NEW TABLES

Existing SafetyIncident.metadata_ JSON column stores man_hours_total per incident. No migration required.

### Service layer (backend/app/modules/safety/service.py)

**New methods:**

1. sync def get_trends_extended(project_id: UUID, period: str = 'monthly') -> SafetyTrendsExtendedResponse
   - Fetch incidents + observations grouped by period
   - For each period: sum man_hours_total, count recordable/lost-time incidents, compute LTIFR/TRIR
   - Calculate rolling 12-month avg LTIFR/TRIR
   - Detect trend direction via 3-month slope analysis
   - Return SafetyTrendsExtendedResponse

2. sync def get_threshold_alert(project_id: UUID, baseline_ltifr: float = 2.5, baseline_trir: float = 3.0) -> SafetyThresholdAlertResponse
   - Call get_stats() to fetch current LTIFR/TRIR
   - Compare against baselines
   - Calculate deltas and status (green/yellow/red)
   - Return SafetyThresholdAlertResponse

3. _compute_trend_direction(entries: list[SafetyTrendEntryExtended]) -> str
   - Take last 3 periods' LTIFR values
   - Simple linear regression slope: improving (slope < -0.2), stable (-0.2 to 0.2), declining (>0.2), unknown (<3 periods)

### Schemas (backend/app/modules/safety/schemas.py)

Add at end of file:

`python
class SafetyTrendEntryExtended(BaseModel):
    period: str = Field(description="Period label, e.g., '2026-01'")
    incident_count: int = 0
    observation_count: int = 0
    days_lost: int = 0
    ltifr: float | None = None
    trir: float | None = None
    man_hours_total: float = 0.0
    recordable_incidents: int = 0
    lost_time_incidents: int = 0

class SafetyTrendsExtendedResponse(BaseModel):
    period_type: str
    entries: list[SafetyTrendEntryExtended] = Field(default_factory=list)
    rolling_12_month_ltifr: float | None = None
    rolling_12_month_trir: float | None = None
    current_period_ltifr: float | None = None
    current_period_trir: float | None = None
    trend_direction: str = Field(default="unknown", pattern=r"^(improving|stable|declining|unknown)$")

class SafetyThresholdAlertResponse(BaseModel):
    current_ltifr: float | None
    current_trir: float | None
    baseline_ltifr: float
    baseline_trir: float
    ltifr_delta: float | None = None
    trir_delta: float | None = None
    ltifr_status: str = Field(default="unknown", pattern=r"^(green|yellow|red|unknown)$")
    trir_status: str = Field(default="unknown", pattern=r"^(green|yellow|red|unknown)$")
    message: str = Field(default="")
`

### Router (backend/app/modules/safety/router.py)

Add before incident endpoints section:

`python
@router.get("/trends/extended", response_model=SafetyTrendsExtendedResponse)
async def safety_trends_extended(
    session: SessionDep,
    project_id: uuid.UUID = Query(...),
    period: str = Query(default="monthly", pattern=r"^(monthly|weekly)$"),
    user_id: CurrentUserId = None,
    _perm: None = Depends(RequirePermission("safety.read")),
    service: SafetyService = Depends(_get_service),
) -> SafetyTrendsExtendedResponse:
    """Return rolling 12-month LTIFR/TRIR time series and trend direction."""
    await verify_project_access(project_id, user_id, session)
    return await service.get_trends_extended(project_id, period=period)

@router.get("/threshold-alert", response_model=SafetyThresholdAlertResponse)
async def safety_threshold_alert(
    session: SessionDep,
    project_id: uuid.UUID = Query(...),
    baseline_ltifr: float = Query(default=2.5, ge=0.0),
    baseline_trir: float = Query(default=3.0, ge=0.0),
    user_id: CurrentUserId = None,
    _perm: None = Depends(RequirePermission("safety.read")),
    service: SafetyService = Depends(_get_service),
) -> SafetyThresholdAlertResponse:
    """Check current LTIFR/TRIR against threshold; return status."""
    await verify_project_access(project_id, user_id, session)
    return await service.get_threshold_alert(project_id, baseline_ltifr=baseline_ltifr, baseline_trir=baseline_trir)
`

---

## Frontend (route, components, UX)

### Route

Existing: /projects/:projectId/safety (SafetyPage.tsx) — no new routes

### New components (frontend/src/features/safety/)

1. **SafetyTrendsChart.tsx**
   - Props: projectId, period
   - Query: GET /v1/safety/trends/extended?project_id=...&period=...
   - Render: ComposedChart with dual Y-axes, legend toggle, tooltip, loading/error states

2. **SafetyThresholdWidget.tsx**
   - Props: projectId
   - Query: GET /v1/safety/threshold-alert?project_id=...
   - Render: Compact card (green/yellow/red), expandable to show delta and 3-month sparkline

3. **Integration into SafetyPage.tsx:**
   - Add "Trends" tab alongside Incidents/Observations
   - Render SafetyThresholdWidget + SafetyTrendsChart in Trends tab

---

## Migration DDL

**No new tables. No new columns.**

SafetyIncident.metadata_ JSON column is sufficient for man_hours_total.

---

## File touch list

**Own (safety module only):**
- backend/app/modules/safety/service.py
- backend/app/modules/safety/schemas.py
- backend/app/modules/safety/router.py
- frontend/src/features/safety/SafetyPage.tsx
- frontend/src/features/safety/SafetyTrendsChart.tsx (new)
- frontend/src/features/safety/SafetyThresholdWidget.tsx (new)
- frontend/src/features/safety/index.ts

**Overlaps with other waves:** None. Safety module is self-contained.

---

## TEST MATRIX (exhaustive concrete cases)

**Backend:**
- Happy path: 12 months → 12 entries with LTIFR calculated; rolling_12_month_ltifr non-null
- Rolling 12-month avg: [1.0, 2.0, 3.0, 2.5...] → rolling_12_month_ltifr ≈ 2.375
- Trend improving: [5.0, 3.0, 1.0] → 'improving'
- Trend declining: [1.0, 3.0, 5.0] → 'declining'
- Trend stable: [2.5, 2.5, 2.5] → 'stable'
- Trend unknown: only 1 month → 'unknown'
- Threshold green: LTIFR=2.0, baseline=2.5 → green
- Threshold yellow: LTIFR=3.1 (>120%) → yellow
- Threshold red: LTIFR=3.9 (>150%) → red
- Zero man-hours → LTIFR=None
- RBAC: no safety.read → 403
- RBAC: different project → 403
- Custom baseline → respects query param
- Negative man_hours → ignored
- Non-numeric man_hours → ignored (same as get_stats)

**Frontend:**
- Chart renders with data
- Legend toggle hides/shows series
- Period toggle switches monthly/weekly
- Tooltip shows correct values on hover
- Widget renders correct color badge (green/yellow/red)
- Widget expand shows delta, % above baseline, 3-month sparkline
- Loading state shows SkeletonTable
- Error state shows EmptyState with retry
- Empty data shows "No data available"

**E2E:**
- 12-month incident trend visible on Trends tab
- Threshold alert badge on dashboard
- Period toggle works
- Click incident bar navigates to detail (deferred)

---

## Sequencing / conflicts

**Zero conflicts.** Safety module self-contained.

- Additive endpoints, no breaking changes
- No dependency on other modules
- No database migrations required
- Can implement in parallel with other waves

**Integration points (Phase 2+):**
- Link to bi_dashboards for KPI dashboard
- Emit safety.threshold_alert_triggered event
- Email/Slack notifications

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|-----------|
| Man-hours data quality | Medium | High | Seed test fixture with man_hours. LTIFR/TRIR stays None if no data. |
| Calculation precision | Low | Medium | Round to 2 decimals. Test edge cases (very large/small numbers). |
| Performance (large incident sets) | Medium | Low | Cache trends response (5min TTL). Defer crew breakdown. |
| Trend heuristic ambiguity | Low | Low | 3-month slope may not capture real trends. UI caveat. |
| Threshold baselines too rigid | Medium | Low | Query params allow override. Phase 2 adds project settings. |
| Chart library quirks | Low | Low | Test Recharts dual-axis in staging. |

---

## Implementation checklist

**Backend:**
- [ ] Add SafetyTrendEntryExtended, SafetyTrendsExtendedResponse, SafetyThresholdAlertResponse to schemas.py
- [ ] Add get_trends_extended, get_threshold_alert, _compute_trend_direction to service.py
- [ ] Add /trends/extended, /threshold-alert endpoints to router.py
- [ ] Write backend tests (test_trends_extended.py)
- [ ] Seed fixture: 12 test incidents with varying man_hours_total and days_lost
- [ ] Verify get_stats unchanged (no regression)

**Frontend:**
- [ ] Create SafetyTrendsChart.tsx (ComposedChart, dual Y-axes)
- [ ] Create SafetyThresholdWidget.tsx (status card + expand)
- [ ] Integrate into SafetyPage.tsx (add Trends tab)
- [ ] Query setup: /v1/safety/trends/extended, /v1/safety/threshold-alert
- [ ] Write SafetyTrendsChart.test.tsx
- [ ] Write SafetyThresholdWidget.test.tsx
- [ ] E2E test: browser navigates to safety page, views Trends tab

**QA:**
- [ ] Browser-drive with 12 months of incidents
- [ ] Verify LTIFR/TRIR calculations match external tools (Excel, OSHA calc)
- [ ] Verify threshold alert triggers at correct percentages
- [ ] Performance: trends endpoint < 500ms
- [ ] Accessibility: readable in light/dark mode
- [ ] No regression on existing /stats, /trends endpoints

---

## Success criteria

1. Rolling 12-month LTIFR/TRIR calculated correctly
2. Threshold alert returns green/yellow/red status based on baselines
3. SafetyTrendsChart displays incidents + LTIFR/TRIR with legend/tooltip
4. SafetyThresholdWidget shows compact status + expandable detail
5. All test matrix cases pass
6. No regression on existing endpoints
7. Documentation: safety-trends.md added explaining LTIFR/TRIR, baseline, trend_direction
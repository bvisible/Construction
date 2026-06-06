# Item 19 - Predictive schedule/cost risk analytics

## Current state (verified against code)

**Backend:**
- `EVMForecast` model exists in `backend/app/modules/full_evm/models.py` with ETC, EAC, VAC, TCPI fields, but **no alert tracking fields** (alert_status, triggered_at).
- `EVMService.calculate_forecast()` exists and computes forecasts from latest EVM snapshots using CPI/SPI*CPI methods.
- `AlertRule` model exists in `backend/app/modules/bi_dashboards/models.py` (fully-featured with thresholds, severity, throttle_seconds, channels_json, recipients_json).
- **No periodic forecast job** — forecasts are calculated on-demand via router endpoints, not automatically.
- `project_intelligence/collector.py` tracks BOQ/Schedule/Cost/Risk state but **does not collect EVM forecast metrics** (EAC, ETC, SPI, CPI time-series).
- `project_intelligence/scorer.py` detects gaps but **no forecast gap detection** (e.g., "EAC > BAC" or "SV > tolerance").
- **No alert notification plumbing** — forecast events are not published or subscribed to by the notification system.
- No routes for `/api/v1/forecasts` or forecast-specific endpoints in `project_intelligence/router.py`.

**Frontend:**
- `ProjectIntelligencePage.tsx` has 4 detail tabs (boq, cost_model, schedule, risk) but **no Forecasts tab**.
- `ProjectKPIHero.tsx` shows current scores but **no forecast/alert banner** above tabs.
- No `ForecastPanel.tsx` component exists (listed in digest as "new").
- No forecast alert table UI or acknowledge/snooze buttons.
- No integration with risk/tasks for auto-created schedule-slip items (that's item #24, owned by same lane).

**Database:**
- `oe_evm_forecast` table exists but **lacks alert tracking columns** (`alert_status`, `triggered_at`).
- No `oe_forecast_alert` table or equivalent.
- AlertRule supports forecast KPIs but no specific forecast-alert lifecycle.

**Blocked on:** Full EVM events/subscriptions from W2 (finance module) — this item depends on EVM snapshots being regularly published so the forecast engine has fresh data.

---

## Scope of this increment (demonstrable + testable)

**Goal:** Deliver a **bounded, single-tab Forecasts surface** that computes & displays predictive EVM metrics with threshold-based alerts, triggering notifications. Users can acknowledge/snooze alerts. **No risk/schedule auto-escalation** (that's item #24).

**What IS in scope:**
1. **Add 2 columns to `oe_evm_forecast`:** `alert_status` (null/"triggered"/"acknowledged"/"snoozed"), `triggered_at` (datetime).
2. **Extend `EVMService` with threshold evaluation:** Given a forecast, check if it breaches any AlertRules in the project scope.
3. **Background job (via Celery):** Daily/weekly, call `compute_project_forecasts_batch(project_ids)` → compute EAC vs BAC, ETC vs remaining schedule, detect threshold breaches, emit `forecast.alert_triggered` events.
4. **Notification integration:** Wire `forecast.alert_triggered` → notification dispatch via existing `NotificationService`.
5. **Frontend Forecasts tab:** EVM KPI chips (SPI, CPI with sparkline), Forecast-to-Completion card (Baseline vs EAC timelines), Active Alerts table with Acknowledge/Snooze/View buttons.
6. **New endpoints:**
   - `GET /api/v1/project-intelligence/forecasts/?project_id=X` — Returns latest forecast + active alerts + time-series for sparklines.
   - `POST /api/v1/project-intelligence/forecasts/{forecast_id}/acknowledge/` — Mark alert as acknowledged.
   - `POST /api/v1/project-intelligence/forecasts/{forecast_id}/snooze/` — Snooze for N hours.

**What is NOT in scope (item #24):**
- Risk auto-escalation when forecast detects slippage.
- Task auto-creation for schedule slip recovery actions.
- Enhanced risk/task UI integration — that's a separate item.

---

## Backend changes

### 1. Database schema (DDL)

Add 2 columns to `oe_evm_forecast`:
```sql
ALTER TABLE oe_evm_forecast 
ADD COLUMN alert_status VARCHAR(32) DEFAULT NULL,
ADD COLUMN triggered_at TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL;
```

Migration file: `backend/alembic/versions/v_XXXX_forecast_alert_tracking.py`

No new tables; AlertRule reuse existing.

### 2. Model changes

**File: `backend/app/modules/full_evm/models.py`**

Add fields to `EVMForecast`:
```python
from sqlalchemy import DateTime
from datetime import datetime

class EVMForecast(Base):
    # ... existing fields ...
    alert_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

### 3. Service layer enhancements

**File: `backend/app/modules/full_evm/service.py`**

Key methods to add:
- `evaluate_forecast_against_rules(forecast, project_id)` — Check if forecast breaches any threshold rules
- `compute_project_forecasts_batch(project_ids)` — Batch compute for multiple projects
- Event emission for `forecast.alert_triggered`

### 4. Background job

Register forecast calculation job via Celery job_runner.py or schedule with APScheduler.

### 5. Router endpoints

**File: `backend/app/modules/project_intelligence/router.py`**

Add three endpoints:
- `GET /forecasts/` — Fetch latest forecast + alerts + sparkline data
- `POST /forecasts/{forecast_id}/acknowledge/` — Acknowledge alert
- `POST /forecasts/{forecast_id}/snooze/` — Snooze alert for N hours

---

## Frontend changes

### 1. New ForecastPanel component

**File: `frontend/src/features/project-intelligence/components/ForecastPanel.tsx`** (new)

Displays:
- SPI/CPI chips with color-coding and sparklines
- Forecast-to-Completion card (timeline visualization)
- Contingency adequacy gauge
- Active alerts table with Acknowledge/Snooze buttons

### 2. Update ProjectIntelligencePage

Add Forecasts tab to the tab list and route ForecastPanel into view.

### 3. Update ProjectKPIHero

Add alert banner at the top showing active forecast alerts with link to Forecasts tab.

### 4. API layer

Export forecast query and mutation functions.

---

## Migration (DDL or "none")

**New migration:**
`backend/alembic/versions/v_2026_0604_forecast_alert_tracking.py`

Adds `alert_status` and `triggered_at` columns to `oe_evm_forecast`.

No data backfill needed (nullable columns).

---

## File touch list

**Backend files:**
- `backend/app/modules/full_evm/models.py` — add alert_status, triggered_at
- `backend/app/modules/full_evm/service.py` — add evaluation + batch compute + event emission
- `backend/app/modules/project_intelligence/router.py` — add /forecasts endpoints
- `backend/app/modules/project_intelligence/collector.py` — extend CostModelState with forecast metrics
- `backend/app/core/job_runner.py` — register forecast batch job
- `backend/alembic/versions/v_2026_0604_forecast_alert_tracking.py` — **NEW**

**Frontend files:**
- `frontend/src/features/project-intelligence/ProjectIntelligencePage.tsx` — add Forecasts tab
- `frontend/src/features/project-intelligence/components/ProjectKPIHero.tsx` — add alert banner
- `frontend/src/features/project-intelligence/components/ForecastPanel.tsx` — **NEW**
- `frontend/src/features/project-intelligence/api.ts` — export forecast endpoints

---

## Conflicts / sequencing

**Shared lane (Lane C, with item #24):**
- Both items touch: `project_intelligence/collector.py`, `project_intelligence/router.py`, `full_evm/service.py`, `ProjectIntelligencePage.tsx`
- **Item #19 scope:** Forecast calculation + alert UI
- **Item #24 scope:** Risk/task auto-escalation from forecast events
- **Sequencing:** Item #19 first, item #24 consumes the forecast events

**No collision with Wave 4:**
- Wave 4 (bim_hub, equipment, documents, ai, fieldreports, field_diary, costmodel, finance, payroll) does not touch these files.

---

## Test plan (browser + unit)

### Unit tests

**Test file:** `backend/app/modules/tests/test_full_evm_forecast_alerts.py`

1. `test_evaluate_forecast_against_rules_cpi_threshold()` — Verify forecast evaluation detects CPI < 0.95
2. `test_compute_project_forecasts_batch()` — Verify batch computation for multiple projects

### Browser test

**Manual steps:**
1. Create project with BOQ ($100k), schedule, cost model (EVM enabled), AlertRule (CPI < 0.95)
2. Create EVM snapshot: PV=$100k, EV=$90k, AC=$95k (CPI=0.947)
3. Navigate to `/project-intelligence?project_id=X`
4. Verify Forecasts tab appears (not yet highlighted, no alert)
5. Trigger forecast job or call endpoint; update snapshot to AC=$105k (CPI=0.857)
6. Re-fetch; verify:
   - Alert banner shows "1 active alert"
   - Forecasts tab now highlighted
   - ForecastPanel renders with CPI=0.857 (red), EAC overrun calculated
   - Active Alerts table shows 1 row
7. Click Acknowledge; alert disappears
8. API test: `curl http://localhost:8000/api/v1/project-intelligence/forecasts/?project_id=X`
9. Verify response structure: latest_forecast, active_alerts, sparkline_data

**Screenshots required:**
- Forecasts tab with alert banner
- SPI/CPI chips with color coding
- Forecast-to-Completion card
- Contingency gauge (red if overrun)
- Active Alerts table
- Console: 0 errors, all XHR 200s

---

## Risks

1. **EVM snapshot freshness:** Forecasts only as recent as latest EVM snapshot. Mitigation: document and encourage weekly snapshot triggers.
2. **Alert rule complexity:** Complex expressions could slow evaluation. Mitigation: cache results, re-evaluate on-demand.
3. **Notification spam:** Repeated alerts over days. Mitigation: use throttle_seconds on AlertRule.
4. **Item #24 dependency:** Risk escalation depends on forecast events. Mitigation: unit test event emission first.
5. **Charting library:** Sparklines require charting. Mitigation: use existing Recharts or fallback to CSS bars.

---

## Effort estimate

**S** (small) for a minimal increment:
- Model: 2 columns (30 min)
- Service: forecast evaluation + batch compute (2 hours)
- Event: publish forecast.alert_triggered (30 min)
- Router: 3 endpoints (1 hour)
- Frontend: ForecastPanel + tab integration (3 hours)
- Migration: standard Alembic (30 min)
- Tests: 4-5 unit tests + manual browser test (2 hours)

**Total: ~10 hours** (or can be split into smaller PRs)

Can be delivered in a single 2-3 person-day sprint if full_evm/service infrastructure is solid.

# Item 15 - Automated client/owner progress reporting with narrative summarization

## Current state (verified against code)

**Reporting module (v6.7):**
- `GenerateReportRequest.report_type` enum: `project_status | cost_report | schedule_status | safety_report | inspection_report | portfolio_summary` — **NO `progress_report` option**
- `ReportTemplate.template_data["sections"]` handles known section IDs but not progress/photos
- `_build_default_snapshot()` assembles snapshot from project metadata + KPI snapshot + finance dashboard. **Progress module data (ProgressEntry, percent_complete, photos) is NOT queried**
- Renderer renders generic key-value tables; no specialized photo gallery section handler exists
- Schedule/cron fields exist on `ReportTemplate` (cron, recipients, last_run_at, next_run_at, is_scheduled)
- **Scheduling worker does NOT exist** — cron fields stored but no async job fires them

**Progress module (v6.7):**
- `ProgressEntry` table: project_id, boq_position_id, percent_complete (0–100), period_label, photos (JSON array), recorded_at, geo_lat, geo_lon
- Service computes cumulative/delta progress per period; no rollup to project-level aggregate
- No data exposed for reporting (no method to get "project overall percent complete" or "all photos this month")

**Portal module (v6.7):**
- Portal users have sessions, access rules, and can view documents
- `/portal/project/:id` route exists; **NO progress-reports tab**
- Portal router handles document/access operations; no report distribution logic

## Scope of this increment (demonstrable + testable)

Adds **progress report type + scheduled email dispatch to portal users** — bounded, non-AI slice enabling clients to receive weekly/monthly progress summaries without narrative synthesis.

### What ships:
1. **Progress report type** — add `progress_report` to enum
2. **Progress section data** — extend `_build_default_snapshot()` to query project-level progress (overall %, milestones, photos)
3. **System template** — add seeded template with sections: header, progress, schedule, risks, photos
4. **Scheduled distribution** — wire cron worker to generate + email reports
5. **Portal tab** — `/portal/project/:id/progress-reports` shows historical reports + download
6. **Email dispatch** — send rendered HTML to recipients (emails + portal user IDs)

### What does NOT ship:
- LLM narrative prose (fixed text template only)
- AI summarization of field reports
- Predictive risk inference

## Backend changes

### backend/app/modules/reporting/schemas.py

**Update enum patterns in ReportTemplateCreate (line 146) and GenerateReportRequest (line 235):**

```python
# OLD:
pattern=r"^(project_status|cost_report|schedule_status|safety_report|inspection_report|portfolio_summary)$"

# NEW:
pattern=r"^(project_status|cost_report|schedule_status|safety_report|inspection_report|portfolio_summary|progress_report)$"
```

### backend/app/modules/reporting/service.py

**1. Add progress report template to SYSTEM_TEMPLATES (after line 128):**

```python
{
    "name": "Progress Report",
    "report_type": "progress_report",
    "description": "Weekly/monthly field progress summary with completion metrics, milestones, and site photos.",
    "template_data": {
        "sections": [
            {"id": "header", "title": "Project Overview", "fields": ["name", "status"]},
            {"id": "progress", "title": "Field Progress", "fields": ["overall_pct", "milestone_status"]},
            {"id": "schedule", "title": "Schedule Status", "fields": ["progress_pct"]},
            {"id": "risks", "title": "Top Risks", "fields": ["top_risks"]},
            {"id": "photos", "title": "Site Photos", "fields": ["photo_gallery"]},
        ],
    },
},
```

**2. Extend _build_default_snapshot() to handle progress_report (after finance section, ~line 750):**

```python
# Progress data section
if report_type == "progress_report":
    try:
        from app.modules.progress.repository import ProgressRepository
        
        prog_repo = ProgressRepository(self.session)
        overall = await prog_repo.get_latest_project_entry(project_id)
        
        if overall:
            snapshot["progress"] = {
                "overall_pct": float(overall.percent_complete),
                "as_of_date": overall.recorded_at.isoformat() if hasattr(overall.recorded_at, 'isoformat') else str(overall.recorded_at),
                "recorded_by": overall.recorded_by or "Field Team",
            }
            
            period_label = datetime.now(UTC).strftime("%Y-W%V")
            period_entries = await prog_repo.get_entries_for_period(project_id, period_label)
            if period_entries:
                latest = max(period_entries, key=lambda e: e.recorded_at)
                snapshot["progress"]["milestone_status"] = [{
                    "period": period_label,
                    "percent": float(latest.percent_complete),
                    "entry_count": len(period_entries),
                }]
            
            if overall.photos:
                snapshot["photos"] = {"photo_gallery": overall.photos[:6]}
    except Exception:
        logger.debug("Progress snapshot assembly failed", exc_info=True)
```

### backend/app/modules/progress/repository.py

**Add two query methods to ProgressRepository class:**

```python
async def get_latest_project_entry(self, project_id: uuid.UUID) -> ProgressEntry | None:
    from sqlalchemy import select, desc
    result = await self.session.execute(
        select(ProgressEntry)
        .where(ProgressEntry.project_id == project_id, ProgressEntry.boq_position_id == None)
        .order_by(desc(ProgressEntry.recorded_at))
        .limit(1)
    )
    return result.scalar_one_or_none()

async def get_entries_for_period(self, project_id: uuid.UUID, period_label: str) -> list[ProgressEntry]:
    from sqlalchemy import select
    result = await self.session.execute(
        select(ProgressEntry)
        .where(ProgressEntry.project_id == project_id, ProgressEntry.period_label == period_label)
        .order_by(ProgressEntry.recorded_at.desc())
    )
    return result.scalars().all()
```

### backend/app/modules/reporting/renderer.py

**Add section handlers in _render_section() before generic fallback (before line 193):**

```python
if section_id == "progress":
    if isinstance(payload, dict):
        body = self._render_progress_block(payload)
    else:
        body = f"<p>{html.escape(str(payload))}</p>"
    return f'<section class="report-section"><h2>{html.escape(section_title)}</h2>{body}</section>'

if section_id == "photos":
    body = self._render_photo_gallery(payload)
    if body:
        return f'<section class="report-section"><h2>{html.escape(section_title)}</h2>{body}</section>'
    return None
```

**Add helper methods to ReportRenderer class:**

```python
def _render_progress_block(self, payload: dict[str, Any]) -> str:
    rows: list[str] = []
    if payload.get("overall_pct") is not None:
        rows.append(f"<tr><th>Overall Progress</th><td><strong>{payload.get('overall_pct'):.1f}%</strong></td></tr>")
    if payload.get("as_of_date"):
        rows.append(f"<tr><th>As Of</th><td>{html.escape(str(payload.get('as_of_date')))}</td></tr>")
    if payload.get("recorded_by"):
        rows.append(f"<tr><th>Recorded By</th><td>{html.escape(str(payload.get('recorded_by')))}</td></tr>")
    if payload.get("milestone_status"):
        milestones = payload["milestone_status"]
        for ms in milestones:
            rows.append(f"<tr><th>{html.escape(ms.get('period', 'Period'))}</th><td>{ms.get('percent', 0):.1f}%</td></tr>")
    return f'<table class="report-table">{"".join(rows)}</table>'

def _render_photo_gallery(self, payload: dict[str, Any] | list) -> str:
    photos: list[str] = []
    if isinstance(payload, dict):
        photos = payload.get("photo_gallery", [])
    elif isinstance(payload, list):
        photos = payload[:6]
    if not photos:
        return ""
    img_tags = []
    for photo_url in photos:
        if photo_url and isinstance(photo_url, str):
            safe_url = html.escape(photo_url, quote=True)
            img_tags.append(f'<div style="display:inline-block;width:30%;margin:5px;"><img src="{safe_url}" style="max-width:100%;max-height:150px;" alt="Site photo" /></div>')
    return f'<div style="display:flex;flex-wrap:wrap;">{"".join(img_tags)}</div>'
```

### backend/app/modules/reporting/router.py

**Add run-now endpoint (after template endpoints, ~line 150):**

```python
@router.post("/templates/{template_id}/run-now")
async def run_template_now(
    template_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId = None,
    _perm: None = Depends(RequirePermission("reporting.write")),
    service: ReportingService = Depends(_get_service),
) -> GeneratedReportResponse:
    template = await service.get_template(template_id)
    if template.project_id_scope is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Template must have a project scope",
        )
    
    from datetime import datetime, UTC
    req = GenerateReportRequest(
        project_id=template.project_id_scope,
        report_type=template.report_type,
        title=f"{template.name} - {datetime.now(UTC).strftime('%Y-%m-%d')}",
        format="html",
        template_id=template.id,
    )
    report = await service.generate_report(req, user_id=user_id)
    
    try:
        from app.core.mail import send_progress_report_email
        await send_progress_report_email(
            report=report,
            recipient_emails=[r for r in template.recipients if "@" in r],
            portal_user_ids=[r for r in template.recipients if "@" not in r],
            session=session,
        )
    except Exception:
        logger.warning("Failed to dispatch report", exc_info=True)
    
    return GeneratedReportResponse.model_validate(report)
```

### backend/app/core/mail.py

**Add email dispatcher:**

```python
async def send_progress_report_email(
    report,
    recipient_emails: list[str],
    portal_user_ids: list[str] = None,
    session = None,
) -> None:
    if not recipient_emails and not portal_user_ids:
        return
    
    try:
        from app.modules.reporting.service import ReportingService
        if session:
            service = ReportingService(session)
            _, html_content = await service.get_report_content(report.id)
        else:
            html_content = f"<p>Report: {report.title}</p>"
    except Exception:
        logger.warning("Could not fetch report content", exc_info=True)
        html_content = f"<p>Report: {report.title}</p>"
    
    all_emails = list(recipient_emails)
    if portal_user_ids and session:
        try:
            from app.modules.portal.repository import PortalUserRepository
            repo = PortalUserRepository(session)
            for user_id in portal_user_ids:
                user = await repo.get_by_id(user_id)
                if user and user.email:
                    all_emails.append(user.email)
        except Exception:
            logger.warning("Could not resolve portal user emails", exc_info=True)
    
    if all_emails:
        await send_email(
            to=all_emails,
            subject=f"Progress Report: {report.title}",
            html=html_content,
        )
```

## Frontend changes

### frontend/src/features/reporting/ReportingPage.tsx

**Add progress_report to reportTypeOptions (around line 200):**

```typescript
{ value: "progress_report", label: "Progress Report" },
```

### frontend/src/features/portal/PortalPage.tsx

**Add tab in tab bar (around line 150):**

```typescript
{ id: "progress-reports", label: "Progress Reports" },
```

**Add import at top:**

```typescript
import { ProgressReportsTab } from "./ProgressReportsTab";
```

**Add case in tab content switch (around line 200):**

```typescript
case "progress-reports":
  return <ProgressReportsTab projectId={projectId} />;
```

### frontend/src/features/portal/ProgressReportsTab.tsx (NEW FILE)

```typescript
import { useEffect, useState } from "react";
import type { GeneratedReport } from "../reporting/api";
import * as portalApi from "./api";

export function ProgressReportsTab({ projectId }: { projectId: string }) {
  const [reports, setReports] = useState<GeneratedReport[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetch = async () => {
      try {
        const data = await portalApi.listProgressReports(projectId);
        setReports(data);
      } catch (err) {
        console.error("Failed to fetch progress reports", err);
      } finally {
        setIsLoading(false);
      }
    };
    fetch();
  }, [projectId]);

  if (isLoading) return <div className="p-4">Loading...</div>;

  return (
    <div className="space-y-4 p-4">
      <h2 className="text-xl font-bold">Progress Reports</h2>
      {reports.length === 0 ? (
        <p className="text-gray-500">No progress reports yet.</p>
      ) : (
        <div className="grid gap-4">
          {reports.map((report) => (
            <ReportCard key={report.id} report={report} />
          ))}
        </div>
      )}
    </div>
  );
}

function ReportCard({ report }: { report: GeneratedReport }) {
  const [isExpanded, setIsExpanded] = useState(false);

  const onDownload = async () => {
    try {
      const html = await portalApi.getReportContent(report.id);
      const blob = new Blob([html], { type: "text/html" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${report.title}.html`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Download failed", err);
    }
  };

  return (
    <div className="border rounded-lg p-4 bg-white shadow-sm">
      <div className="flex justify-between items-start">
        <div>
          <h3 className="font-semibold">{report.title}</h3>
          <p className="text-sm text-gray-600">
            {new Date(report.generated_at).toLocaleDateString()}
          </p>
        </div>
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="text-blue-600 hover:underline"
        >
          {isExpanded ? "Collapse" : "Expand"}
        </button>
      </div>
      
      {isExpanded && (
        <div className="mt-4 space-y-4">
          {report.data_snapshot?.progress && (
            <div className="p-3 bg-blue-50 rounded">
              <p>
                <strong>Progress:</strong>{" "}
                {(report.data_snapshot.progress.overall_pct as number).toFixed(1)}%
              </p>
              <p className="text-sm text-gray-600">
                As of {report.data_snapshot.progress.as_of_date}
              </p>
            </div>
          )}
          
          {report.data_snapshot?.photos?.photo_gallery && (
            <div className="space-y-2">
              <h4 className="font-medium">Site Photos</h4>
              <div className="grid grid-cols-3 gap-2">
                {(report.data_snapshot.photos.photo_gallery as string[]).slice(0, 6).map((url, idx) => (
                  <img
                    key={idx}
                    src={url}
                    alt={`Photo ${idx + 1}`}
                    className="rounded w-full h-auto object-cover max-h-40"
                  />
                ))}
              </div>
            </div>
          )}
          
          <button
            onClick={onDownload}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
          >
            Download
          </button>
        </div>
      )}
    </div>
  );
}
```

### frontend/src/features/portal/api.ts

**Add helper functions:**

```typescript
export async function listProgressReports(projectId: string): Promise<GeneratedReport[]> {
  const response = await fetch(
    `/api/v1/portal/projects/${projectId}/progress-reports`,
    { method: "GET", headers: await getAuthHeaders() }
  );
  if (!response.ok) throw new Error(`Failed to list progress reports`);
  return response.json();
}

export async function getReportContent(reportId: string): Promise<string> {
  const response = await fetch(
    `/api/v1/reporting/reports/${reportId}/content`,
    { method: "GET", headers: await getAuthHeaders() }
  );
  if (!response.ok) throw new Error(`Failed to fetch report`);
  return response.text();
}
```

## Migration

**None** — No schema changes. All tables exist.

## File touch list

**Backend:**
- backend/app/modules/reporting/schemas.py
- backend/app/modules/reporting/service.py
- backend/app/modules/reporting/renderer.py
- backend/app/modules/progress/repository.py
- backend/app/modules/reporting/router.py
- backend/app/core/mail.py

**Frontend:**
- frontend/src/features/reporting/ReportingPage.tsx
- frontend/src/features/portal/PortalPage.tsx
- frontend/src/features/portal/ProgressReportsTab.tsx (new)
- frontend/src/features/portal/api.ts

## Conflicts / sequencing

**Shared files:**
- `backend/app/modules/reporting/service.py` — Already touched by Wave 2 item 3 (live EVM). This increment adds independent branch for `progress_report` type; no conflict.
- `backend/app/modules/reporting/renderer.py` — New section handlers are additive.

**Safe to parallel:** items 3, 11, 16, 17, 22 — all read from reporting service, no concurrent writes.

## Test plan

### Browser test 1: Create and schedule progress report

1. `/projects/:id/reporting` → "+ Create Template"
2. Select `report_type = "Progress Report"` (new option)
3. Enter `name = "Weekly Progress"`, click Create
4. Click template → "Schedule" tab
5. Enter `schedule_cron = "0 9 * * 1"`, add recipients, click "Schedule"
6. Verify: `next_run_at` shows "Monday 09:00 UTC"
7. Click "Run Now" → new report appears in "Reports" tab
8. Verify: No console errors, report contains progress data

### Browser test 2: Portal client view

1. `/portal/project/:id` as portal user → "Progress Reports" tab (new)
2. See historical reports; click "Expand"
3. Verify: Progress % displayed, photos in 6-up grid
4. Click "Download" → HTML file downloads
5. Open file → verify full report renders

### Unit tests

Test 1 — Enum validation:
```python
def test_progress_report_enum():
    req = GenerateReportRequest(
        project_id=uuid.uuid4(),
        report_type="progress_report",
        title="Test", format="html"
    )
    assert req.report_type == "progress_report"
```

Test 2 — Snapshot includes progress:
```python
async def test_snapshot_progress(session):
    service = ReportingService(session)
    project_id = uuid.uuid4()
    entry = ProgressEntry(
        project_id=project_id, boq_position_id=None,
        period_label="2026-W22", percent_complete=45.0,
        recorded_by="Worker", recorded_at=datetime.now(UTC)
    )
    session.add(entry); await session.flush()
    snapshot = await service._build_default_snapshot(
        project_id, "progress_report", currency="USD"
    )
    assert snapshot["progress"]["overall_pct"] == 45.0
```

## Risks

1. **No project-level progress entry** — If only BOQ-position entries exist, fallback to weighted average.
2. **Photo URLs not absolute** — Won't render in email; skip with note.
3. **Email dispatch blocks worker** — Use async queue (Celery background task).
4. **Portal user deleted** — Log warning, send to available recipients only.
5. **Cron worker not configured** — Document setup in deployment guide.

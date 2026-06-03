"""‌⁠‍Reporting service — business logic for KPI snapshots, templates, and report generation.

Event publishing (slice E):
    reporting.kpi_snapshot.created — new KPI snapshot row
    reporting.template.created     — new custom template
    reporting.template.scheduled   — cron schedule attached/cleared
    reporting.report.generated     — new report rendered
"""

import logging
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import event_bus
from app.modules.reporting.cron import CronParseError, next_occurrence
from app.modules.reporting.currency_resolver import resolve_template_currency
from app.modules.reporting.models import GeneratedReport, KPISnapshot, ReportTemplate
from app.modules.reporting.renderer import ReportRenderer
from app.modules.reporting.repository import (
    GeneratedReportRepository,
    KPISnapshotRepository,
    ReportTemplateRepository,
)
from app.modules.reporting.schemas import (
    GenerateReportRequest,
    KPISnapshotCreate,
    ReportScheduleRequest,
    ReportTemplateCreate,
)

logger = logging.getLogger(__name__)
_logger_ev = logging.getLogger(__name__ + ".events")


async def _safe_publish(name: str, data: dict, source_module: str = "oe_reporting") -> None:
    """‌⁠‍Best-effort event publish — never blocks the caller on failure."""
    try:
        event_bus.publish_detached(name, data, source_module=source_module)
    except Exception:
        _logger_ev.debug("Event publish skipped: %s", name)


# ── System report templates (seeded on first startup) ──────────────────────

SYSTEM_TEMPLATES: list[dict] = [
    {
        "name": "Project Status Report",
        "report_type": "project_status",
        "description": "Comprehensive project status overview with KPIs, schedule, budget, and risk summary.",
        "template_data": {
            "sections": [
                {"id": "header", "title": "Project Overview", "fields": ["name", "status", "dates"]},
                {"id": "kpi", "title": "Key Performance Indicators", "fields": ["cpi", "spi", "budget_consumed_pct"]},
                {"id": "schedule", "title": "Schedule Status", "fields": ["progress_pct", "milestones"]},
                {"id": "risk", "title": "Risk Summary", "fields": ["risk_score_avg", "top_risks"]},
                {"id": "issues", "title": "Open Issues", "fields": ["defects", "observations", "rfis"]},
            ],
        },
    },
    {
        "name": "Cost Report",
        "report_type": "cost_report",
        "description": "Detailed cost breakdown by trade, element, and cost group with budget vs. actual comparison.",
        "template_data": {
            "sections": [
                {"id": "summary", "title": "Cost Summary", "fields": ["budget", "committed", "forecast"]},
                {"id": "breakdown", "title": "Cost Breakdown", "fields": ["by_trade", "by_element"]},
                {"id": "changes", "title": "Change Orders", "fields": ["approved", "pending", "rejected"]},
                {"id": "cashflow", "title": "Cash Flow", "fields": ["monthly_actual", "monthly_forecast"]},
            ],
        },
    },
    {
        "name": "Schedule Status Report",
        "report_type": "schedule_status",
        "description": "Schedule performance with milestone tracking, critical path, and lookahead.",
        "template_data": {
            "sections": [
                {"id": "overview", "title": "Schedule Overview", "fields": ["spi", "progress_pct"]},
                {"id": "milestones", "title": "Milestone Status", "fields": ["upcoming", "overdue"]},
                {"id": "critical", "title": "Critical Path", "fields": ["critical_activities"]},
                {"id": "lookahead", "title": "3-Week Lookahead", "fields": ["planned_activities"]},
            ],
        },
    },
    {
        "name": "Safety Report",
        "report_type": "safety_report",
        "description": "Safety incident summary, near-miss tracking, and safety KPIs.",
        "template_data": {
            "sections": [
                {"id": "kpi", "title": "Safety KPIs", "fields": ["ltifr", "trifr", "days_without_incident"]},
                {"id": "incidents", "title": "Incident Log", "fields": ["recent_incidents"]},
                {"id": "near_miss", "title": "Near-Miss Reports", "fields": ["recent_near_misses"]},
                {"id": "training", "title": "Safety Training", "fields": ["completed", "upcoming"]},
            ],
        },
    },
    {
        "name": "Inspection Report",
        "report_type": "inspection_report",
        "description": "Quality inspection results with pass/fail statistics and punch list status.",
        "template_data": {
            "sections": [
                {"id": "summary", "title": "Inspection Summary", "fields": ["total", "passed", "failed"]},
                {"id": "by_type", "title": "By Inspection Type", "fields": ["type_breakdown"]},
                {"id": "punchlist", "title": "Punch List Status", "fields": ["open", "closed", "overdue"]},
                {"id": "details", "title": "Recent Inspections", "fields": ["recent_list"]},
            ],
        },
    },
    {
        "name": "Portfolio Summary",
        "report_type": "portfolio_summary",
        "description": "Multi-project portfolio dashboard with aggregated KPIs and project comparison.",
        "template_data": {
            "sections": [
                {"id": "overview", "title": "Portfolio Overview", "fields": ["project_count", "total_budget"]},
                {"id": "status", "title": "Project Statuses", "fields": ["by_status", "by_health"]},
                {"id": "kpi_comparison", "title": "KPI Comparison", "fields": ["cpi_table", "spi_table"]},
                {"id": "risks", "title": "Portfolio Risks", "fields": ["top_risks_across"]},
            ],
        },
    },
]


class ReportingService:
    """‌⁠‍Business logic for reporting operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.kpi_repo = KPISnapshotRepository(session)
        self.template_repo = ReportTemplateRepository(session)
        self.report_repo = GeneratedReportRepository(session)

    # ── KPI Snapshots ─────────────────────────────────────────────────────

    async def get_latest_kpi(self, project_id: uuid.UUID) -> KPISnapshot | None:
        """Get the most recent KPI snapshot for a project."""
        return await self.kpi_repo.get_latest(project_id)

    async def list_kpi_history(
        self,
        project_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[KPISnapshot], int]:
        """List KPI snapshots for a project."""
        return await self.kpi_repo.list_history(project_id, offset=offset, limit=limit)

    async def create_kpi_snapshot(
        self,
        data: KPISnapshotCreate,
        user_id: str | None = None,
    ) -> KPISnapshot:
        """Create (or upsert) a KPI snapshot for a project + date.

        ``oe_reporting_kpi_snapshot`` has a UNIQUE(project_id,
        snapshot_date) constraint: a project has exactly one snapshot per
        day. A blind INSERT on a date that already had a snapshot raised an
        unhandled ``IntegrityError`` → 500. We upsert instead — the same
        date-idempotent behaviour ``auto_recalculate_kpis`` already
        implements — so re-posting a day's KPIs updates that day's row.
        """
        from sqlalchemy import select

        existing = (
            await self.session.execute(
                select(KPISnapshot).where(
                    KPISnapshot.project_id == data.project_id,
                    KPISnapshot.snapshot_date == data.snapshot_date,
                )
            )
        ).scalar_one_or_none()

        if existing is not None:
            existing.cpi = data.cpi
            existing.spi = data.spi
            existing.budget_consumed_pct = data.budget_consumed_pct
            existing.open_defects = data.open_defects
            existing.open_observations = data.open_observations
            existing.schedule_progress_pct = data.schedule_progress_pct
            existing.open_rfis = data.open_rfis
            existing.open_submittals = data.open_submittals
            existing.risk_score_avg = data.risk_score_avg
            existing.metadata_ = data.metadata
            await self.session.flush()
            snapshot = existing
        else:
            snapshot = KPISnapshot(
                project_id=data.project_id,
                snapshot_date=data.snapshot_date,
                cpi=data.cpi,
                spi=data.spi,
                budget_consumed_pct=data.budget_consumed_pct,
                open_defects=data.open_defects,
                open_observations=data.open_observations,
                schedule_progress_pct=data.schedule_progress_pct,
                open_rfis=data.open_rfis,
                open_submittals=data.open_submittals,
                risk_score_avg=data.risk_score_avg,
                metadata_=data.metadata,
            )
            snapshot = await self.kpi_repo.create(snapshot)

        # The upsert flush expires the instance's attributes; refresh before
        # the event payload reads them and the router serializes the snapshot,
        # otherwise asyncpg emits a sync lazy reload outside the greenlet.
        await self.session.refresh(snapshot)

        await _safe_publish(
            "reporting.kpi_snapshot.created",
            {
                "snapshot_id": str(snapshot.id),
                "project_id": str(snapshot.project_id),
                "snapshot_date": snapshot.snapshot_date,
                "cpi": snapshot.cpi,
                "spi": snapshot.spi,
            },
        )

        logger.info(
            "KPI snapshot created for project %s date %s",
            data.project_id,
            data.snapshot_date,
        )
        return snapshot

    # ── Report Templates ──────────────────────────────────────────────────

    async def list_templates(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[ReportTemplate], int]:
        """List all report templates."""
        return await self.template_repo.list_all(offset=offset, limit=limit)

    async def create_template(
        self,
        data: ReportTemplateCreate,
        user_id: str | None = None,
    ) -> ReportTemplate:
        """Create a custom report template."""
        template = ReportTemplate(
            name=data.name,
            name_translations=data.name_translations,
            report_type=data.report_type,
            description=data.description,
            template_data=data.template_data,
            is_system=False,
            created_by=uuid.UUID(user_id) if user_id else None,
            metadata_=data.metadata,
        )
        template = await self.template_repo.create(template)

        await _safe_publish(
            "reporting.template.created",
            {
                "template_id": str(template.id),
                "name": template.name,
                "report_type": template.report_type,
                "is_system": False,
                "created_by": user_id,
            },
        )

        logger.info("Report template created: %s (%s)", data.name, data.report_type)
        return template

    async def get_template(self, template_id: uuid.UUID) -> ReportTemplate:
        """Fetch a template or raise 404."""
        template = await self.template_repo.get_by_id(template_id)
        if template is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Report template not found",
            )
        return template

    # ── Scheduling (v2.3.0) ───────────────────────────────────────────────

    async def schedule_template(
        self,
        template_id: uuid.UUID,
        data: ReportScheduleRequest,
    ) -> ReportTemplate:
        """Attach/replace/clear a cron schedule on a template.

        Passing ``schedule_cron=None`` clears scheduling (and also clears
        ``next_run_at``). Otherwise the cron is parsed, the next run is
        computed from ``now`` in UTC, and persisted.
        """
        template = await self.get_template(template_id)

        template.recipients = list(data.recipients)
        template.project_id_scope = data.project_id_scope

        if data.schedule_cron is None:
            template.schedule_cron = None
            template.next_run_at = None
            template.is_scheduled = False
        else:
            try:
                next_run = next_occurrence(
                    data.schedule_cron,
                    datetime.now(UTC),
                )
            except CronParseError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid cron expression: {exc}",
                ) from exc
            template.schedule_cron = data.schedule_cron
            template.next_run_at = next_run.strftime("%Y-%m-%dT%H:%M:%SZ")
            template.is_scheduled = data.is_scheduled

        await self.template_repo.update(template)

        await _safe_publish(
            "reporting.template.scheduled",
            {
                "template_id": str(template.id),
                "schedule_cron": template.schedule_cron,
                "is_scheduled": template.is_scheduled,
                "next_run_at": template.next_run_at,
                "project_id_scope": (str(template.project_id_scope) if template.project_id_scope else None),
            },
        )

        logger.info(
            "Report template %s scheduled: cron=%r is_scheduled=%s next_run=%s",
            template.id,
            template.schedule_cron,
            template.is_scheduled,
            template.next_run_at,
        )
        return template

    async def list_due_templates(self, as_of: datetime | None = None) -> list[ReportTemplate]:
        """List scheduled templates whose next_run_at has arrived.

        Used by the Celery-Beat worker. Accepts an optional ``as_of``
        datetime (UTC) for tests; defaults to now.
        """
        if as_of is None:
            as_of = datetime.now(UTC)
        as_of_iso = as_of.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        return await self.template_repo.list_due(as_of_iso)

    async def list_scheduled_templates(self) -> list[ReportTemplate]:
        """List every template that has a cron expression set."""
        return await self.template_repo.list_scheduled()

    async def mark_template_ran(
        self,
        template: ReportTemplate,
        *,
        ran_at: datetime | None = None,
    ) -> ReportTemplate:
        """Advance a template after a successful worker run.

        Records ``last_run_at`` and recomputes ``next_run_at`` using the
        stored cron expression. If the cron expression is no longer valid
        or scheduling was paused, ``next_run_at`` is cleared so the
        worker won't pick it up again.
        """
        if ran_at is None:
            ran_at = datetime.now(UTC)
        ran_at = ran_at.astimezone(UTC)
        template.last_run_at = ran_at.strftime("%Y-%m-%dT%H:%M:%SZ")

        if not template.is_scheduled or not template.schedule_cron:
            template.next_run_at = None
        else:
            try:
                next_run = next_occurrence(template.schedule_cron, ran_at)
                template.next_run_at = next_run.strftime("%Y-%m-%dT%H:%M:%SZ")
            except CronParseError:
                logger.exception(
                    "Template %s has invalid cron %r — pausing",
                    template.id,
                    template.schedule_cron,
                )
                template.next_run_at = None
                template.is_scheduled = False

        await self.template_repo.update(template)
        return template

    # ── Generated Reports ─────────────────────────────────────────────────

    async def list_reports(
        self,
        project_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[GeneratedReport], int]:
        """List generated reports for a project."""
        return await self.report_repo.list_for_project(
            project_id,
            offset=offset,
            limit=limit,
        )

    async def get_report(self, report_id: uuid.UUID) -> GeneratedReport:
        """Get a generated report by ID. Raises 404 if not found."""
        report = await self.report_repo.get_by_id(report_id)
        if report is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Report not found",
            )
        return report

    async def delete_report(self, report_id: uuid.UUID) -> None:
        """Hard-delete a generated report. 404 if not found.

        Caller is expected to enforce project access via
        ``verify_project_access`` before invoking this — the service layer
        does not gate on the user's project ownership.
        """
        report = await self.report_repo.get_by_id(report_id)
        if report is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Report not found",
            )
        await self.session.delete(report)
        await self.session.flush()

    async def generate_report(
        self,
        data: GenerateReportRequest,
        user_id: str | None = None,
    ) -> GeneratedReport:
        """Generate a new report.

        After the metadata row is persisted we render the report body via
        :class:`ReportRenderer` and store the resulting HTML through the
        global storage backend, recording its key on ``report.storage_key``
        so the ``/reports/{id}/content`` endpoint can fetch it back. Before
        this wiring landed (W23 P0 audit, task #252) the row existed but
        ``storage_key`` was always ``None`` — clicking the report in the
        history panel showed nothing because there was nothing to show.

        Rendering and storage failures are best-effort: we log them and
        leave ``storage_key`` as ``None`` rather than rejecting the whole
        call. This matches the cron-worker contract (a failed render
        should not lose the audit trail of "we tried to render").
        """
        # ── Resolve the report currency (override > project > EUR) ──
        # Worldwide currency parameterisation (Wave 23). The resolved code
        # is stamped onto the row *and* into the data_snapshot so every
        # money figure in the report reads in a single, explicit currency.
        # ``override_currency`` is already shape-validated (3-letter, upper)
        # at the schema layer, so an invalid code never reaches here — it
        # is rejected with HTTP 422 before this method runs.
        currency = await resolve_template_currency(
            session=self.session,
            project_id=data.project_id,
            override_currency=data.override_currency,
        )

        # If the caller did not supply a data snapshot, assemble one
        # server-side from the project's live module state. Without this
        # the renderer falls straight through to its "No data available"
        # notice and every report a user generates is a blank shell — the
        # only generation path the UI exposes never sends a snapshot
        # (W2 audit, /reporting). Best-effort: a failure here degrades to
        # the empty-snapshot notice rather than failing the whole call.
        effective_snapshot = data.data_snapshot
        if effective_snapshot is None:
            try:
                effective_snapshot = await self._build_default_snapshot(
                    data.project_id,
                    data.report_type,
                    currency=currency,
                )
            except Exception:
                logger.warning(
                    "reporting.generate_report could not assemble a default "
                    "data_snapshot for project_id=%s; the report will render "
                    "the empty-snapshot notice.",
                    data.project_id,
                    exc_info=True,
                )
                effective_snapshot = None

        # Stamp the resolved currency into the snapshot. A caller-supplied
        # snapshot is copied (never mutated in place) so the request object
        # stays pristine, and the stamped ``currency`` key always reflects
        # the resolved code — overriding any stale currency the caller may
        # have embedded. This is what guarantees a USD report never carries
        # a euro sign and vice versa: money lives under one currency code.
        if effective_snapshot is not None:
            effective_snapshot = {**effective_snapshot, "currency": currency}
        else:
            effective_snapshot = {"currency": currency}

        report = GeneratedReport(
            project_id=data.project_id,
            template_id=data.template_id,
            report_type=data.report_type,
            title=data.title,
            generated_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S"),
            generated_by=uuid.UUID(user_id) if user_id else None,
            format=data.format,
            currency=currency,
            data_snapshot=effective_snapshot,
            metadata_=data.metadata,
        )
        report = await self.report_repo.create(report)

        # Best-effort render-and-store. Wrapped in try/except so a missing
        # storage backend (e.g. unit tests with a stub service) or a
        # renderer regression cannot prevent the metadata row from being
        # returned to the caller.
        try:
            template_data: dict | None = None
            if data.template_id is not None:
                template = await self.template_repo.get_by_id(data.template_id)
                if template is not None:
                    template_data = template.template_data

            project_name = await self._lookup_project_name(data.project_id)

            renderer = ReportRenderer()
            rendered_html = renderer.render_html(
                report_type=data.report_type,
                title=data.title,
                project_name=project_name,
                template_data=template_data,
                data_snapshot=effective_snapshot,
                generated_at=report.generated_at,
            )

            storage_key = f"reports/{report.project_id}/{report.id}.html"
            try:
                from app.core.storage import get_storage_backend

                backend = get_storage_backend()
                await backend.put(storage_key, rendered_html.encode("utf-8"))
                report.storage_key = storage_key
                await self.report_repo.update(report)
            except Exception:
                logger.warning(
                    "Report storage backend put failed for report_id=%s; "
                    "the metadata row is preserved but storage_key remains null.",
                    report.id,
                    exc_info=True,
                )
        except Exception:
            logger.warning(
                "Report rendering failed for report_id=%s; the metadata row is preserved but storage_key remains null.",
                report.id,
                exc_info=True,
            )

        await _safe_publish(
            "reporting.report.generated",
            {
                "report_id": str(report.id),
                "project_id": str(report.project_id),
                "report_type": report.report_type,
                "format": report.format,
                "template_id": (str(report.template_id) if report.template_id else None),
                "generated_by": user_id,
                "storage_key": report.storage_key,
            },
        )

        logger.info(
            "Report generated: %s (%s) for project %s",
            data.title,
            data.report_type,
            data.project_id,
        )
        return report

    async def get_report_content(self, report_id: uuid.UUID) -> tuple[GeneratedReport, str]:
        """Fetch a rendered report's HTML body.

        Returns ``(report, html_string)``. Raises 404 if the report is
        unknown or 410 (Gone) if the metadata row exists but the rendered
        body is no longer reachable from the storage backend — a clearer
        signal than blank 200 OK.
        """
        report = await self.get_report(report_id)
        if not report.storage_key:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Report body has not been rendered yet",
            )

        try:
            from app.core.storage import get_storage_backend

            backend = get_storage_backend()
            blob = await backend.get(report.storage_key)
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Rendered report body was removed from storage",
            ) from exc
        return report, blob.decode("utf-8")

    async def _lookup_project_name(self, project_id: uuid.UUID) -> str:
        """Best-effort lookup of a project's display name for the report header.

        Falls back to the stringified UUID on any failure so a transient
        DB error doesn't sabotage the whole render pipeline.
        """
        try:
            from app.modules.projects.repository import ProjectRepository

            project = await ProjectRepository(self.session).get_by_id(project_id)
            if project is not None and getattr(project, "name", None):
                return str(project.name)
        except Exception:
            logger.debug(
                "Could not resolve project name for report; falling back to UUID",
                exc_info=True,
            )
        return str(project_id)

    async def _build_default_snapshot(
        self,
        project_id: uuid.UUID,
        report_type: str,
        *,
        currency: str,
    ) -> dict | None:
        """Assemble a ``data_snapshot`` from the project's live module state.

        Used when ``generate_report`` is called without an explicit
        snapshot (the only path the /reporting UI exercises). Returns a
        dict keyed by the renderer's section IDs (``header``, ``kpi``,
        ``schedule``, ``risk``, ``issues``, ``summary``, ``cashflow`` …)
        so the body actually contains numbers instead of the
        "No data available" notice.

        Every figure is sourced from data the dashboards already compute:
        the most recent :class:`KPISnapshot` (CPI/SPI/budget/schedule/risk
        and open-item counts) plus the finance dashboard (payable /
        receivable / budget / cash-flow). Money values always carry the
        report's *resolved* currency code (``currency`` arg) so the whole
        report reads in one currency — we never blend the finance
        dashboard's own currency with the resolved report currency.

        Args:
            project_id: Owning project UUID.
            report_type: Report type (forward-compat; not branched on yet).
            currency: The already-resolved ISO 4217 code for this report
                (override > project > EUR). All money figures are stamped
                with this single code.

        Returns ``None`` when neither a KPI snapshot nor finance data is
        available, so the caller still gets the explicit empty-snapshot
        notice rather than a misleading half-empty report.
        """
        from app.modules.projects.repository import ProjectRepository

        snapshot: dict[str, dict] = {}

        # ── Project header ──
        project = None
        try:
            project = await ProjectRepository(self.session).get_by_id(project_id)
        except Exception:
            project = None
        if project is not None:
            header: dict[str, object] = {
                "name": getattr(project, "name", "") or "",
                "status": getattr(project, "status", "") or "",
            }
            if getattr(project, "phase", None):
                header["phase"] = project.phase
            if getattr(project, "planned_start_date", None):
                header["planned_start"] = project.planned_start_date
            if getattr(project, "planned_end_date", None):
                header["planned_end"] = project.planned_end_date
            snapshot["header"] = header
            snapshot["overview"] = dict(header)

        # ── KPI snapshot → kpi / schedule / risk / issues sections ──
        kpi = await self.get_latest_kpi(project_id)
        if kpi is not None:
            kpi_block: dict[str, object] = {}
            if kpi.cpi is not None:
                kpi_block["cpi"] = kpi.cpi
            if kpi.spi is not None:
                kpi_block["spi"] = kpi.spi
            if kpi.budget_consumed_pct is not None:
                kpi_block["budget_consumed_pct"] = f"{kpi.budget_consumed_pct}%"
            if kpi.snapshot_date:
                kpi_block["as_of"] = kpi.snapshot_date
            if kpi_block:
                snapshot["kpi"] = kpi_block

            if kpi.schedule_progress_pct is not None:
                snapshot["schedule"] = {"progress_pct": f"{kpi.schedule_progress_pct}%"}
                snapshot["overview"] = {
                    **snapshot.get("overview", {}),
                    "schedule_progress_pct": f"{kpi.schedule_progress_pct}%",
                }

            if kpi.risk_score_avg is not None:
                snapshot["risk"] = {"risk_score_avg": kpi.risk_score_avg}

            issues_block = {
                "open_rfis": kpi.open_rfis,
                "open_submittals": kpi.open_submittals,
                "open_defects": kpi.open_defects,
                "open_observations": kpi.open_observations,
            }
            if any(v for v in issues_block.values()):
                snapshot["issues"] = issues_block

        # ── Finance dashboard → summary / cashflow sections ──
        try:
            from app.modules.finance.service import FinanceService

            dash = await FinanceService(self.session).get_dashboard(project_id=project_id)
            dash_data = dash.model_dump() if hasattr(dash, "model_dump") else dict(dash)

            # Money always reads in the report's *resolved* currency — never
            # the finance dashboard's own currency. Blending the two would
            # let a USD-override report show EUR-denominated finance figures
            # (or vice versa), which is exactly the cross-currency leak the
            # tests guard against. We do not FX-convert here: the values are
            # presented under one declared code, and any real conversion is
            # the caller's responsibility upstream.
            def _money(value: object) -> str:
                num = value if value is not None else 0
                return f"{num} {currency}".strip()

            summary_block: dict[str, object] = {}
            if dash_data.get("total_budget_revised") is not None:
                summary_block["budget"] = _money(dash_data.get("total_budget_revised"))
            if dash_data.get("total_committed") is not None:
                summary_block["committed"] = _money(dash_data.get("total_committed"))
            if dash_data.get("total_actual") is not None:
                summary_block["actual"] = _money(dash_data.get("total_actual"))
            if dash_data.get("budget_consumed_pct") is not None:
                summary_block["budget_consumed_pct"] = f"{dash_data.get('budget_consumed_pct')}%"
            if summary_block:
                snapshot["summary"] = summary_block

            cashflow_block: dict[str, object] = {}
            if dash_data.get("total_payable") is not None:
                cashflow_block["payable"] = _money(dash_data.get("total_payable"))
            if dash_data.get("total_receivable") is not None:
                cashflow_block["receivable"] = _money(dash_data.get("total_receivable"))
            if dash_data.get("cash_flow_net") is not None:
                cashflow_block["net_cash_flow"] = _money(dash_data.get("cash_flow_net"))
            if cashflow_block:
                snapshot["cashflow"] = cashflow_block
        except Exception:
            logger.debug(
                "reporting._build_default_snapshot: finance dashboard unavailable for %s",
                project_id,
                exc_info=True,
            )

        # ``report_type`` is accepted for forward-compatibility (a future
        # type-specific assembler can branch on it); today every type
        # draws from the same KPI + finance source set above.
        _ = report_type
        return snapshot or None

    # ── KPI Auto-Recalculation ───────────────────────────────────────────

    async def auto_recalculate_kpis(self) -> dict:
        """Recalculate KPI snapshots for all active projects.

        Called by the scheduler or manually via the admin API endpoint.
        Queries each module (finance, safety, RFI, schedule, etc.) to
        compute up-to-date KPI values and creates a new KPISnapshot row
        per project.

        Returns a summary dict with counts of processed / failed projects.
        """
        from sqlalchemy import Float, func, select
        from sqlalchemy.sql.expression import cast

        from app.modules.projects.models import Project

        today = datetime.now(UTC).strftime("%Y-%m-%d")

        # Fetch all active projects
        stmt = select(Project).where(Project.status == "active")
        result = await self.session.execute(stmt)
        projects = list(result.scalars().all())

        processed = 0
        failed = 0

        for project in projects:
            try:
                pid = project.id

                # ── Finance: CPI, SPI, budget consumed ──
                cpi: str | None = None
                spi: str | None = None
                budget_consumed_pct: str | None = None
                try:
                    from app.modules.finance.service import FinanceService

                    fin_svc = FinanceService(self.session)
                    dashboard = await fin_svc.get_dashboard(project_id=pid)
                    if dashboard.get("total_budget") and float(dashboard["total_budget"]) > 0:
                        total_budget = float(dashboard["total_budget"])
                        total_actual = float(dashboard.get("total_actual", 0))
                        budget_consumed_pct = str(round((total_actual / total_budget) * 100, 1))
                except Exception:
                    logger.warning(
                        "reporting.kpi_recalc finance.get_dashboard failed for project_id=%s — "
                        "budget_consumed_pct will be null",
                        pid,
                        exc_info=True,
                    )

                try:
                    from app.modules.costmodel.service import CostModelService

                    cm_svc = CostModelService(self.session)
                    cm_dash = await cm_svc.get_dashboard(pid)
                    if cm_dash.get("cpi"):
                        cpi = str(cm_dash["cpi"])
                    if cm_dash.get("spi"):
                        spi = str(cm_dash["spi"])
                except Exception:
                    logger.warning(
                        "reporting.kpi_recalc costmodel.get_dashboard failed for project_id=%s — cpi/spi will be null",
                        pid,
                        exc_info=True,
                    )

                # ── Safety: open defects & observations ──
                open_defects = 0
                open_observations = 0
                try:
                    from app.modules.safety.service import SafetyService

                    safety_svc = SafetyService(self.session)
                    safety_stats = await safety_svc.get_stats(pid)
                    open_observations = getattr(safety_stats, "total_observations", 0) - getattr(
                        safety_stats, "closed_observations", 0
                    )
                    if open_observations < 0:
                        open_observations = 0
                    open_defects = getattr(safety_stats, "total_incidents", 0)
                except Exception:
                    logger.warning(
                        "reporting.kpi_recalc safety.get_stats failed for project_id=%s — "
                        "open_defects/open_observations default to 0",
                        pid,
                        exc_info=True,
                    )

                # ── RFIs ──
                open_rfis = 0
                try:
                    from app.modules.rfi.service import RFIService

                    rfi_svc = RFIService(self.session)
                    rfi_stats = await rfi_svc.get_stats(pid)
                    open_rfis = getattr(rfi_stats, "open", 0)
                except Exception:
                    logger.warning(
                        "reporting.kpi_recalc rfi.get_stats failed for project_id=%s — open_rfis defaults to 0",
                        pid,
                        exc_info=True,
                    )

                # ── Submittals ──
                open_submittals = 0
                try:
                    from sqlalchemy import select as sa_select

                    from app.modules.submittals.models import Submittal

                    sub_count = (
                        await self.session.execute(
                            sa_select(func.count(Submittal.id)).where(
                                Submittal.project_id == pid,
                                Submittal.status.notin_(["approved", "closed"]),
                            )
                        )
                    ).scalar_one()
                    open_submittals = sub_count
                except Exception:
                    logger.warning(
                        "reporting.kpi_recalc submittals count failed for project_id=%s — "
                        "open_submittals defaults to 0",
                        pid,
                        exc_info=True,
                    )

                # ── Schedule progress ──
                schedule_progress_pct: str | None = None
                try:
                    from app.modules.schedule.models import Activity, Schedule

                    sched_ids_stmt = select(Schedule.id).where(Schedule.project_id == pid)
                    sched_result = await self.session.execute(sched_ids_stmt)
                    sched_ids = [r[0] for r in sched_result.all()]

                    if sched_ids:
                        avg_progress = (
                            await self.session.execute(
                                select(func.avg(cast(Activity.progress_pct, Float))).where(
                                    Activity.schedule_id.in_(sched_ids)
                                )
                            )
                        ).scalar_one()
                        if avg_progress is not None:
                            schedule_progress_pct = str(round(avg_progress, 1))
                except Exception:
                    logger.warning(
                        "reporting.kpi_recalc schedule.avg_progress failed for project_id=%s — "
                        "schedule_progress_pct will be null",
                        pid,
                        exc_info=True,
                    )

                # ── Risk score ──
                risk_score_avg: str | None = None
                try:
                    from app.modules.risk.models import RiskItem

                    avg_risk = (
                        await self.session.execute(
                            select(func.avg(cast(RiskItem.risk_score, Float))).where(
                                RiskItem.project_id == pid,
                                RiskItem.status != "closed",
                            )
                        )
                    ).scalar_one()
                    if avg_risk is not None:
                        risk_score_avg = str(round(avg_risk, 2))
                except Exception:
                    logger.warning(
                        "reporting.kpi_recalc risk.avg_score failed for project_id=%s — risk_score_avg will be null",
                        pid,
                        exc_info=True,
                    )

                # ── Create snapshot (upsert for today) ──
                existing = None
                existing_stmt = select(KPISnapshot).where(
                    KPISnapshot.project_id == pid,
                    KPISnapshot.snapshot_date == today,
                )
                existing = (await self.session.execute(existing_stmt)).scalar_one_or_none()

                if existing:
                    existing.cpi = cpi
                    existing.spi = spi
                    existing.budget_consumed_pct = budget_consumed_pct
                    existing.open_defects = open_defects
                    existing.open_observations = open_observations
                    existing.schedule_progress_pct = schedule_progress_pct
                    existing.open_rfis = open_rfis
                    existing.open_submittals = open_submittals
                    existing.risk_score_avg = risk_score_avg
                else:
                    snapshot = KPISnapshot(
                        project_id=pid,
                        snapshot_date=today,
                        cpi=cpi,
                        spi=spi,
                        budget_consumed_pct=budget_consumed_pct,
                        open_defects=open_defects,
                        open_observations=open_observations,
                        schedule_progress_pct=schedule_progress_pct,
                        open_rfis=open_rfis,
                        open_submittals=open_submittals,
                        risk_score_avg=risk_score_avg,
                        metadata_={},
                    )
                    self.session.add(snapshot)

                await self.session.flush()
                processed += 1

            except Exception:
                logger.exception("KPI recalculation failed for project %s", project.id)
                failed += 1

        logger.info(
            "KPI auto-recalculation complete: %d processed, %d failed",
            processed,
            failed,
        )
        return {
            "processed": processed,
            "failed": failed,
            "total_projects": len(projects),
            "snapshot_date": today,
        }

    # ── Seed system templates ─────────────────────────────────────────────

    async def seed_system_templates(self) -> int:
        """Seed the 6 system report templates. Truly idempotent.

        Checks each template by name+report_type to avoid duplicates even
        when some templates were manually deleted and re-seeded.
        Returns the number of templates created (0 if all already exist).
        """
        from sqlalchemy import select

        created = 0
        for tmpl_data in SYSTEM_TEMPLATES:
            # Check if this specific template already exists by name + report_type
            stmt = select(ReportTemplate).where(
                ReportTemplate.name == tmpl_data["name"],
                ReportTemplate.report_type == tmpl_data["report_type"],
                ReportTemplate.is_system.is_(True),
            )
            result = await self.session.execute(stmt)
            if result.scalar_one_or_none() is not None:
                continue

            template = ReportTemplate(
                name=tmpl_data["name"],
                report_type=tmpl_data["report_type"],
                description=tmpl_data["description"],
                template_data=tmpl_data["template_data"],
                is_system=True,
                metadata_={},
            )
            self.session.add(template)
            created += 1

        if created:
            await self.session.flush()
            logger.info("Seeded %d system report templates", created)
        return created

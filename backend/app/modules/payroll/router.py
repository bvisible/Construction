# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""Payroll API routes (mounted at ``/api/v1/payroll``).

Endpoints (all manager-scoped + project-access checked):
    POST  /projects/{project_id}/batches/        - generate a draft batch
    GET   /projects/{project_id}/batches/        - list batches for a project
    GET   /batches/{batch_id}                     - batch detail with entries
    PATCH /batches/{batch_id}/submit/             - draft -> submitted
    PATCH /batches/{batch_id}/finalize/           - approve + post labour cost
    PATCH /batches/{batch_id}/post/               - approved -> posted (GL)
    GET   /batches/{batch_id}/reconcile/          - batch hours vs field hours
    GET   /batches/{batch_id}/export.json         - JSON export (ERP handoff)
    GET   /batches/{batch_id}/export.csv          - CSV export (ERP handoff)
    GET   /projects/{project_id}/labour-cost/     - live labour-cost rollup
"""

import csv
import io
import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.dependencies import (
    CurrentUserId,
    RequirePermission,
    SessionDep,
    verify_project_access,
)
from app.modules.payroll.schemas import (
    LabourCostResponse,
    PayrollBatchDetailResponse,
    PayrollBatchGenerate,
    PayrollBatchResponse,
    PayrollEntryResponse,
    PayrollExportResponse,
    PayrollExportRow,
    ReconciliationResponse,
)
from app.modules.payroll.service import PayrollService

router = APIRouter(tags=["payroll"])


def _get_service(session: SessionDep) -> PayrollService:
    return PayrollService(session)


@router.post(
    "/projects/{project_id}/batches/",
    response_model=PayrollBatchDetailResponse,
    status_code=201,
    dependencies=[Depends(RequirePermission("payroll.manage"))],
)
async def generate_batch(
    project_id: uuid.UUID,
    data: PayrollBatchGenerate,
    user_id: CurrentUserId,
    session: SessionDep,
    service: PayrollService = Depends(_get_service),
) -> PayrollBatchDetailResponse:
    """Generate a draft payroll batch by aggregating field labour."""
    await verify_project_access(project_id, user_id, session)
    batch, entries = await service.generate_batch(
        project_id,
        date_from=data.date_from,
        date_to=data.date_to,
        period_label=data.period_label,
        notes=data.notes,
        user_id=user_id,
    )
    detail = PayrollBatchDetailResponse.model_validate(batch)
    detail.entries = [PayrollEntryResponse.model_validate(e) for e in entries]
    return detail


@router.get(
    "/projects/{project_id}/batches/",
    response_model=list[PayrollBatchResponse],
    dependencies=[Depends(RequirePermission("payroll.read"))],
)
async def list_batches(
    project_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    service: PayrollService = Depends(_get_service),
) -> list[PayrollBatchResponse]:
    """List payroll batches for a project (most recent first)."""
    await verify_project_access(project_id, user_id, session)
    batches, _ = await service.list_batches(project_id, offset=offset, limit=limit)
    return [PayrollBatchResponse.model_validate(b) for b in batches]


@router.get(
    "/batches/{batch_id}",
    response_model=PayrollBatchDetailResponse,
    dependencies=[Depends(RequirePermission("payroll.read"))],
)
async def get_batch(
    batch_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: PayrollService = Depends(_get_service),
) -> PayrollBatchDetailResponse:
    """Get a payroll batch and its entries."""
    batch = await service.get_batch(batch_id)
    # IDOR guard: the batch's project must be one the caller can access.
    await verify_project_access(batch.project_id, user_id, session)
    entries = await service.list_entries(batch_id)
    detail = PayrollBatchDetailResponse.model_validate(batch)
    detail.entries = [PayrollEntryResponse.model_validate(e) for e in entries]
    return detail


@router.patch(
    "/batches/{batch_id}/submit/",
    response_model=PayrollBatchDetailResponse,
    dependencies=[Depends(RequirePermission("payroll.manage"))],
)
async def submit_batch(
    batch_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: PayrollService = Depends(_get_service),
) -> PayrollBatchDetailResponse:
    """Submit a draft batch for approval (no money moved).

    Idempotent: a second call on an already-submitted batch returns 200 with the
    unchanged batch. 404 if missing, 400 if not in 'draft'.
    """
    batch = await service.get_batch(batch_id)
    await verify_project_access(batch.project_id, user_id, session)
    batch = await service.submit_batch(batch_id, user_id=user_id)
    entries = await service.list_entries(batch_id)
    detail = PayrollBatchDetailResponse.model_validate(batch)
    detail.entries = [PayrollEntryResponse.model_validate(e) for e in entries]
    return detail


@router.patch(
    "/batches/{batch_id}/finalize/",
    response_model=PayrollBatchDetailResponse,
    dependencies=[Depends(RequirePermission("payroll.finalize"))],
)
async def finalize_batch(
    batch_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: PayrollService = Depends(_get_service),
) -> PayrollBatchDetailResponse:
    """Approve a draft/submitted batch and post its labour cost to the budget.

    Idempotent: a second call on an already-approved (or posted) batch returns
    200 with the unchanged batch. The labour cost lands on the project's
    cost-spine labour budget line (never double-posted). 404 if the batch is
    missing, 400 if it is in a status that cannot be approved.
    """
    batch = await service.get_batch(batch_id)
    # IDOR guard: the caller must have access to the batch's project.
    await verify_project_access(batch.project_id, user_id, session)
    batch = await service.finalize_batch(batch_id, user_id=user_id)
    entries = await service.list_entries(batch_id)
    detail = PayrollBatchDetailResponse.model_validate(batch)
    detail.entries = [PayrollEntryResponse.model_validate(e) for e in entries]
    return detail


@router.patch(
    "/batches/{batch_id}/post/",
    response_model=PayrollBatchDetailResponse,
    dependencies=[Depends(RequirePermission("payroll.post"))],
)
async def post_batch(
    batch_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: PayrollService = Depends(_get_service),
) -> PayrollBatchDetailResponse:
    """Post an approved batch to the finance general ledger (terminal).

    Writes a balanced payroll accrual journal (labour expense / wages payable)
    and flips the batch to 'posted'. Idempotent: a second call on an already
    posted batch returns 200 unchanged with no second journal. 404 if missing,
    400 if not in 'approved'.
    """
    batch = await service.get_batch(batch_id)
    await verify_project_access(batch.project_id, user_id, session)
    batch = await service.post_batch(batch_id, user_id=user_id)
    entries = await service.list_entries(batch_id)
    detail = PayrollBatchDetailResponse.model_validate(batch)
    detail.entries = [PayrollEntryResponse.model_validate(e) for e in entries]
    return detail


@router.get(
    "/batches/{batch_id}/reconcile/",
    response_model=ReconciliationResponse,
    dependencies=[Depends(RequirePermission("payroll.read"))],
)
async def reconcile_batch(
    batch_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: PayrollService = Depends(_get_service),
) -> ReconciliationResponse:
    """Reconcile a batch's hours against the live field-labour sources.

    Read-only: returns a per-worker/date delta of batch hours vs the field
    report + diary hours for the batch period, plus a balanced flag.
    """
    batch = await service.get_batch(batch_id)
    await verify_project_access(batch.project_id, user_id, session)
    return ReconciliationResponse.model_validate(await service.reconcile_batch(batch_id))


@router.get(
    "/batches/{batch_id}/export.json",
    response_model=PayrollExportResponse,
    dependencies=[Depends(RequirePermission("payroll.read"))],
)
async def export_batch_json(
    batch_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: PayrollService = Depends(_get_service),
) -> PayrollExportResponse:
    """Export a batch as JSON for ERP / payroll-provider handoff."""
    batch = await service.get_batch(batch_id)
    await verify_project_access(batch.project_id, user_id, session)
    batch, rows = await service.export_rows(batch_id)
    return PayrollExportResponse(
        batch_id=batch.id,
        project_id=batch.project_id,
        period_label=batch.period_label,
        status=batch.status,
        currency=batch.currency,
        total_hours=batch.total_hours,
        total_amount=batch.total_amount,
        rows=[PayrollExportRow(**r) for r in rows],
    )


@router.get(
    "/batches/{batch_id}/export.csv",
    dependencies=[Depends(RequirePermission("payroll.read"))],
)
async def export_batch_csv(
    batch_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: PayrollService = Depends(_get_service),
) -> StreamingResponse:
    """Export a batch as CSV for ERP / payroll-provider handoff."""
    batch = await service.get_batch(batch_id)
    await verify_project_access(batch.project_id, user_id, session)
    batch, rows = await service.export_rows(batch_id)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["worker", "resource_id", "work_date", "hours", "rate", "amount", "currency", "source"])
    for r in rows:
        writer.writerow(
            [
                r["worker"],
                r["resource_id"],
                r["work_date"],
                r["hours"],
                r["rate"],
                r["amount"],
                r["currency"],
                r["source"],
            ]
        )
    buf.seek(0)
    filename = f"payroll-batch-{batch.id}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/projects/{project_id}/labour-cost/",
    response_model=LabourCostResponse,
    dependencies=[Depends(RequirePermission("payroll.read"))],
)
async def get_labour_cost(
    project_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    date_from: str | None = Query(default=None, max_length=20),
    date_to: str | None = Query(default=None, max_length=20),
    service: PayrollService = Depends(_get_service),
) -> LabourCostResponse:
    """Live labour-cost rollup (base currency) - surfaced beside the cost model."""
    await verify_project_access(project_id, user_id, session)
    cost, hours, currency = await service.labour_cost(project_id, date_from=date_from, date_to=date_to)
    return LabourCostResponse(
        project_id=project_id,
        currency=currency,
        labour_cost=str(cost),
        total_hours=str(hours),
    )

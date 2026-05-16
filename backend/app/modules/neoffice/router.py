"""NEOFFICE FILE — Owned 100% by Neoservice. Not from upstream OpenConstructionERP.

Neoffice extensions API routes.

Endpoints:
    POST /bim/import-roomplan/   — Import an Apple RoomPlan scan into a project
                                   (creates BIMModel + BIMElements, skips DDC).

Planned (Phase 2):
    POST /bim/export-dxf/        — Generate a .dxf 2D floor plan from a scan
    POST /bim/export-ifc/        — Generate an .ifc IFC4 model from a scan
"""

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import SessionDep, get_current_user_id
from app.modules.bim_hub.router import _verify_project_access
from app.modules.bim_hub.schemas import BIMModelCreate, BIMModelResponse
from app.modules.bim_hub.service import BIMHubService
from app.modules.neoffice.roomplan_importer import parse_roomplan_scan
from app.modules.neoffice.schemas import RoomPlanImportRequest

router = APIRouter(dependencies=[Depends(get_current_user_id)])
logger = logging.getLogger(__name__)


@router.post(
    "/bim/import-roomplan/",
    response_model=BIMModelResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_roomplan(
    request: RoomPlanImportRequest,
    session: SessionDep,
    user_id: str = Depends(get_current_user_id),
) -> BIMModelResponse:
    """Import an Apple RoomPlan scan into the target project.

    Skips the DDC IfcExporter pipeline entirely — RoomPlan is already
    parametric, so we map its surfaces/objects directly to ``BIMElement``
    rows with canonical quantities (Length, Width, Height, Area, Volume).

    Returns the created ``BIMModel`` with ``status="ready"`` immediately —
    no background task, no GLB rendering (yet).
    """
    await _verify_project_access(session, request.project_id, user_id)

    elements_data, meta = parse_roomplan_scan(request.scan)
    if not elements_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "No importable elements found in scan. Expected top-level "
                "keys: walls, doors, windows, openings, objects."
            ),
        )

    service = BIMHubService(session)

    metadata = _build_model_metadata(request)
    model_create = BIMModelCreate(
        project_id=request.project_id,
        name=request.name,
        discipline="architecture",
        model_format="roomplan",
        status="processing",
        bounding_box=meta["bounding_box"],
        metadata=metadata,
    )
    model = await service.create_model(model_create, user_id=user_id)

    # Bulk-insert elements via the ORM (single flush at commit time).
    from app.modules.bim_hub.models import BIMElement
    for el in elements_data:
        session.add(BIMElement(model_id=model.id, **el))

    # Finalize model fields once elements are queued.
    model.status = "ready"
    model.element_count = meta["element_count"]
    model.storey_count = meta["storey_count"]
    model.import_date = datetime.now(UTC).isoformat()[:20]
    await session.flush()
    await session.commit()
    await session.refresh(model)

    logger.info(
        "RoomPlan import OK: model=%s project=%s elements=%d",
        model.id, request.project_id, meta["element_count"],
    )
    return BIMModelResponse.model_validate(model)


def _build_model_metadata(request: RoomPlanImportRequest) -> dict[str, Any]:
    """Compose the ``metadata_`` blob stored on BIMModel."""
    meta: dict[str, Any] = {
        "source": "roomplan",
        "units": {"length": "m"},
        "geometry_type": "parametric",
        "geometry_quality": "lidar",
    }
    if request.device_info:
        meta["device"] = request.device_info
    raw_version = request.scan.get("version") or request.scan.get("schemaVersion")
    if raw_version is not None:
        meta["roomplan_version"] = str(raw_version)[:40]
    return meta

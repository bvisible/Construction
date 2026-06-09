"""NEOFFICE FILE — Owned 100% by Neoservice. Not from upstream OpenConstructionERP.

Neoffice extensions API routes.

Endpoints:
    POST /bim/import-roomplan/   — Import an Apple RoomPlan scan into a project
                                   (creates BIMModel + BIMElements, skips DDC).

Planned (Phase 2):
    POST /bim/export-dxf/        — Generate a .dxf 2D floor plan from a scan
    POST /bim/export-ifc/        — Generate an .ifc IFC4 model from a scan
"""

import asyncio
import hmac
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.dependencies import SessionDep, SettingsDep, get_current_user_id
from app.modules.bim_hub import file_storage as bim_file_storage
from app.modules.bim_hub.router import _verify_project_access
from app.modules.bim_hub.schemas import BIMModelCreate, BIMModelResponse
from app.modules.bim_hub.service import BIMHubService
from app.modules.neoffice.plan_vision import analyze_plan_vision
from app.modules.neoffice.roomplan_glb_builder import build_glb_bytes
from app.modules.neoffice.roomplan_importer import parse_roomplan_scan
from app.modules.neoffice.schemas import (
    DetectedRoom,
    FieldReportFromActivitiesRequest,
    PlanVisionRequest,
    PlanVisionResponse,
    RoomDetectionRequest,
    RoomDetectionResponse,
    RoomPlanImportRequest,
    ScheduleProgressBridgeRequest,
)
from app.modules.schedule.models import WorkOrder
from app.modules.schedule.service_4d import ScheduleProgressService

# Each route carries its own auth: the roomplan import keeps the user-JWT
# dependency in its signature, the bridge route uses a shared-token header.
# So the router itself declares no global dependency.
router = APIRouter()
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

    # Bulk-insert elements via the ORM. The importer pre-populates
    # `mesh_ref` with the raw RoomPlan identifier (Apple UUID), which
    # matches the GLB node names emitted by roomplan_glb_builder — that's
    # how the Three.js viewer crosses a picked mesh back to its row.
    from app.modules.bim_hub.models import BIMElement
    for el in elements_data:
        session.add(BIMElement(model_id=model.id, **el))

    # Build + persist a GLB so the viewer renders the room in 3D.
    # Best-effort: a build failure must not block the import — the user
    # still gets the element list, quantities, BoQ linking. We just
    # leave canonical_file_path null and let the existing
    # has_geometry=false fallback kick in.
    glb_key: str | None = None
    try:
        glb_bytes = build_glb_bytes(request.scan)
        glb_key = await bim_file_storage.save_geometry(
            project_id=request.project_id,
            model_id=model.id,
            ext="glb",
            content=glb_bytes,
        )
    except Exception:
        logger.exception(
            "RoomPlan GLB build failed for model %s — model created without geometry",
            model.id,
        )

    # Finalize model fields once elements are queued.
    model.status = "ready"
    model.element_count = meta["element_count"]
    model.storey_count = meta["storey_count"]
    model.import_date = datetime.now(UTC).isoformat()[:20]
    if glb_key:
        model.canonical_file_path = glb_key
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


def _verify_activity_bridge_token(
    x_activity_bridge_token: str = Header(default="", alias="X-Activity-Bridge-Token"),
) -> None:
    """Authenticate a request from the Frappe Activity bridge by shared token.

    The token is read from the ACTIVITY_BRIDGE_TOKEN environment variable --
    the same secret the outbound bridge client uses. Raises 401 on mismatch.
    """
    expected = os.environ.get("ACTIVITY_BRIDGE_TOKEN", "")
    if not expected or not hmac.compare_digest(x_activity_bridge_token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Activity bridge token",
        )


@router.post("/bridge/progress/", dependencies=[Depends(_verify_activity_bridge_token)])
async def record_bridge_progress(
    request: ScheduleProgressBridgeRequest,
    session: SessionDep,
) -> dict[str, Any]:
    """Record a schedule progress entry pushed by the Frappe Activity bridge.

    The mirrored Activity on the Frappe side reports execution progress
    (timer, status). A Work Order source is resolved to its parent Schedule
    Activity, whose id is the ScheduleProgressEntry task_id.
    """
    if request.neoconstruction_source_type == "Work Order":
        work_order = await session.get(WorkOrder, request.neoconstruction_source_id)
        if work_order is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Work order not found"
            )
        task_id = work_order.activity_id
    else:
        task_id = request.neoconstruction_source_id

    service = ScheduleProgressService(session)
    try:
        entry = await service.record(
            task_id=task_id,
            progress_percent=request.progress_percent,
            notes=request.notes,
            device="mobile",
            geolocation=request.geolocation,
            actual_start_date=request.actual_start_date,
            actual_finish_date=request.actual_finish_date,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    await session.commit()
    logger.info(
        "Activity bridge progress recorded: task=%s entry=%s", task_id, entry.id
    )
    return {"success": True, "entry_id": str(entry.id), "task_id": str(task_id)}


@router.post(
    "/bridge/fieldreports/from-activities/",
    dependencies=[Depends(_verify_activity_bridge_token)],
)
async def upsert_fieldreport_from_activities(
    request: FieldReportFromActivitiesRequest,
    session: SessionDep,
) -> dict[str, Any]:
    """Upsert a daily FieldReport draft from consolidated Frappe Activities.

    A draft report for (project, report_date) is updated in place; a missing
    one is created. A report already submitted or approved is left untouched
    so a signed daily report is never overwritten by a late sync.
    """
    from app.modules.fieldreports.schemas import FieldReportCreate
    from app.modules.fieldreports.service import FieldReportService

    service = FieldReportService(session)
    existing = await service.get_by_date(
        request.neoconstruction_project_id, request.report_date
    )
    workforce = [entry.model_dump() for entry in request.workforce]

    if existing is not None:
        if existing.status != "draft":
            return {
                "success": True,
                "skipped": "report is not in draft status",
                "report_id": str(existing.id),
            }
        existing.work_performed = request.work_performed
        existing.workforce = workforce
        existing.equipment_on_site = list(request.equipment_on_site)
        existing.materials_used = list(request.materials_used)
        await session.commit()
        logger.info("Activity bridge FieldReport updated: %s", existing.id)
        return {"success": True, "created": False, "report_id": str(existing.id)}

    report = await service.create_report(
        FieldReportCreate(
            project_id=request.neoconstruction_project_id,
            report_date=request.report_date,
            report_type="daily",
            work_performed=request.work_performed,
            workforce=workforce,
            equipment_on_site=list(request.equipment_on_site),
            materials_used=list(request.materials_used),
        )
    )
    await session.commit()
    logger.info("Activity bridge FieldReport created: %s", report.id)
    return {"success": True, "created": True, "report_id": str(report.id)}


@router.post("/takeoff/analyze-vision/", response_model=PlanVisionResponse)
async def analyze_takeoff_plan_vision(
    request: PlanVisionRequest,
    session: SessionDep,
    settings: SettingsDep,
    user_id: str = Depends(get_current_user_id),
) -> PlanVisionResponse:
    """Analyse one page of a takeoff plan PDF with the multimodal model (vision).

    Unlike the text-only core takeoff analysis, this renders the page to an
    image and asks the vision model to read the rooms, elements and the drawing
    scale, then derives the pixel-per-metre calibration so the plan is
    pre-calibrated and the detected rooms can be pre-drawn as measurements.
    """
    # Lazy import to avoid coupling the module load order to oe_takeoff.
    from app.modules.takeoff.service import TakeoffService

    takeoff = TakeoffService(session)
    doc = await takeoff.get_document(request.document_id)
    if doc is None or not doc.file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Takeoff document not found",
        )

    # Authorise via the document's project when one is set.
    if doc.project_id is not None:
        await _verify_project_access(session, doc.project_id, user_id)

    pdf_path = Path(doc.file_path)
    if not pdf_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stored PDF file not found on server",
        )
    pdf_bytes = pdf_path.read_bytes()

    try:
        result = await analyze_plan_vision(
            pdf_bytes,
            page_index=request.page - 1,
            settings=settings,
            scale_override=request.scale_override,
        )
    except IndexError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:  # LLM/parse failure — surface as upstream error
        logger.exception(
            "Vision plan analysis failed for doc %s", request.document_id
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Vision analysis failed",
        ) from exc

    return PlanVisionResponse(
        document_id=request.document_id, page=request.page, **result
    )


@router.post("/takeoff/detect-rooms/", response_model=RoomDetectionResponse)
async def detect_takeoff_rooms(
    request: RoomDetectionRequest,
    session: SessionDep,
    settings: SettingsDep,
    user_id: str = Depends(get_current_user_id),
) -> RoomDetectionResponse:
    """Detect room polygons from a takeoff PDF's vector layer (geometry, not vision).

    Reads the wall strokes, closes doorways and polygonises into room contours
    that follow the real walls — far more precise than the vision boxes. The
    drawing scale is read off the plan via the vision model when not supplied.
    """
    from app.modules.neoffice.room_detection import detect_rooms, page_has_vectors
    from app.modules.takeoff.service import TakeoffService

    takeoff = TakeoffService(session)
    doc = await takeoff.get_document(request.document_id)
    if doc is None or not doc.file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Takeoff document not found"
        )
    if doc.project_id is not None:
        await _verify_project_access(session, doc.project_id, user_id)

    pdf_path = Path(doc.file_path)
    if not pdf_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stored PDF file not found on server",
        )
    pdf_bytes = pdf_path.read_bytes()
    page_idx = request.page - 1

    # Route by PDF type: a vector CAD export goes to the geometry pathway
    # (precise wall-following contours); a raster/scan PDF (image only, no walls
    # to polygonise) goes to the vision pathway. One button, two engines.
    is_vector = await asyncio.to_thread(page_has_vectors, pdf_bytes, page_idx)

    if not is_vector:
        try:
            vision = await analyze_plan_vision(
                pdf_bytes, page_idx, settings, scale_override=request.scale_override
            )
        except Exception as exc:
            logger.exception("Vision room detection failed for %s", request.document_id)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Vision room detection failed",
            ) from exc
        # Each vision box (normalised [0,1]) becomes a rectangular polygon so the
        # frontend renders it exactly like a geometry-detected room.
        vrooms: list[DetectedRoom] = []
        for r in vision.get("rooms", []):
            bbox = r.get("bbox")
            if not bbox or len(bbox) != 4:
                continue
            x0, y0, x1, y1 = bbox
            vrooms.append(
                DetectedRoom(
                    name=r.get("name"),
                    polygon=[[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
                    area_m2=r.get("approx_area_m2"),
                )
            )
        return RoomDetectionResponse(
            document_id=request.document_id,
            page=request.page,
            page_width_pt=vision.get("page_width_pt", 0.0),
            page_height_pt=vision.get("page_height_pt", 0.0),
            scale_ratio=vision.get("scale_ratio"),
            scale_pixels_per_unit=vision.get("scale_pixels_per_unit"),
            rooms=vrooms,
            stats={"vision": 1, "rooms": len(vrooms)},
        )

    # Vector pathway: geometry. Read the drawing scale off the plan when absent.
    scale_ratio = request.scale_override
    if scale_ratio is None:
        try:
            vision = await analyze_plan_vision(pdf_bytes, page_idx, settings)
            scale_ratio = vision.get("scale_ratio")
        except Exception:
            logger.exception("Scale read via vision failed for %s", request.document_id)
            scale_ratio = None

    try:
        # CPU-bound geometry — run off the event loop.
        result = await asyncio.to_thread(detect_rooms, pdf_bytes, page_idx, scale_ratio)
    except IndexError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.exception("Room detection failed for %s", request.document_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Room detection failed"
        ) from exc

    return RoomDetectionResponse(
        document_id=request.document_id, page=request.page, **result
    )

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
import uuid
from decimal import Decimal, InvalidOperation  #//// Neoffice — price band on the resource pass; InvalidOperation guards the String money columns
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

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
    ElementMetreRequest,
    FieldReportFromActivitiesRequest,
    PlanVisionRequest,
    PlanVisionResponse,
    RoomDetectionRequest,
    RoomDetectionProposalResponse,
    RoomDetectionResponse,
    RoomPlanImportRequest,
    ScheduleProgressBridgeRequest,
    SiteMeasurementAgree,
    SiteMeasurementCreate,
    SiteMeasurementUpdate,
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
                    confidence="low",
                    needs_review=True,
                    review_reason="vision_bbox",
                    source="vision",
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

    # Vector pathway: geometry. detect_rooms derives the TRUE scale from the plan's
    # dimension lines (§1d) and only falls back to scale_override when none are
    # found — so the slow vision scale-read is no longer needed on this path.
    try:
        # CPU-bound geometry — run off the event loop.
        result = await asyncio.to_thread(
            detect_rooms, pdf_bytes, page_idx, request.scale_override
        )
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


@router.post("/takeoff/element-metre/")
async def element_metre(
    request: ElementMetreRequest,
    session: SessionDep,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Deterministic element take-off (métré) from a vector PDF's CAD layers.

    Measures concrete walls (interior/exterior), partitions and slabs by reading
    the architect's preserved OCG layers — no ML. Returns linear metres + m²
    (walls) and m² (slabs) with eBKP-H codes. Companion to /takeoff/detect-rooms/
    (rooms) — this measures structural & finish *elements*.
    """
    from app.modules.neoffice.element_metre import compute_element_metre
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
    try:
        # CPU-bound geometry (polygonise + centre-lines) — run off the event loop.
        result = await asyncio.to_thread(
            compute_element_metre,
            pdf_bytes,
            request.page - 1,
            request.scale_ratio,
            request.storey_height_m,
        )
    except IndexError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.exception("Element métré failed for %s", request.document_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Element métré failed"
        ) from exc
    return {"document_id": request.document_id, **result}


# ── Linked quantity (Neoffice) — one measurement drives many BOQ positions ────


class LinkQuantityRequest(BaseModel):
    """Drive one BOQ position from a source × factor. The source is either a
    takeoff ``measurement_id`` OR another ``source_position_id`` (exactly one)."""

    position_id: str
    measurement_id: str | None = None
    source_position_id: str | None = None
    factor: float = 1.0


class RefreshDrivenRequest(BaseModel):
    boq_id: str


class UnlinkQuantityRequest(BaseModel):
    position_id: str


@router.post("/boq/link-quantity/")
async def link_quantity(
    request: LinkQuantityRequest,
    session: SessionDep,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Drive a BOQ position's quantity from a takeoff measurement (× factor).

    Neoffice one-to-many linked quantity: upstream links a measurement to a single
    position; this stores the link on the position so the SAME measurement can
    drive several positions (call once per position). A slab area can feed the
    concrete, screed and parquet positions, each with its own factor.
    """
    from app.modules.boq.service import BOQService
    from app.modules.neoffice.quantity_link import (
        link_position_to_measurement,
        link_position_to_position,
    )
    from app.modules.takeoff.service import TakeoffService

    try:
        if request.source_position_id:
            # Source = another BOQ position's quantity (e.g. "Surface 2").
            src = await BOQService(session).position_repo.get_by_id(
                uuid.UUID(request.source_position_id)
            )
            if src is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Source position not found"
                )
            project_id = await BOQService(session).position_repo.project_id_for_boq(src.boq_id)
            if project_id is not None:
                await _verify_project_access(session, project_id, user_id)
            return await link_position_to_position(
                session,
                uuid.UUID(request.position_id),
                uuid.UUID(request.source_position_id),
                factor=request.factor,
            )
        if request.measurement_id:
            # Source = a takeoff measurement (a zone/area extracted from a plan).
            measurement = await TakeoffService(session).get_measurement(
                uuid.UUID(request.measurement_id)
            )
            await _verify_project_access(session, measurement.project_id, user_id)
            return await link_position_to_measurement(
                session,
                uuid.UUID(request.position_id),
                uuid.UUID(request.measurement_id),
                factor=request.factor,
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="measurement_id or source_position_id required",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/boq/refresh-driven/")
async def refresh_driven(
    request: RefreshDrivenRequest,
    session: SessionDep,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Re-push every driven position in a BOQ from its source measurement (live).

    Run after re-measuring the plan to update the whole devis in one click.
    """
    from app.modules.boq.service import BOQService
    from app.modules.neoffice.quantity_link import refresh_driven_quantities

    boq_id = uuid.UUID(request.boq_id)
    project_id = await BOQService(session).position_repo.project_id_for_boq(boq_id)
    if project_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BOQ not found")
    await _verify_project_access(session, project_id, user_id)
    return await refresh_driven_quantities(session, boq_id)


@router.post("/boq/unlink-quantity/")
async def unlink_quantity(
    request: UnlinkQuantityRequest,
    session: SessionDep,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Remove a position's driven-by link (leaves its current quantity as-is)."""
    from app.modules.boq.service import BOQService
    from app.modules.neoffice.quantity_link import unlink_position

    position_id = uuid.UUID(request.position_id)
    boq = BOQService(session)
    position = await boq.position_repo.get_by_id(position_id)
    if position is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Position not found")
    project_id = await boq.position_repo.project_id_for_boq(position.boq_id)
    if project_id is not None:
        await _verify_project_access(session, project_id, user_id)
    try:
        return await unlink_position(session, position_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _room_detection_confidence(room: DetectedRoom) -> float:
    """Map the Neoffice QA band to the 0..1 plan-read confidence scale."""
    by_band = {"high": 0.86, "medium": 0.68, "low": 0.45}
    score = by_band.get((room.confidence or "low").lower(), 0.45)
    if room.needs_review and score > 0.69:
        score = 0.69
    if room.error_pct is not None and abs(room.error_pct) > 10:
        score = min(score, 0.55)
    return round(max(0.0, min(1.0, score)), 2)


def _room_detection_pdf_points(
    polygon: list[list[float]],
    page_width_pt: float,
    page_height_pt: float,
) -> list[dict[str, float]]:
    """Convert normalised Neoffice room polygons to PDF-point canvas coords."""
    out: list[dict[str, float]] = []
    for xy in polygon:
        if len(xy) < 2:
            continue
        x = max(0.0, min(1.0, float(xy[0]))) * page_width_pt
        y = max(0.0, min(1.0, float(xy[1]))) * page_height_pt
        out.append({"x": x, "y": y})
    return out


@router.post(
    "/takeoff/detect-rooms/proposals/",
    response_model=RoomDetectionProposalResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_room_detection_proposals(
    request: RoomDetectionRequest,
    session: SessionDep,
    settings: SettingsDep,
    user_id: str = Depends(get_current_user_id),
) -> RoomDetectionProposalResponse:
    """Persist Neoffice room detection as v7.6 plan-read review proposals.

    This keeps the Neoffice geometry detector outside the OCE core while using
    the upstream plan-read lifecycle for review, accept, reload and audit.
    """
    from app.modules.takeoff import plan_read as _plan_read
    from app.modules.takeoff.models import AiTakeoffRun, TakeoffMeasurement
    from app.modules.takeoff.service import TakeoffService
    from sqlalchemy import delete

    takeoff = TakeoffService(session)
    doc = await takeoff.get_document(request.document_id)
    if doc is None or not doc.file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Takeoff document not found"
        )
    if doc.project_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Room proposals require a project-backed takeoff document",
        )
    await _verify_project_access(session, doc.project_id, user_id)

    detected = await detect_takeoff_rooms(request, session, settings, user_id)

    # Supersede previous still-unreviewed room proposals for this page. A
    # confirmed measurement is user data and must never be replaced here.
    await session.execute(
        delete(TakeoffMeasurement).where(
            TakeoffMeasurement.project_id == doc.project_id,
            TakeoffMeasurement.document_id == request.document_id,
            TakeoffMeasurement.page == request.page,
            TakeoffMeasurement.source == "ai_plan_read",
            TakeoffMeasurement.review_status == "proposed",
        )
    )

    run = await takeoff.plan_read_repo.create(
        AiTakeoffRun(
            project_id=doc.project_id,
            document_id=request.document_id,
            page=request.page,
            mode="rooms",
            user_id=uuid.UUID(str(user_id)),
            created_by=str(user_id),
            status="review",
            scale_pixels_per_unit=detected.scale_pixels_per_unit,
            do_cost_match=False,
            provider="neoffice",
            model_used=(
                "neoffice-room-vision-bbox"
                if any(room.source == "vision" for room in detected.rooms)
                else (
                    "neoffice-room-label-surface-v1"
                    if any(room.source == "label_surface" for room in detected.rooms)
                    else "neoffice-room-vector-v2"
                )
            ),
            proposal_count=0,
            accepted_count=0,
            validation_report={
                "engine": "neoffice_room_detection",
                "source": "vector_or_vision",
                "stats": detected.stats,
                "sources": sorted({room.source for room in detected.rooms}),
                "scale_ratio": detected.scale_ratio,
                "scale_pixels_per_unit": detected.scale_pixels_per_unit,
                "page_width_pt": detected.page_width_pt,
                "page_height_pt": detected.page_height_pt,
            },
            metadata_={"engine": "neoffice_room_detection"},
        )
    )
    run_id = run.id

    proposals: list[TakeoffMeasurement] = []
    for room in detected.rooms:
        if len(room.polygon) < 3:
            continue
        points = _room_detection_pdf_points(
            room.polygon,
            detected.page_width_pt,
            detected.page_height_pt,
        )
        if len(points) < 3:
            continue
        point_pairs = [(p["x"], p["y"]) for p in points]
        self_intersects = _plan_read.polygon_self_intersects(point_pairs)
        confidence = _room_detection_confidence(room)
        if self_intersects:
            confidence = min(confidence, 0.55)
        needs_review = bool(room.needs_review) or self_intersects
        metadata: dict[str, Any] = {
            "ai_takeoff_run_id": str(run_id),
            "engine": "neoffice_room_detection",
            "detection_source": room.source,
            "detection_confidence": room.confidence,
            "detection_needs_review": needs_review,
            "detection_review_reason": "self_intersects"
            if self_intersects
            else room.review_reason,
            "detection_declared_area_m2": room.declared_m2,
            "detection_error_pct": room.error_pct,
            "detection_geometry_area_m2": getattr(room, "geometry_m2", None),
            "detection_quantity_source": (
                "printed_surface" if room.source == "label_surface" else "polygon"
            ),
            "page_width_pt": detected.page_width_pt,
            "page_height_pt": detected.page_height_pt,
            "room_name": room.name,
            "self_intersects": self_intersects,
            "verdict": "error" if self_intersects else ("review" if needs_review else "ok"),
        }
        proposals.append(
            TakeoffMeasurement(
                project_id=doc.project_id,
                document_id=request.document_id,
                page=request.page,
                type="area",
                group_name="Pièces",
                group_color="#F59E0B" if needs_review else "#10B981",
                annotation=room.name or "Pièce",
                points=points,
                measurement_value=room.area_m2,
                measurement_unit="m2",
                scale_pixels_per_unit=detected.scale_pixels_per_unit,
                source="ai_plan_read",
                confidence=confidence,
                review_status="proposed",
                metadata_=metadata,
                created_by=str(user_id),
            )
        )

    if proposals:
        await takeoff.measurement_repo.create_bulk(proposals)
    await takeoff.plan_read_repo.update_fields(
        run_id,
        proposal_count=len(proposals),
        validation_report={
            **(run.validation_report or {}),
            "proposal_count": len(proposals),
            "rooms_needs_review": sum(
                1 for p in proposals if (p.metadata_ or {}).get("detection_needs_review")
            ),
        },
    )
    await session.commit()
    return RoomDetectionProposalResponse(
        run_id=run_id,
        document_id=request.document_id,
        page=request.page,
        scale_ratio=detected.scale_ratio,
        scale_pixels_per_unit=detected.scale_pixels_per_unit,
        proposal_count=len(proposals),
        stats={**detected.stats, "proposal_count": len(proposals)},
    )


# //// NEOFFICE PATCH — Sottens -> site travel distance via OpenStreetMap
# (Nominatim geocoding + OSRM routing, no API key). Feeds the déplacement
# component of the composed Protti labour tariff.
class DepotToSiteRequest(BaseModel):
    site_address: str
    depot_address: str | None = None


@router.post("/distance/depot-to-site/")
async def compute_depot_to_site(
    request: DepotToSiteRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Driving distance depot (Sottens) -> construction site via OpenStreetMap,
    with the CN/CCT travel split (driver paid all, passengers the excess)."""
    from app.modules.neoffice import distance

    return await distance.depot_to_site(request.site_address, request.depot_address)


# //// NEOFFICE PATCH — composed labour tariff (the estimating "moteur"): base wage
# -> composed hourly cost (charges + repas + indemnité + déplacement). With a site
# address it pulls the OSM distance and returns driver + passenger tariffs.
class LaborTariffRequest(BaseModel):
    base_hourly: float | None = None
    site_address: str | None = None
    depot_address: str | None = None
    # When set, the project's own calibration is used (falling back to the
    # company defaults for anything it does not override).
    project_id: str | None = None
    charges_pct: str | None = None
    repas_jour: str | None = None
    indemnite_jour: str | None = None
    heures_jour: str | None = None
    salaire_base_horaire: str | None = None
    charges_depot_h: str | None = None
    charges_bureau_h: str | None = None
    marge_mo_pct: str | None = None
    arrondi_chf: str | None = None


class LaborParamsUpdate(BaseModel):
    """Calibration payload. Every field is optional so a caller can patch a
    single value without having to resend the whole set; anything omitted keeps
    its stored value (and falls back to the documented default when unset)."""

    charges_pct: str | None = None
    repas_jour: str | None = None
    indemnite_jour: str | None = None
    heures_jour: str | None = None
    salaire_base_horaire: str | None = None
    charges_depot_h: str | None = None
    charges_bureau_h: str | None = None
    marge_mo_pct: str | None = None
    marge_materiaux_pct: str | None = None
    marge_machines_pct: str | None = None
    marge_outillage_pct: str | None = None
    marge_tiers_pct: str | None = None
    arrondi_chf: str | None = None


async def _load_company_params(session: Any, user_id: str) -> dict[str, str]:
    """Company-wide calibration (stored on the user's metadata_)."""
    from app.modules.neoffice import labor_tariff
    from app.modules.users.models import User

    user = await session.get(User, user_id)
    meta = (user.metadata_ or {}) if user else {}
    return meta.get(labor_tariff.PARAMS_META_KEY, {}) or {}


async def _load_project_params(session: Any, project_id: str | None) -> dict[str, str]:
    """Per-project overrides (stored on the project's metadata_)."""
    from app.modules.neoffice import labor_tariff
    from app.modules.projects.models import Project

    if not project_id:
        return {}
    project = await session.get(Project, project_id)
    meta = (project.metadata_ or {}) if project else {}
    return meta.get(labor_tariff.PARAMS_META_KEY, {}) or {}


async def _load_labor_params(
    session: Any, user_id: str, project_id: str | None = None
) -> dict[str, str]:
    """Effective calibration: company defaults, then the project's overrides.

    This is the inheritance the estimator asked about ("where are the general
    variables taken from when a project is created?"): one company-wide set
    acts as the starting point, and a project only stores what it changes.
    """
    company = await _load_company_params(session, user_id)
    project = await _load_project_params(session, project_id)
    return {**company, **project}


@router.post("/labor-tariff/compose/")
async def compose_labor_tariff_endpoint(
    request: LaborTariffRequest,
    session: SessionDep,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Compose the real hourly labour cost from a CN base wage, optionally adding
    the distance-based déplacement (driver + passenger tariffs, CN/CCT split).
    Uses the instance's calibrated parameters, overridable per request."""
    from app.modules.neoffice import distance, labor_tariff

    stored = await _load_labor_params(session, user_id, request.project_id)
    overrides = {
        k: v for k, v in {
            "charges_pct": request.charges_pct,
            "repas_jour": request.repas_jour,
            "indemnite_jour": request.indemnite_jour,
            "heures_jour": request.heures_jour,
            "salaire_base_horaire": request.salaire_base_horaire,
            "charges_depot_h": request.charges_depot_h,
            "charges_bureau_h": request.charges_bureau_h,
            "marge_mo_pct": request.marge_mo_pct,
            "arrondi_chf": request.arrondi_chf,
        }.items() if v is not None
    }
    params = labor_tariff.TariffParams.from_mapping({**stored, **overrides})
    travel = None
    if request.site_address:
        travel = await distance.depot_to_site(request.site_address, request.depot_address)
    # The base wage is a calibrated parameter now: the request may still pass one
    # explicitly (a specific crew class), otherwise the calibration decides.
    base = request.base_hourly if request.base_hourly is not None else params.salaire_base_horaire
    return labor_tariff.compose(base, params, travel)


class LaborTariffApplyRequest(BaseModel):
    """Push the composed hourly tariff onto the labour components of a scope."""

    project_id: str | None = None
    assembly_id: str | None = None
    site_address: str | None = None
    #: "conducteur" (travel paid in full) or "passager" (excess only).
    role: str = "conducteur"
    #: Apply the SELLING price (cost + risk & profit, rounded) instead of the cost.
    use_selling_price: bool = False
    #: Only units in this list are touched (an hourly rate makes no sense on a m3 line).
    units: list[str] = ["h", "hr", "heure", "heures"]
    #: Report what would change without writing anything. Default: report only.
    dry_run: bool = True
    #: //// NEOFFICE PATCH — also re-price the catalogue's labour resources.
    #: Cédric Protti, 2026-08-20, twice in one mail: "une ressource « Main
    #: d'oeuvre » devrait être mise à jour automatiquement avec les indications
    #: données sur la page principale de l'affaire". Re-pricing the assemblies
    #: alone left the library they are built from stale, so the next assembly
    #: an estimator composed picked the old rate back up.
    #: Off by default: an existing caller keeps its exact behaviour.
    include_catalog_resources: bool = False
    #: Region to confine the resource pass to. None = every region.
    resource_region: str | None = None
    #: Write even though hourly overhead lines would price the structure twice.
    allow_double_count: bool = False
    #: //// END NEOFFICE PATCH


@router.post("/labor-tariff/apply/")
async def apply_labor_tariff(
    request: LaborTariffApplyRequest,
    session: SessionDep,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Re-price the labour components from the composed tariff.

    The estimator's ask: "the labour price should be taken automatically from
    the calculation in the Project section". Their assemblies currently carry a
    flat hourly rate typed once (540 components at the same value), so every
    change to the wage, the charges or the margin had to be re-typed everywhere.

    Deliberately explicit rather than magic:
      * ``dry_run`` is TRUE by default — the caller sees the count and the old
        vs new rate before anything is written;
      * only hourly units are touched, never a m3 or a forfait line;
      * each updated row records what was applied (rate, role, timestamp) in
        its metadata, so the change is auditable and a later run can tell which
        rows it owns.
    """
    from sqlalchemy import select

    from app.modules.assemblies.models import Assembly, Component as AssemblyComponent
    from app.modules.neoffice import distance, labor_tariff

    params = labor_tariff.TariffParams.from_mapping(
        await _load_labor_params(session, user_id, request.project_id)
    )
    travel = None
    if request.site_address:
        travel = await distance.depot_to_site(request.site_address)
    composed = labor_tariff.compose(params.salaire_base_horaire, params, travel)

    role = "passager" if request.role == "passager" else "conducteur"
    key = f"prix_horaire_{role}_chf" if request.use_selling_price else f"cout_horaire_{role}_chf"
    new_rate = composed.get(key) or composed["cout_horaire_conducteur_chf"]

    stmt = select(AssemblyComponent).where(AssemblyComponent.resource_type == "labor")
    if request.assembly_id:
        stmt = stmt.where(AssemblyComponent.assembly_id == request.assembly_id)
    elif request.project_id:
        stmt = stmt.join(Assembly, Assembly.id == AssemblyComponent.assembly_id).where(
            Assembly.project_id == request.project_id
        )
    rows = (await session.execute(stmt)).scalars().all()

    wanted_units = {u.strip().lower() for u in request.units}
    changed: list[dict[str, str]] = []
    #//// Neoffice — assemblies whose stored total_rate must be rebuilt.
    touched_assemblies: set[str] = set()
    for row in rows:
        if (row.unit or "").strip().lower() not in wanted_units:
            continue
        old = str(row.unit_cost)
        if old == str(new_rate):
            continue
        changed.append({"id": str(row.id), "old": old, "new": str(new_rate)})
        if not request.dry_run:
            row.unit_cost = str(new_rate)
            # //// NEOFFICE PATCH — recompute the line total, or the row shows a
            # new hourly rate beside a total still built on the old one. The
            # component total is factor * quantity * unit_cost (see
            # assemblies/service.py); writing unit_cost alone left every touched
            # row internally inconsistent, and the assembly total below with it.
            try:
                _f = Decimal(str(row.factor or "1"))
                _q = Decimal(str(row.quantity or "0"))
                _line = _f * _q * Decimal(str(new_rate))
                row.total = str(_line) if _line.is_finite() else "0"
            except (ArithmeticError, ValueError):
                row.total = "0"
            touched_assemblies.add(str(row.assembly_id))
            # //// END NEOFFICE PATCH
            meta = dict(row.metadata_ or {})
            meta["neoffice_tariff"] = {
                "rate": str(new_rate),
                "role": role,
                "selling_price": request.use_selling_price,
                "applied_at": datetime.now(UTC).isoformat(),
            }
            row.metadata_ = meta

    # //// NEOFFICE PATCH — the same pass over the resource catalogue.
    # An assembly component stores its own rate, so re-pricing components fixes
    # today's assemblies and nothing else: the library they are composed from
    # kept the old figure and handed it straight back to the next assembly.
    # Same three guarantees as above — dry-run first, hourly units only, and an
    # audit stamp so a later run knows which rows it owns.
    resources_changed: list[dict[str, str]] = []
    resources_in_scope = 0
    if request.include_catalog_resources:
        from app.modules.catalog.models import CatalogResource

        rstmt = select(CatalogResource).where(CatalogResource.resource_type == "labor")
        if request.resource_region:
            rstmt = rstmt.where(CatalogResource.region == request.resource_region)
        resources = (await session.execute(rstmt)).scalars().all()
        resources_in_scope = len(resources)
        for res in resources:
            if (res.unit or "").strip().lower() not in wanted_units:
                continue
            old_price = str(res.base_price)
            if old_price == str(new_rate):
                continue
            resources_changed.append(
                {"id": str(res.id), "code": res.resource_code, "old": old_price, "new": str(new_rate)}
            )
            if not request.dry_run:
                # Money columns on this model are String(50) — write text, and
                # widen the band rather than leave base outside [min, max].
                res.base_price = str(new_rate)
                try:
                    band_lo = Decimal(str(res.min_price or "0"))
                    band_hi = Decimal(str(res.max_price or "0"))
                    rate = Decimal(str(new_rate))
                except (ArithmeticError, ValueError):
                    band_lo = band_hi = rate = Decimal("0")
                if band_lo and rate < band_lo:
                    res.min_price = str(rate)
                if band_hi and rate > band_hi:
                    res.max_price = str(rate)
                meta = dict(res.metadata_ or {})
                meta["neoffice_tariff"] = {
                    "rate": str(new_rate),
                    "role": role,
                    "selling_price": request.use_selling_price,
                    "applied_at": datetime.now(UTC).isoformat(),
                }
                res.metadata_ = meta
    # //// END NEOFFICE PATCH

    # //// NEOFFICE PATCH — refuse to double-count the structure costs.
    #
    # The composed tariff already carries the depot and office overhead
    # (charges_depot_h + charges_bureau_h). Protti's assemblies ALSO carry a
    # separate "FG administratif" line per productive hour, inherited from the
    # Excel sheet. Pushing the tariff while those lines stand prices every hour
    # twice — measured on 2026-08-20: 95.65 + 18.94 = 114.59 CHF/h, +28 % on a
    # real estimate, and nothing on screen would say so.
    #
    # The estimator decided to drop those lines (option B, 2026-08-20), but the
    # order matters and an ordering rule that lives only in a mail is a rule
    # that gets forgotten. Report it always; refuse to write while it holds,
    # unless the caller says it knows.
    structure_h = params.charges_depot_h + params.charges_bureau_h
    overhead_rows: list[Any] = []
    if structure_h > 0:
        ostmt = select(AssemblyComponent).where(
            AssemblyComponent.resource_type == "overhead"
        )
        if request.assembly_id:
            ostmt = ostmt.where(AssemblyComponent.assembly_id == request.assembly_id)
        elif request.project_id:
            ostmt = ostmt.join(
                Assembly, Assembly.id == AssemblyComponent.assembly_id
            ).where(Assembly.project_id == request.project_id)
        overhead_rows = [
            r for r in (await session.execute(ostmt)).scalars().all()
            if (r.unit or "").strip().lower() in wanted_units
        ]

    double_count = {
        "hourly_overhead_lines": len(overhead_rows),
        "tariff_structure_chf_h": str(structure_h),
        "explanation": (
            "The composed tariff already carries the depot and office overhead. "
            "These hourly overhead lines carry it a second time — remove them "
            "before applying, or pass allow_double_count to proceed anyway."
        ) if overhead_rows else None,
    }
    if overhead_rows and not request.dry_run and not request.allow_double_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "structure_cost_counted_twice",
                **double_count,
            },
        )
    # //// END NEOFFICE PATCH

    # //// NEOFFICE PATCH — rebuild the stored total of every assembly touched.
    # Assembly.total_rate is persisted, not derived on read, so re-pricing a
    # component without it leaves the header showing yesterday's figure.
    # Same arithmetic as assemblies/service.py: sum(component totals) * bid_factor.
    assemblies_retotalled = 0
    if not request.dry_run and touched_assemblies:
        await session.flush()
        for aid in touched_assemblies:
            asm = await session.get(Assembly, aid)
            if asm is None:
                continue
            comps = (await session.execute(
                select(AssemblyComponent).where(AssemblyComponent.assembly_id == aid)
            )).scalars().all()
            subtotal = Decimal("0")
            for c in comps:
                try:
                    v = Decimal(str(c.total or "0"))
                except (ArithmeticError, ValueError):
                    continue
                if v.is_finite():
                    subtotal += v
            try:
                bf = Decimal(str(asm.bid_factor or "1"))
            except (ArithmeticError, ValueError):
                bf = Decimal("1")
            product = subtotal * bf
            asm.total_rate = str(product) if product.is_finite() else "0"
            assemblies_retotalled += 1
    # //// END NEOFFICE PATCH

    if not request.dry_run and (changed or resources_changed):
        await session.commit()

    return {
        "dry_run": request.dry_run,
        "role": role,
        "rate_applied": str(new_rate),
        "using": "selling_price" if request.use_selling_price else "cost",
        "labour_components_in_scope": len(rows),
        "would_change" if request.dry_run else "changed": len(changed),
        "sample": changed[:5],
        # //// NEOFFICE PATCH — the resource pass reports separately, so a caller
        # can see at a glance whether the library moved as well as the assemblies.
        "catalog_resources_in_scope": resources_in_scope,
        ("resources_would_change" if request.dry_run else "resources_changed"): len(resources_changed),
        "resources_sample": resources_changed[:5],
        "double_count_check": double_count,
        "assemblies_retotalled": assemblies_retotalled,
        # //// END NEOFFICE PATCH
        "tariff": composed,
    }


@router.get("/labor-tariff/params/")
async def get_labor_params(
    session: SessionDep,
    project_id: str | None = None,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Return the effective labour params (defaults ← company ← project).

    ``effective`` is what the tariff actually uses. ``company`` and ``project``
    are returned alongside so the UI can show what a project overrides and
    which values are simply inherited.
    """
    from app.modules.neoffice import labor_tariff

    company = await _load_company_params(session, user_id)
    project = await _load_project_params(session, project_id)
    return {
        "effective": {**labor_tariff.DEFAULTS, **company, **project},
        "company": company,
        "project": project,
        "defaults": labor_tariff.DEFAULTS,
    }


@router.put("/labor-tariff/params/")
async def put_labor_params(
    request: LaborParamsUpdate,
    session: SessionDep,
    project_id: str | None = None,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, str]:
    """Persist the calibration — company-wide, or for one project.

    With ``project_id`` the values land on that project and only override what
    was sent; without it they become the company defaults every new project
    inherits. Fields left null keep their stored value, so the UI can patch a
    single number without resending the whole form.
    """
    from app.modules.neoffice import labor_tariff
    from app.modules.projects.models import Project
    from app.modules.users.models import User

    sent = {k: v for k, v in request.model_dump().items() if v is not None}

    if project_id:
        target: Any = await session.get(Project, project_id)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    else:
        target = await session.get(User, user_id)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")

    meta = dict(target.metadata_ or {})
    stored = dict(meta.get(labor_tariff.PARAMS_META_KEY) or {})
    stored.update(sent)
    meta[labor_tariff.PARAMS_META_KEY] = stored
    # Reassign (not mutate) so SQLAlchemy sees the JSON column as dirty.
    target.metadata_ = meta
    await session.commit()
    return stored
# //// END NEOFFICE PATCH


# ── Swiss CAN / NPK text catalogue ──────────────────────────────────────────
# A library of position TEXTS, not priced articles. See models.py for why this
# cannot live in the cost catalogue (`oe_costs_item.rate` is NOT NULL).


class TextCatalogCreate(BaseModel):
    code: str
    name: str
    description: str = ""
    standard: str = "CAN"
    language: str = "fr"
    project_id: str | None = None


class TextPositionCreate(BaseModel):
    code: str
    title: str = ""
    body: str = ""
    #: Leave null/empty for a wording line; set it on a measurable sub-position.
    unit: str | None = None
    parent_id: str | None = None
    assembly_id: str | None = None
    sort_order: int = 0


class TextPositionUpdate(BaseModel):
    code: str | None = None
    title: str | None = None
    body: str | None = None
    unit: str | None = None
    assembly_id: str | None = None
    sort_order: int | None = None


class InsertIntoBoqRequest(BaseModel):
    boq_id: str
    #: Parent section the position is created under (optional).
    parent_id: str | None = None
    #: Ordinal to give the new BOQ position; auto if omitted.
    ordinal: str | None = None
    quantity: str = "0"
    #: Slot the row immediately AFTER this BOQ position (same rule as the
    #: batch insert above).
    after_position_id: str | None = None
    #: Copy the linked assembly (price analysis) onto the created rows.
    #: Cédric Protti, 2026-08-18: "pourquoi les articles du catalogue ne
    #: pourraient-ils pas être insérés avec ou sans l'analyse de prix ?".
    #: Default True keeps the previous behaviour for existing callers.
    with_assembly: bool = True


def _position_payload(p: Any, children: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Serialise one position.

    ``children`` is passed IN rather than read off the relationship: touching
    ``p.children`` inside an async request lazy-loads and raises MissingGreenlet
    (the same trap that produced the bogus "rasterize_failed" in plan-read).
    The tree endpoint loads every row of the catalogue in one query and nests
    them in Python instead.
    """
    return {
        "id": str(p.id),
        "code": p.code,
        "title": p.title,
        "body": p.body,
        "unit": p.unit,
        "measurable": bool(p.unit and p.unit.strip()),
        "assembly_id": str(p.assembly_id) if p.assembly_id else None,
        "sort_order": p.sort_order,
        "children": children or [],
    }


@router.get("/text-catalog/")
async def list_text_catalogs(
    session: SessionDep,
    project_id: str | None = None,
    user_id: str = Depends(get_current_user_id),
) -> list[dict[str, Any]]:
    """Catalogues visible here: the shared ones plus this project's own."""
    from sqlalchemy import or_, select

    from app.modules.neoffice.models import TextCatalog

    stmt = select(TextCatalog)
    stmt = stmt.where(
        or_(TextCatalog.project_id.is_(None), TextCatalog.project_id == project_id)
        if project_id else TextCatalog.project_id.is_(None)
    )
    rows = (await session.execute(stmt.order_by(TextCatalog.code))).scalars().all()

    # Counted with an aggregate, not `len(c.positions)`: reading the
    # relationship here lazy-loads inside the async request (MissingGreenlet).
    from sqlalchemy import func

    from app.modules.neoffice.models import TextPosition

    counts = dict(
        (str(cid), n)
        for cid, n in (await session.execute(
            select(TextPosition.catalog_id, func.count(TextPosition.id))
            .group_by(TextPosition.catalog_id)
        )).all()
    )
    return [
        {
            "id": str(c.id), "code": c.code, "name": c.name,
            "description": c.description, "standard": c.standard,
            "language": c.language,
            "project_id": str(c.project_id) if c.project_id else None,
            "position_count": counts.get(str(c.id), 0),
        }
        for c in rows
    ]


@router.post("/text-catalog/", status_code=status.HTTP_201_CREATED)
async def create_text_catalog(
    request: TextCatalogCreate,
    session: SessionDep,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Create a text catalogue (e.g. "CAN 135 — Béton et béton armé")."""
    from app.modules.neoffice.models import TextCatalog

    catalog = TextCatalog(**request.model_dump())
    session.add(catalog)
    await session.commit()
    await session.refresh(catalog)
    return {"id": str(catalog.id), "code": catalog.code, "name": catalog.name}


@router.get("/text-catalog/{catalog_id}/tree/")
async def get_text_catalog_tree(
    catalog_id: str,
    session: SessionDep,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """The catalogue as the estimator reads it: positions, each with its
    sub-positions nested underneath and in their own order."""
    from sqlalchemy import select

    from app.modules.neoffice.models import TextCatalog, TextPosition

    catalog = await session.get(TextCatalog, catalog_id)
    if catalog is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="catalog not found")

    # One query for the whole catalogue, nested in Python. Walking the ORM
    # relationship would lazy-load each level and blow up on MissingGreenlet.
    rows = (await session.execute(
        select(TextPosition)
        .where(TextPosition.catalog_id == catalog_id)
        .order_by(TextPosition.sort_order, TextPosition.code)
    )).scalars().all()

    by_parent: dict[str | None, list[Any]] = {}
    for row in rows:
        by_parent.setdefault(str(row.parent_id) if row.parent_id else None, []).append(row)

    def build(parent_key: str | None) -> list[dict[str, Any]]:
        return [
            _position_payload(row, build(str(row.id)))
            for row in by_parent.get(parent_key, [])
        ]

    return {
        "id": str(catalog.id),
        "code": catalog.code,
        "name": catalog.name,
        "standard": catalog.standard,
        "positions": build(None),
    }


@router.post("/text-catalog/{catalog_id}/positions/", status_code=status.HTTP_201_CREATED)
async def create_text_position(
    catalog_id: str,
    request: TextPositionCreate,
    session: SessionDep,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Add a position text, or a sub-position when ``parent_id`` is given."""
    from app.modules.neoffice.models import TextCatalog, TextPosition

    if await session.get(TextCatalog, catalog_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="catalog not found")

    data = request.model_dump()
    # An empty unit means "wording line" — store NULL rather than "" so the
    # measurable/non-measurable distinction stays a single check everywhere.
    if data.get("unit") is not None and not str(data["unit"]).strip():
        data["unit"] = None
    position = TextPosition(catalog_id=catalog_id, **data)
    session.add(position)
    await session.commit()
    await session.refresh(position)
    return _position_payload(position)


@router.put("/text-catalog/positions/{position_id}/")
async def update_text_position(
    position_id: str,
    request: TextPositionUpdate,
    session: SessionDep,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Patch one position. Fields left null keep their stored value."""
    from app.modules.neoffice.models import TextPosition

    position = await session.get(TextPosition, position_id)
    if position is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="position not found")

    for key, value in request.model_dump(exclude_none=True).items():
        if key == "unit" and not str(value).strip():
            value = None
        # //// NEOFFICE PATCH — an empty string detaches. ``exclude_none``
        # means a JSON null is indistinguishable from "field not sent", so
        # without this sentinel a price analysis could be attached and never
        # removed. //// END NEOFFICE PATCH
        if key == "assembly_id" and not str(value).strip():
            value = None
        setattr(position, key, value)
    await session.commit()
    await session.refresh(position)
    return _position_payload(position)


@router.delete("/text-catalog/positions/{position_id}/", status_code=status.HTTP_204_NO_CONTENT)
async def delete_text_position(
    position_id: str,
    session: SessionDep,
    user_id: str = Depends(get_current_user_id),
) -> None:
    """Delete a position (its sub-positions cascade)."""
    from app.modules.neoffice.models import TextPosition

    position = await session.get(TextPosition, position_id)
    if position is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="position not found")
    await session.delete(position)
    await session.commit()


# //// NEOFFICE PATCH — added endpoint (no upstream equivalent).
# Cédric Protti, 2026-08-20: "Ce serait bien de pouvoir déplacer les positions
# (comme dans le devis) pour pouvoir changer l'ordre si on crée une nouvelle
# position." A new position lands at the end; a CAN chapter has an order that
# matters to whoever reads the estimate.
class ReorderTextPositionsRequest(BaseModel):
    #: Positions in their new order. Only rows sharing one parent are accepted:
    #: reordering across levels is a move, not a sort, and needs its own gesture.
    position_ids: list[str]


@router.post("/text-catalog/{catalog_id}/reorder/")
async def reorder_text_positions(
    catalog_id: str,
    request: ReorderTextPositionsRequest,
    session: SessionDep,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Renumber sort_order to match the order given."""
    from sqlalchemy import select

    from app.modules.neoffice.models import TextPosition

    rows = (await session.execute(
        select(TextPosition)
        .where(TextPosition.id.in_(request.position_ids))
        .where(TextPosition.catalog_id == catalog_id)
    )).scalars().all()
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="positions not found")

    parents = {str(r.parent_id) if r.parent_id else None for r in rows}
    if len(parents) > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="all positions must share the same parent",
        )

    by_id = {str(r.id): r for r in rows}
    order = 0
    for pid in request.position_ids:
        row = by_id.get(pid)
        if row is None:
            continue
        order += 1
        row.sort_order = order
    await session.commit()
    return {"reordered": order}
# //// END NEOFFICE PATCH


# //// NEOFFICE PATCH — added endpoint (no upstream equivalent).
# The other direction: a line written in the estimate becomes catalogue text.
# Cédric Protti, 2026-08-20: "Il n'est pas possible d'enregistrer dans le
# catalogue des descriptions une position, une sous-position, ou les deux […]
# depuis le devis." Wording gets written where the work is understood — in the
# estimate — and the library is what should collect it, not the other way round.
class SaveToTextCatalogRequest(BaseModel):
    catalog_id: str
    #: BOQ positions to file, in the order given. A parent lands first and its
    #: children hang under it.
    position_ids: list[str]
    #: Reuse an existing code instead of failing on a duplicate.
    overwrite: bool = False


@router.post("/text-catalog/save-from-boq/")
async def save_boq_positions_to_catalog(
    request: SaveToTextCatalogRequest,
    session: SessionDep,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """File one or more BOQ positions into a description catalogue."""
    from sqlalchemy import select

    from app.modules.boq.models import Position as BoqPosition
    from app.modules.neoffice.models import TextCatalog, TextPosition

    catalog = await session.get(TextCatalog, request.catalog_id)
    if catalog is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="catalog not found")

    rows = (await session.execute(
        select(BoqPosition).where(BoqPosition.id.in_(request.position_ids))
    )).scalars().all()
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="positions not found")
    by_id = {str(r.id): r for r in rows}
    ordered = [by_id[i] for i in request.position_ids if i in by_id]

    existing = {
        p.code: p
        for p in (await session.execute(
            select(TextPosition).where(TextPosition.catalog_id == request.catalog_id)
        )).scalars().all()
    }
    next_order = max((p.sort_order for p in existing.values()), default=0)

    # A BOQ description is one blob: first line is the title, the rest is the
    # body. That is how the catalogue splits them, and how insertion rebuilds
    # them, so a round trip through both keeps the same shape.
    created: list[str] = []
    skipped: list[str] = []
    boq_to_text: dict[str, str] = {}
    for row in ordered:
        code = (row.ordinal or "").strip()
        if not code:
            skipped.append(str(row.id))
            continue
        if code in existing and not request.overwrite:
            skipped.append(code)
            continue

        desc = (row.description or "").strip()
        head, _, tail = desc.partition("\n")
        meta = row.metadata_ or {}
        is_text = meta.get("neoffice_text_only") is True
        unit = None if is_text else ((row.unit or "").strip() or None)
        if unit == "txt":
            unit = None

        target = existing.get(code)
        if target is not None:
            target.title = head
            target.body = tail
            target.unit = unit
        else:
            next_order += 1
            parent_txt = boq_to_text.get(str(row.parent_id)) if row.parent_id else None
            target = TextPosition(
                catalog_id=request.catalog_id,
                parent_id=parent_txt,
                code=code,
                title=head,
                body=tail,
                unit=unit,
                assembly_id=meta.get("neoffice_assembly_id"),
                sort_order=next_order,
            )
            session.add(target)
            existing[code] = target
        await session.flush()
        boq_to_text[str(row.id)] = str(target.id)
        created.append(code)

    await session.commit()
    return {
        "catalog_id": request.catalog_id,
        "catalog_name": catalog.name,
        "saved": len(created),
        "codes": created,
        "skipped": skipped,
    }
# //// END NEOFFICE PATCH


# //// NEOFFICE PATCH — added endpoint (no upstream equivalent).
# Insert an explicit selection rather than a wording and everything under it.
#
# Cédric Protti, 2026-08-19: "Si nous avons besoin d'une seule sous-position,
# nous devons effacer manuellement celles qui sont en trop." Taking the whole
# CAN position is the common case, not the only one, and deleting rows to
# undo an insert is work the software created.
#
# The caller sends exactly the rows it wants, already ordered. No implicit
# children: what is checked is what lands. Quantity is deliberately absent —
# see the same feedback: "les quantités soient gérées uniquement dans la
# fenêtre du devis".
class InsertManyRequest(BaseModel):
    boq_id: str
    parent_id: str | None = None
    position_ids: list[str]
    with_assembly: bool = True
    #: Slot the rows immediately AFTER this BOQ position instead of at the top
    #: of the chapter. Cédric Protti, 2026-08-20: "les lignes s'insèrent au
    #: début du chapitre et il faut les déplacer soi-même au bon endroit".
    after_position_id: str | None = None
    #: Also insert the catalogue's own heading ("100 Installation de chantier")
    #: as a text line above the selection. Cédric Protti, 2026-08-20: "il
    #: faudrait aussi pouvoir insérer la ligne du chapitre […] comme cela nous
    #: ne sommes pas obligés d'écrire à chaque nouveau chapitre le texte depuis
    #: le bouton du devis."
    include_catalog_heading: bool = False


#//// Neoffice — where a freshly created row sits among its siblings.
#//// Our endpoints build BoqPosition rows directly, so they never went through
#//// BOQService.create_position and never got its after_position_id handling —
#//// which is why every insert landed at the top of the chapter. Same rule
#//// reimplemented here: open a gap of ``count`` slots after the anchor, and
#//// return the first free sort_order. Returns None when there is no anchor,
#//// meaning "append", which is what the caller does by default.
async def _slot_after(session: Any, boq_id: str, after_position_id: str | None, count: int) -> int | None:
    """Open ``count`` slots right after ``after_position_id``; None = append."""
    if not after_position_id:
        return None
    from sqlalchemy import select, update

    from app.modules.boq.models import Position as BoqPosition

    anchor = await session.get(BoqPosition, after_position_id)
    # A stale or cross-BOQ anchor falls back to appending rather than
    # scrambling the order of a bill it does not belong to.
    if anchor is None or str(anchor.boq_id) != str(boq_id):
        return None
    base = int(anchor.sort_order or 0)
    await session.execute(
        update(BoqPosition)
        .where(BoqPosition.boq_id == boq_id, BoqPosition.sort_order > base)
        .values(sort_order=BoqPosition.sort_order + count)
    )
    return base + 1


@router.post("/text-catalog/insert-many-into-boq/")
async def insert_text_positions_into_boq(
    request: InsertManyRequest,
    session: SessionDep,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Create one BOQ row per selected catalogue position, in catalogue order."""
    from sqlalchemy import select

    from app.modules.assemblies.models import Assembly, Component as AssemblyComponent
    from app.modules.boq.models import Position as BoqPosition
    from app.modules.neoffice.models import TextPosition

    if not request.position_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="no position selected"
        )

    rows = (await session.execute(
        select(TextPosition)
        .where(TextPosition.id.in_(request.position_ids))
        .order_by(TextPosition.code)
    )).scalars().all()
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="positions not found")

    #//// Neoffice — the catalogue the selection belongs to, for its heading.
    from app.modules.neoffice.models import TextCatalog

    catalog = await session.get(TextCatalog, rows[0].catalog_id)
    if catalog is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="catalog not found")

    #//// Neoffice — open the gap before creating, so the new rows take the
    #//// freed slots in the order the user checked them.
    #//// Neoffice — the heading takes a slot too, so the gap has to allow for it.
    heading_wanted = request.include_catalog_heading
    slot = await _slot_after(
        session, request.boq_id, request.after_position_id, len(rows) + (1 if heading_wanted else 0)
    )

    created: list[tuple[Any, Any]] = []

    #//// Neoffice — the catalogue's own heading, as a free text line above the
    #//// positions. It carries no unit and no price: it names the chapter, it
    #//// does not measure anything.
    heading_code = None
    if heading_wanted:
        heading = BoqPosition(
            boq_id=request.boq_id,
            parent_id=request.parent_id,
            ordinal=catalog.code,
            description=catalog.name,
            unit="txt",
            quantity="0",
            unit_rate="0",
            metadata_={
                "neoffice_text_only": True,
                "neoffice_text_catalog_id": str(catalog.id),
                "neoffice_text_code": catalog.code,
            },
        )
        if slot is not None:
            heading.sort_order = slot
            slot += 1
        session.add(heading)
        heading_code = catalog.code
    #//// End Neoffice
    for src in rows:
        is_wording = not (src.unit or "").strip()
        desc = "\n".join(part for part in (src.title, src.body) if part).strip()
        meta: dict[str, Any] = {
            "neoffice_text_position_id": str(src.id),
            "neoffice_text_code": src.code,
        }
        if is_wording:
            meta["neoffice_text_only"] = True
        row = BoqPosition(
            boq_id=request.boq_id,
            parent_id=request.parent_id,
            ordinal=src.code,
            description=desc,
            unit="txt" if is_wording else (src.unit or ""),
            # Zero on purpose: the estimator types the quantity in the grid,
            # where it can be seen next to the others.
            quantity="0",
            unit_rate="0",
            metadata_=meta,
        )
        if slot is not None:
            row.sort_order = slot
            slot += 1
        session.add(row)
        created.append((src, row))
    await session.flush()

    assemblies_applied = 0
    if request.with_assembly:
        for src, row in created:
            if not src.assembly_id:
                continue
            assembly = await session.get(Assembly, src.assembly_id)
            if assembly is None:
                continue
            components = (await session.execute(
                select(AssemblyComponent).where(
                    AssemblyComponent.assembly_id == src.assembly_id
                )
            )).scalars().all()
            meta = dict(row.metadata_ or {})
            meta["resources"] = [
                {
                    "description": c.description,
                    "resource_type": c.resource_type,
                    "unit": c.unit,
                    "quantity": c.quantity,
                    "unit_cost": c.unit_cost,
                    "factor": c.factor,
                }
                for c in components
            ]
            meta["neoffice_assembly_id"] = str(src.assembly_id)
            meta["neoffice_assembly_code"] = assembly.code
            row.metadata_ = meta
            row.unit_rate = str(assembly.total_rate or "0")
            if not row.unit and assembly.unit:
                row.unit = assembly.unit
            assemblies_applied += 1

    await session.commit()
    return {
        "inserted": len(created) + (1 if heading_code else 0),
        "assemblies_applied": assemblies_applied,
        "codes": ([heading_code] if heading_code else []) + [src.code for src, _ in created],
        "heading_inserted": heading_code,
    }
# //// END NEOFFICE PATCH


# //// NEOFFICE PATCH — added endpoint (no upstream equivalent).
# The catalogue → assembly link was one-way: you could see that a wording
# carries a price analysis, but from the assembly itself there was no way to
# know which catalogue texts depend on it. Editing an assembly then meant
# editing something whose blast radius you could not see.
@router.get("/text-catalog/by-assembly/{assembly_id}/")
async def text_positions_using_assembly(
    assembly_id: str,
    session: SessionDep,
    user_id: str = Depends(get_current_user_id),
) -> list[dict[str, Any]]:
    """List the catalogue positions that reference this assembly."""
    from sqlalchemy import select

    from app.modules.neoffice.models import TextCatalog, TextPosition

    rows = (await session.execute(
        select(TextPosition, TextCatalog)
        .join(TextCatalog, TextCatalog.id == TextPosition.catalog_id)
        .where(TextPosition.assembly_id == assembly_id)
        .order_by(TextPosition.code)
    )).all()
    return [
        {
            "id": str(p.id),
            "code": p.code,
            "title": p.title,
            "unit": p.unit,
            "catalog_id": str(c.id),
            "catalog_code": c.code,
            "catalog_name": c.name,
        }
        for p, c in rows
    ]
# //// END NEOFFICE PATCH


@router.post("/text-catalog/positions/{position_id}/insert-into-boq/")
async def insert_text_position_into_boq(
    position_id: str,
    request: InsertIntoBoqRequest,
    session: SessionDep,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Create a BOQ position from a catalogue text, assembly included.

    This is the payoff of the whole table: the estimator picks a wording from
    the catalogue and gets the position AND its priced recipe in one move,
    instead of retyping the text and rebuilding the assembly by hand.

    The wording travels as `title` + `body` joined with a newline, because a CAN
    text is written across several lines and the BOQ description column now
    renders them (see the remark-line / multi-line work).
    """
    from app.modules.assemblies.models import Assembly, Component as AssemblyComponent
    from app.modules.boq.models import Position as BoqPosition
    from app.modules.neoffice.models import TextPosition

    position = await session.get(TextPosition, position_id)
    if position is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="position not found")

    # //// NEOFFICE PATCH — inserting a wording line, and its sub-positions with it.
    #
    # Cédric, 2026-08-18: "Impossible d'insérer le libellé. Le sous-article seul
    # est inutile dans le devis." He is right, and the design was wrong.
    #
    # A CAN page splits one item in two. The wording carries the verb —
    # "Fourniture et mise en place d'un béton de propreté sur fond de
    # terrassement" — and the sub-position carries only what varies: "Sous
    # radier, ép. 5 cm". Insert the sub-position alone and the estimate says
    # what thickness, never what work. So the wording is not decoration to be
    # skipped; it is half the sentence.
    #
    # It could not be inserted because it has no unit, and a BOQ row demands
    # one. The free text line built on 2026-08-14 solves exactly that: a filler
    # unit the screen hides plus a marker in metadata. A wording now inserts as
    # one of those, and its measurable children follow underneath, which also
    # answers "peut-on insérer plusieurs lignes en même temps" for the case that
    # actually occurs — taking a whole CAN position.
    is_wording = not (position.unit or "").strip()

    def _row(src: "TextPosition", parent_id: str | None, as_text: bool) -> "BoqPosition":
        desc = "\n".join(part for part in (src.title, src.body) if part).strip()
        meta: dict[str, Any] = {
            "neoffice_text_position_id": str(src.id),
            "neoffice_text_code": src.code,
        }
        if as_text:
            # Same contract as the toolbar's "Ligne libre": filler unit, marker,
            # zeroes, so it weighs nothing and shows nothing but its text.
            meta["neoffice_text_only"] = True
        return BoqPosition(
            boq_id=request.boq_id,
            parent_id=parent_id,
            ordinal=request.ordinal if (src is position and request.ordinal) else src.code,
            description=desc,
            unit="txt" if as_text else (src.unit or ""),
            quantity="0" if as_text else request.quantity,
            unit_rate="0",
            metadata_=meta,
        )

    #//// Neoffice — same placement rule as the batch insert. A wording brings
    #//// its children, so the gap has to cover them too, not just the one row.
    _child_guess = 1 + (len(position.children) if getattr(position, "children", None) else 0)
    _slot = await _slot_after(session, request.boq_id, request.after_position_id, _child_guess)

    new_position = _row(position, request.parent_id, as_text=is_wording)
    if _slot is not None:
        new_position.sort_order = _slot
        _slot += 1
    session.add(new_position)
    await session.flush()

    # (catalogue row, created BOQ row) pairs. The assembly copy below runs over
    # this list rather than on ``new_position`` alone: a wording carries no
    # assembly of its own, its measurable children do — so keying the copy on
    # the parent silently dropped every price analysis the sub-positions had.
    created: list[tuple[Any, Any]] = [(position, new_position)]

    # A wording on its own is what the client called useless. Bring the
    # measurable children across in catalogue order, under the same parent so
    # they read as one block.
    children_inserted = 0
    if is_wording:
        from sqlalchemy import select as _select

        children = (await session.execute(
            _select(TextPosition)
            .where(TextPosition.parent_id == position.id)
            .order_by(TextPosition.sort_order, TextPosition.code)
        )).scalars().all()
        for child in children:
            if not (child.unit or "").strip():
                continue  # a nested wording: leave it, one level is the real case
            child_row = _row(child, request.parent_id, as_text=False)
            if _slot is not None:
                child_row.sort_order = _slot
                _slot += 1
            session.add(child_row)
            created.append((child, child_row))
            children_inserted += 1
        if children_inserted:
            await session.flush()
    # //// END NEOFFICE PATCH

    # //// NEOFFICE PATCH — the price analysis is now optional, and it is
    # applied per created row instead of only to the one the user clicked.
    #
    # Two things were wrong. The copy keyed on ``position.assembly_id``, but a
    # wording never has an assembly — its measurable children do. So inserting
    # a whole CAN position dropped every analysis the sub-positions carried
    # (135.046.01 has one). And there was no way to decline the copy, which is
    # precisely what the client asked for: "insérés avec ou sans l'analyse de
    # prix" — an estimator who prices by hand does not want ours imposed.
    # //// END NEOFFICE PATCH
    resources: list[dict[str, Any]] = []
    assemblies_applied = 0
    if request.with_assembly:
        from sqlalchemy import select

        for src, row in created:
            if not src.assembly_id:
                continue
            assembly = await session.get(Assembly, src.assembly_id)
            if assembly is None:
                continue
            components = (await session.execute(
                select(AssemblyComponent).where(
                    AssemblyComponent.assembly_id == src.assembly_id
                )
            )).scalars().all()
            row_resources = [
                {
                    "description": c.description,
                    "resource_type": c.resource_type,
                    "unit": c.unit,
                    "quantity": c.quantity,
                    "unit_cost": c.unit_cost,
                    "factor": c.factor,
                }
                for c in components
            ]
            meta = dict(row.metadata_ or {})
            meta["resources"] = row_resources
            meta["neoffice_assembly_id"] = str(src.assembly_id)
            meta["neoffice_assembly_code"] = assembly.code
            row.metadata_ = meta
            row.unit_rate = str(assembly.total_rate or "0")
            if not row.unit and assembly.unit:
                row.unit = assembly.unit
            assemblies_applied += 1
            if row is new_position:
                resources = row_resources

    await session.commit()
    await session.refresh(new_position)
    return {
        "boq_position_id": str(new_position.id),
        "ordinal": new_position.ordinal,
        "description": new_position.description,
        "unit": new_position.unit,
        "unit_rate": new_position.unit_rate,
        "assembly_applied": assemblies_applied > 0,
        "resources_copied": len(resources),
        # //// NEOFFICE PATCH — how many rows actually received an analysis,
        # so the toast can be honest when the children carried them and the
        # clicked wording did not. //// END NEOFFICE PATCH
        "assemblies_applied": assemblies_applied,
        # //// NEOFFICE PATCH — so the toast can say what actually landed:
        # a wording brings its measurable children with it.
        "is_wording": is_wording,
        "children_inserted": children_inserted,
        # //// END NEOFFICE PATCH
    }
# //// END NEOFFICE PATCH


# ── Site measurements ────────────────────────────────────────────────────────
# What the site actually built, against the position that priced it. See the
# class note in models.py for why this does not reuse upstream's
# oe_variations_site_measurement.


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def _measurement_or_404(session: Any, measurement_id: str) -> Any:
    from app.modules.neoffice.models import SiteMeasurement

    row = await session.get(SiteMeasurement, uuid.UUID(str(measurement_id)))
    if row is None:
        raise HTTPException(status_code=404, detail="Measurement not found")
    return row


@router.get("/site-measurements/")
async def list_site_measurements(
    session: SessionDep,
    user_id: str = Depends(get_current_user_id),
    boq_position_id: str | None = None,
    project_id: str | None = None,
    status_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Measurements for one position, or for a whole project.

    Ordered oldest first: a position is measured several times as the work
    advances, and the story reads forwards.
    """
    from sqlalchemy import select

    from app.modules.neoffice.models import SiteMeasurement

    stmt = select(SiteMeasurement)
    if boq_position_id:
        stmt = stmt.where(SiteMeasurement.boq_position_id == uuid.UUID(boq_position_id))
    if project_id:
        stmt = stmt.where(SiteMeasurement.project_id == uuid.UUID(project_id))
    if status_filter:
        stmt = stmt.where(SiteMeasurement.status == status_filter)
    stmt = stmt.order_by(SiteMeasurement.measured_at.asc().nulls_last(),
                         SiteMeasurement.created_at.asc())

    rows = (await session.execute(stmt)).scalars().all()
    return [_measurement_dict(r) for r in rows]


def _measurement_dict(row: Any) -> dict[str, Any]:
    """Serialise one measurement. Decimals as strings — never floats."""
    return {
        "id": str(row.id),
        "boq_position_id": str(row.boq_position_id),
        "project_id": str(row.project_id) if row.project_id else None,
        "measured_quantity": str(row.measured_quantity),
        "unit": row.unit,
        "location": row.location,
        "notes": row.notes,
        "photos": row.photos or [],
        "measured_at": row.measured_at,
        "measured_by": row.measured_by,
        "agreed_at": row.agreed_at,
        "agreed_by": row.agreed_by,
        "signature_ref": row.signature_ref,
        "status": row.status,
        "invoiced_at": row.invoiced_at,
        "invoice_ref": row.invoice_ref,
    }


@router.post("/site-measurements/", status_code=status.HTTP_201_CREATED)
async def create_site_measurement(
    request: SiteMeasurementCreate,
    session: SessionDep,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Record a quantity measured on site against a priced position.

    The unit and the project are copied from the position when the caller does
    not give them: the phone that records "49" should not have to know either,
    and a unit copied now cannot be reinterpreted by a later edit of the
    estimate.
    """
    from app.modules.boq.models import BOQ, Position as BOQPosition
    from app.modules.neoffice.models import SiteMeasurement

    position = await session.get(BOQPosition, uuid.UUID(request.boq_position_id))
    if position is None:
        raise HTTPException(status_code=404, detail="BOQ position not found")

    project_id = None
    boq = await session.get(BOQ, position.boq_id) if position.boq_id else None
    if boq is not None:
        project_id = boq.project_id

    row = SiteMeasurement(
        boq_position_id=position.id,
        project_id=project_id,
        measured_quantity=request.measured_quantity,
        unit=request.unit or (position.unit or ""),
        location=request.location,
        notes=request.notes,
        photos=list(request.photos or []),
        measured_at=request.measured_at or _now_iso(),
        measured_by=request.measured_by or str(user_id) if user_id else None,
        status="draft",
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _measurement_dict(row)


@router.patch("/site-measurements/{measurement_id}")
async def update_site_measurement(
    measurement_id: str,
    request: SiteMeasurementUpdate,
    session: SessionDep,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Correct a measurement that has not been agreed yet.

    Refused once agreed: it has been signed, and an invoice may already rest on
    it. The correction of a signed measurement is a new measurement — the way
    an accountant corrects, by writing another line rather than erasing one.
    """
    row = await _measurement_or_404(session, measurement_id)
    if row.status != "draft":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "measurement_locked",
                "status": row.status,
                "message": (
                    "An agreed measurement cannot be edited. Record a new "
                    "measurement instead."
                ),
            },
        )

    for field, value in request.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(row, field, value)
    await session.commit()
    await session.refresh(row)
    return _measurement_dict(row)


@router.post("/site-measurements/{measurement_id}/agree")
async def agree_site_measurement(
    measurement_id: str,
    request: SiteMeasurementAgree,
    session: SessionDep,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """The contradictory half: the quantity is agreed and becomes billable.

    Idempotent — agreeing twice keeps the first agreement. The date of an
    agreement is evidence, and evidence does not get rewritten by a second tap
    on a phone.
    """
    row = await _measurement_or_404(session, measurement_id)
    if row.agreed_at:
        return _measurement_dict(row)

    row.agreed_at = _now_iso()
    row.agreed_by = request.agreed_by or (str(user_id) if user_id else None)
    row.signature_ref = request.signature_ref or row.signature_ref
    row.status = "agreed"
    await session.commit()
    await session.refresh(row)
    return _measurement_dict(row)


@router.delete("/site-measurements/{measurement_id}", status_code=204)
async def delete_site_measurement(
    measurement_id: str,
    session: SessionDep,
    user_id: str = Depends(get_current_user_id),
) -> None:
    """Delete a draft measurement. An agreed one is kept, like any signed record."""
    row = await _measurement_or_404(session, measurement_id)
    if row.status != "draft":
        raise HTTPException(
            status_code=409,
            detail={"error": "measurement_locked", "status": row.status},
        )
    await session.delete(row)
    await session.commit()


def _dec(value: Any) -> Decimal:
    """Coerce a BOQ money/quantity column to Decimal.

    ``BOQPosition.quantity``, ``.unit_rate`` and ``.total`` are String columns
    upstream, not Numeric. They hold "", "0", "12.5", and occasionally a
    localised or plainly broken value. Comparing or summing them as text is the
    trap that once made a price band read "9" as greater than "42"; every read
    goes through here.
    """
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    text = str(value).strip().replace(" ", "").replace("'", "").replace(" ", "")
    if not text:
        return Decimal("0")
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return Decimal("0")


@router.get("/site-measurements/variance/")
async def position_variance_report(
    session: SessionDep,
    boq_id: str,
    user_id: str = Depends(get_current_user_id),
    agreed_only: bool = True,
) -> dict[str, Any]:
    """Priced against built, position by position.

    This is the screen an estimator asks for: what each position priced, what
    the site measured, the gap, and what the measured quantity is worth.

    ``amount`` is the built quantity at the position's own unit rate, not a
    share of the priced total. In a remeasured contract those two differ the
    moment the quantity does, and it is the first one that goes on an invoice.

    ``agreed_only`` (the default) counts only measurements that carry a
    signature. The unsigned ones are still reported in ``measurement_count`` so
    a foreman can see what is waiting for the client, but they do not move the
    money.
    """
    from sqlalchemy import select

    from app.modules.boq.models import Position as BOQPosition
    from app.modules.neoffice.models import SiteMeasurement

    positions = (
        await session.execute(
            select(BOQPosition)
            .where(BOQPosition.boq_id == uuid.UUID(boq_id))
            .order_by(BOQPosition.ordinal)
        )
    ).scalars().all()
    if not positions:
        raise HTTPException(status_code=404, detail="BOQ not found or empty")

    by_position = {p.id: p for p in positions}
    measurements = (
        await session.execute(
            select(SiteMeasurement).where(
                SiteMeasurement.boq_position_id.in_(list(by_position.keys()))
            )
        )
    ).scalars().all()

    tally: dict[uuid.UUID, dict[str, Any]] = {}
    for m in measurements:
        slot = tally.setdefault(
            m.boq_position_id, {"qty": Decimal("0"), "count": 0, "agreed": 0}
        )
        slot["count"] += 1
        if m.agreed_at:
            slot["agreed"] += 1
        if m.agreed_at or not agreed_only:
            slot["qty"] += _dec(m.measured_quantity)

    rows: list[dict[str, Any]] = []
    priced_total = measured_total = priced_total_measured = Decimal("0")
    positions_measured = 0

    for p in positions:
        slot = tally.get(p.id)
        # A heading line carries no unit and no quantity; it is not measurable
        # and would only add empty rows to the comparison.
        if not (p.unit or "").strip() and not slot:
            continue

        priced_qty = _dec(p.quantity)
        rate = _dec(p.unit_rate)
        built_qty = slot["qty"] if slot else Decimal("0")
        variance = built_qty - priced_qty
        amount = built_qty * rate

        if slot:
            positions_measured += 1
            # Only measured positions feed the comparable total. Summing the
            # whole bill against a handful of measured lines produces a
            # headline gap that is arithmetically true and factually absurd
            # ("you are 1.27M under" on day one), which is worse than no
            # figure at all.
            priced_total_measured += priced_qty * rate
        priced_total += priced_qty * rate
        measured_total += amount

        variance_percent: float | None = None
        if priced_qty != 0:
            variance_percent = float(
                (variance / priced_qty * Decimal("100")).quantize(Decimal("0.001"))
            )

        if variance > 0:
            state = "over_run"
        elif variance < 0:
            state = "under_run"
        else:
            state = "on_target"

        rows.append({
            "boq_position_id": str(p.id),
            "ordinal": p.ordinal,
            "description": p.description,
            "unit": p.unit or "",
            "priced_quantity": str(priced_qty),
            "measured_quantity": str(built_qty),
            "variance": str(variance),
            "variance_percent": variance_percent,
            "status": state,
            "unit_rate": str(rate),
            "amount": str(amount),
            "measurement_count": slot["count"] if slot else 0,
            "agreed_count": slot["agreed"] if slot else 0,
        })

    return {
        "boq_id": boq_id,
        "agreed_only": agreed_only,
        "rows": rows,
        # The whole bill, for context: what the estimate is worth.
        "priced_total": str(priced_total),
        # The two figures that may be compared with each other: what the
        # measured positions were priced at, and what they measured.
        "priced_total_measured": str(priced_total_measured),
        "measured_total": str(measured_total),
        "variance_total": str(measured_total - priced_total_measured),
        "positions_measured": positions_measured,
        "positions_total": len(rows),
    }

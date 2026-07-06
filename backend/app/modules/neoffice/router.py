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
# //// END NEOFFICE PATCH

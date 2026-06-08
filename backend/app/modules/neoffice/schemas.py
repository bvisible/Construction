"""NEOFFICE FILE — Owned 100% by Neoservice. Not from upstream OpenConstructionERP.

Pydantic schemas for the Neoffice extensions module — RoomPlan import/export.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class RoomPlanImportRequest(BaseModel):
    """Body for POST /api/v1/neoffice/bim/import-roomplan/.

    The `scan` field carries the raw CapturedRoom JSON exported by Apple
    RoomPlan (`ExportType.Parametric`). The backend parses it and creates
    one BIMModel + N BIMElements, skipping the DDC IfcExporter pipeline.
    """

    project_id: UUID = Field(..., description="Target project UUID")
    name: str = Field(..., min_length=1, max_length=255)
    scan: dict[str, Any] = Field(
        ...,
        description=(
            "Raw RoomPlan CapturedRoom JSON. Expected top-level keys: "
            "walls, doors, windows, openings, objects, story (optional), "
            "version, identifier."
        ),
    )
    device_info: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional metadata about the capture device (iPhone model, "
            "iOS version, scan duration ms, app version). Stored in "
            "BIMModel.metadata_ for audit."
        ),
    )


class RoomPlanImportResponse(BaseModel):
    """Response after a successful RoomPlan import."""

    model_id: UUID
    name: str
    status: str
    element_count: int
    storey_count: int
    bounding_box: dict[str, list[float]] | None = None


class ScheduleProgressBridgeRequest(BaseModel):
    """Body for POST /api/v1/neoffice/bridge/progress/ from the Frappe bridge.

    The mirrored Activity on the Frappe side reports execution progress back
    to Neoconstruction. A Work Order source is resolved to its parent
    Schedule Activity (whose id is the ScheduleProgressEntry task_id).
    """

    neoconstruction_source_type: str = Field(
        ..., description='"Work Order" or "Schedule Activity"'
    )
    neoconstruction_source_id: UUID = Field(
        ..., description="Upstream object UUID (Work Order or Schedule Activity)"
    )
    progress_percent: float = Field(..., ge=0.0, le=100.0)
    notes: str | None = Field(default=None, max_length=4000)
    geolocation: dict[str, Any] | None = Field(default=None)
    actual_start_date: str | None = Field(default=None, description="ISO date YYYY-MM-DD")
    actual_finish_date: str | None = Field(default=None, description="ISO date YYYY-MM-DD")


class FieldReportWorkforceEntry(BaseModel):
    """One workforce line of a consolidated daily report."""

    trade: str = Field(..., max_length=100)
    count: int = Field(default=1, ge=0)
    hours: float = Field(default=0.0, ge=0.0)


class FieldReportFromActivitiesRequest(BaseModel):
    """Body for POST /api/v1/neoffice/bridge/fieldreports/from-activities/.

    A daily consolidation of Frappe Activities for one Neoconstruction
    project. Upserts a draft FieldReport keyed on (project, report_date).
    """

    neoconstruction_project_id: UUID
    report_date: date
    work_performed: str = Field(default="", max_length=10000)
    workforce: list[FieldReportWorkforceEntry] = Field(default_factory=list)
    equipment_on_site: list[str] = Field(default_factory=list)
    materials_used: list[str] = Field(default_factory=list)


# ── Takeoff plan vision analysis ──────────────────────────────────────────────


class PlanVisionRequest(BaseModel):
    """Body for POST /api/v1/neoffice/takeoff/analyze-vision/.

    Runs a multimodal (vision) analysis of one page of an uploaded takeoff PDF:
    the page is rendered to an image and read by the vision model, which returns
    the rooms, elements and the drawing scale.
    """

    document_id: str = Field(..., description="Takeoff document UUID")
    page: int = Field(default=1, ge=1, description="1-based page number to analyse")
    scale_override: float | None = Field(
        default=None,
        gt=0,
        description=(
            "Optional manual scale ratio (e.g. 50 for 1:50) that overrides the "
            "scale read off the plan when deriving the pixel-per-metre calibration."
        ),
    )


class PlanVisionRoom(BaseModel):
    """One room detected on the plan.

    ``bbox`` is ``[x0, y0, x1, y1]`` normalised in [0, 1] relative to the page
    (origin top-left). Multiply by the page dimensions (PDF points) to obtain
    measurement points in the takeoff drawing frame.
    """

    name: str
    zone: str | None = None
    usage: str | None = None
    bbox: list[float] | None = None
    approx_area_m2: float | None = None


class PlanVisionElement(BaseModel):
    """A notable element detected on the plan (door, window, wall, other).

    ``bbox`` is normalised in [0, 1] relative to the page (see PlanVisionRoom).
    """

    type: str
    label: str | None = None
    bbox: list[float] | None = None


class PlanVisionResponse(BaseModel):
    """Structured result of the vision analysis of a plan page.

    ``scale_pixels_per_unit`` is the takeoff calibration in **PDF points per
    metre** (matches the frontend ``presetScale()``), derived from the scale
    read off the plan. ``page_width_pt``/``page_height_pt`` are the page
    dimensions in PDF points; the frontend multiplies the normalised bboxes by
    them to pre-draw the detected rooms aligned with the drawing.
    """

    document_id: str
    page: int
    plan_type: str | None = None
    scale_label: str | None = None
    scale_ratio: float | None = None
    scale_pixels_per_unit: float | None = None
    page_width_pt: float
    page_height_pt: float
    image_width: int
    image_height: int
    rooms: list[PlanVisionRoom] = Field(default_factory=list)
    elements: list[PlanVisionElement] = Field(default_factory=list)
    tokens_used: int = 0


# ── Takeoff vector-geometry room detection (Piste B) ──────────────────────────


class RoomDetectionRequest(BaseModel):
    """Body for POST /api/v1/neoffice/takeoff/detect-rooms/.

    Detects room polygons from the PDF vector layer (walls). ``scale_override``
    sets the drawing scale ratio (e.g. 50 for 1:50); when omitted the scale is
    read off the plan via the vision model.
    """

    document_id: str = Field(..., description="Takeoff document UUID")
    page: int = Field(default=1, ge=1, description="1-based page number")
    scale_override: float | None = Field(default=None, gt=0)


class DetectedRoom(BaseModel):
    """One room polygon detected from the vectors.

    ``polygon`` is a list of [x, y] points normalised in [0, 1] of the page
    (multiply by the page dimensions / pdfjs viewport to draw).
    """

    name: str | None = None
    polygon: list[list[float]]
    area_m2: float | None = None


class RoomDetectionResponse(BaseModel):
    """Structured result of the vector room detection."""

    document_id: str
    page: int
    page_width_pt: float
    page_height_pt: float
    scale_ratio: float | None = None
    scale_pixels_per_unit: float | None = None
    rooms: list[DetectedRoom] = Field(default_factory=list)
    stats: dict[str, int] = Field(default_factory=dict)

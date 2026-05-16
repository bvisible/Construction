"""NEOFFICE FILE — Owned 100% by Neoservice. Not from upstream OpenConstructionERP.

Pydantic schemas for the Neoffice extensions module — RoomPlan import/export.
"""

from __future__ import annotations

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

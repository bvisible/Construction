"""Pydantic schemas for the costmodel_typed module — request/response models.

Money fields follow v3 §10: Decimal in / Decimal-as-string out in JSON, persisted
as strings in the database.
"""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer


def _serialise_decimal(v: Decimal | None) -> str | None:
    """Decimal → plain decimal string for JSON. NULL passes through."""
    if v is None:
        return None
    if not isinstance(v, Decimal):
        try:
            v = Decimal(str(v))
        except (InvalidOperation, ValueError):
            return "0"
    if not v.is_finite():
        return "0"
    return format(v, "f")


# ── AssemblyComponent schemas ────────────────────────────────────────────────


class AssemblyComponentCreate(BaseModel):
    """Create a typed component for a CostLine."""

    model_config = ConfigDict(str_strip_whitespace=True)

    cost_line_id: UUID | None = None  # set from URL path
    sub_block_label: str = ""
    component_type: str = Field(
        ...,
        description=(
            "One of: labor, fg_admin, machine, material, internal_loc, "
            "external_loc, external_margin, subcontractor, subcontractor_margin, "
            "misc, transport"
        ),
    )
    description: str = ""
    unit: str | None = None
    unit_rate: Decimal = Decimal("0")
    discount: Decimal | None = None
    qty: Decimal | None = None
    yield_per_hour: Decimal | None = None
    amount: Decimal = Decimal("0")
    sort_order: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_serializer(
        "unit_rate", "discount", "qty", "yield_per_hour", "amount", when_used="json"
    )
    def _ser(self, v: Decimal | None) -> str | None:
        return _serialise_decimal(v)


class AssemblyComponentUpdate(BaseModel):
    """Partial update of a typed component."""

    model_config = ConfigDict(str_strip_whitespace=True)

    sub_block_label: str | None = None
    component_type: str | None = None
    description: str | None = None
    unit: str | None = None
    unit_rate: Decimal | None = None
    discount: Decimal | None = None
    qty: Decimal | None = None
    yield_per_hour: Decimal | None = None
    amount: Decimal | None = None
    sort_order: int | None = None
    metadata: dict[str, Any] | None = None

    @field_serializer(
        "unit_rate", "discount", "qty", "yield_per_hour", "amount", when_used="json"
    )
    def _ser(self, v: Decimal | None) -> str | None:
        return _serialise_decimal(v)


class AssemblyComponentResponse(BaseModel):
    """Typed component returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    cost_line_id: UUID
    sub_block_label: str
    component_type: str
    description: str
    unit: str | None = None
    unit_rate: Decimal = Decimal("0")
    discount: Decimal | None = None
    qty: Decimal | None = None
    yield_per_hour: Decimal | None = None
    amount: Decimal = Decimal("0")
    sort_order: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict, alias="metadata_")
    created_at: datetime
    updated_at: datetime

    @field_serializer(
        "unit_rate", "discount", "qty", "yield_per_hour", "amount", when_used="json"
    )
    def _ser(self, v: Decimal | None) -> str | None:
        return _serialise_decimal(v)


# ── YieldLibraryEntry schemas ────────────────────────────────────────────────


class YieldLibraryEntryCreate(BaseModel):
    """Create a yield library entry."""

    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: UUID | None = None  # NULL = global
    task_label: str = Field(..., min_length=1, max_length=255)
    unit: str = ""
    yield_per_hour: Decimal = Decimal("0")
    source: str = "manual"  # 'import' / 'calibrated' / 'manual'
    source_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_serializer("yield_per_hour", when_used="json")
    def _ser(self, v: Decimal | None) -> str | None:
        return _serialise_decimal(v)


class YieldLibraryEntryUpdate(BaseModel):
    """Partial update of a yield library entry."""

    model_config = ConfigDict(str_strip_whitespace=True)

    task_label: str | None = None
    unit: str | None = None
    yield_per_hour: Decimal | None = None
    source: str | None = None
    source_ref: str | None = None
    last_calibrated_at: datetime | None = None
    metadata: dict[str, Any] | None = None

    @field_serializer("yield_per_hour", when_used="json")
    def _ser(self, v: Decimal | None) -> str | None:
        return _serialise_decimal(v)


class YieldLibraryEntryResponse(BaseModel):
    """Yield library entry returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    project_id: UUID | None = None
    task_label: str
    unit: str
    yield_per_hour: Decimal = Decimal("0")
    source: str
    source_ref: str | None = None
    last_calibrated_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, alias="metadata_")
    created_at: datetime
    updated_at: datetime

    @field_serializer("yield_per_hour", when_used="json")
    def _ser(self, v: Decimal | None) -> str | None:
        return _serialise_decimal(v)

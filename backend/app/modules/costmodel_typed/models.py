"""Typed Cost Components & Yield Library ORM models.

Tables:
    oe_assembly_component — typed sub-block component attached to a CostLine
    oe_yield_library — productivity rates (U/h) library, project-scoped or global
"""

import uuid

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import GUID, Base

# Component type enum kept as a plain string column for forward-compat —
# matches the typing produced by the Phase 1 parser of the Protti corpus.
COMPONENT_TYPES = (
    "labor",
    "fg_admin",
    "machine",
    "material",
    "internal_loc",
    "external_loc",
    "external_margin",
    "subcontractor",
    "subcontractor_margin",
    "misc",
    "transport",
)


class AssemblyComponent(Base):
    """A typed sub-block component attached to a Cost Spine CostLine.

    A CostLine (one scope item) is internally decomposed into sub-blocks
    (e.g. ``a)`` fouille, ``b)`` béton, ``c)`` coffrage) and each sub-block
    is a list of typed components. The ``component_type`` enum lets the
    pricing engine and downstream listeners apply the right rule (labor →
    hourly cost × hours/yield, machine → VLOOKUP fleet rate, material →
    price × (1 − discount) × qty, etc.) without inspecting the description.

    ``yield_per_hour`` is only meaningful for ``type='labor'`` rows —
    productivity in target units per labor-hour. NULL otherwise.
    """

    __tablename__ = "oe_assembly_component"
    __table_args__ = (
        Index("ix_oe_assembly_component_cost_line", "cost_line_id"),
        Index("ix_oe_assembly_component_type", "component_type"),
    )

    cost_line_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_costmodel_cost_line.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sub_block_label: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        server_default="",
        doc="Free-form sub-block grouping label, e.g. 'a) Fouille en rigole'",
    )
    component_type: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        doc="One of COMPONENT_TYPES — drives the pricing rule",
    )
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    unit_rate: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default="0",
        doc="Money — Decimal-as-string (v3 §10)",
    )
    discount: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        doc="Discount rate 0-1, Decimal-as-string. NULL = no discount.",
    )
    qty: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        doc="Quantity of the component, Decimal-as-string. NULL = derived from formula.",
    )
    yield_per_hour: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        doc="Productivity in target units per labor-hour. NULL except for labor.",
    )
    amount: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default="0",
        doc="Computed amount for this component, Decimal-as-string.",
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
        doc=(
            "Reserved for downstream-module extensions. Convention: set "
            "``extension_owner`` to the originating module name (e.g. "
            "``oe_protti``) so cross-extension conflicts can be detected."
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<AssemblyComponent {self.component_type} "
            f"line={self.cost_line_id} amount={self.amount}>"
        )


class YieldLibraryEntry(Base):
    """A productivity reference entry (U/h) for a labor task.

    Entries are either project-scoped (``project_id`` set) or global
    (``project_id`` NULL) so calibrated yields gleaned from one project
    can be re-used as defaults elsewhere. ``source`` distinguishes how
    the value was obtained (imported from a parsed devis, calibrated
    against real-world progress, or entered manually).
    """

    __tablename__ = "oe_yield_library"
    __table_args__ = (
        Index("ix_oe_yield_library_project", "project_id"),
        Index("ix_oe_yield_library_task_label", "task_label"),
    )

    project_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        doc="NULL = global cross-project entry",
    )
    task_label: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="",
        doc="Target unit for the productivity rate (m2, m3, m1, kg, pce, ...)",
    )
    yield_per_hour: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default="0",
        doc="Decimal-as-string — units produced per labor-hour",
    )
    source: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        server_default="manual",
        doc="One of: 'import', 'calibrated', 'manual'",
    )
    source_ref: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        doc="Free-form provenance string, e.g. 'art#002, sous-bloc c)'",
    )
    last_calibrated_at: Mapped[str | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Wall-clock time of the latest calibration pass",
    )
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    def __repr__(self) -> str:
        return (
            f"<YieldLibraryEntry {self.task_label} "
            f"({self.unit}/h={self.yield_per_hour})>"
        )

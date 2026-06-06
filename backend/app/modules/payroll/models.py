# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""Payroll ORM models.

Tables:
    oe_payroll_batch  - one draft/approved pay run per (project, period)
    oe_payroll_entry  - one line per (worker, date): hours x rate = amount

Money is stored Decimal-as-string (the project convention) and is always
expressed in the project base currency - the generator converts each
source row's native ``hours x cost_rate`` to base via the project fx_rates
before it lands here, so a batch never blends currencies.
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import GUID, Base


class PayrollBatch(Base):
    """A draft pay run aggregating field labour for a project + period.

    A batch is created in ``draft`` status by the generator. Totals
    (``total_hours`` / ``total_amount``) are denormalised sums of the
    batch's entries so the list view needs no per-row aggregation.
    """

    __tablename__ = "oe_payroll_batch"
    __table_args__ = (Index("ix_oe_payroll_batch_project_status", "project_id", "status"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Human label, e.g. "Week 2026-W23" or an explicit date range. Free-form
    # so the generator can name a batch by whatever period it covered.
    period_label: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    # ISO YYYY-MM-DD bounds of the labour aggregated into this batch.
    period_start: Mapped[str | None] = mapped_column(String(20), nullable=True)
    period_end: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # draft / submitted / approved / posted - free-form on the DB side; the
    # service FSM is authoritative. New batches always start ``draft``
    # (human-confirmed). The lifecycle is:
    #   draft     -> generated, manager reviews/edits
    #   submitted -> sent for approval (no money moved yet)
    #   approved  -> labour cost posted to the cost-spine budget line
    #   posted    -> approved AND handed to the finance GL (terminal)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="draft",
        server_default="draft",
        index=True,
    )
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="", server_default="")
    total_hours: Mapped[str] = mapped_column(String(50), nullable=False, default="0", server_default="0")
    total_amount: Mapped[str] = mapped_column(String(50), nullable=False, default="0", server_default="0")
    entry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    created_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    # ── Lifecycle audit (FSM transitions) ────────────────────────────────
    # Each transition stamps its own timestamp + actor so the batch carries a
    # full audit trail. Plain UUIDs (no FK) - the acting user may be archived
    # while the pay history survives.
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    posted_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    # Finance ledger transaction reference written when the batch is posted to
    # the GL. NULL until the batch reaches ``posted``; the value doubles as the
    # idempotency guard so a re-post never writes a second journal.
    gl_transaction_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug repr
        return f"<PayrollBatch {self.period_label} ({self.status}) {self.total_amount}>"


class PayrollEntry(Base):
    """A single payroll line: one worker, one date, hours x rate = amount.

    ``rate`` and ``amount`` are in the batch currency (project base). The
    ``resource_id`` link is optional - free-text ``worker_type`` rows
    (e.g. "carpenter" with no resource record) still produce an entry using
    whatever rate the source row carried.
    """

    __tablename__ = "oe_payroll_entry"
    __table_args__ = (Index("ix_oe_payroll_entry_batch_date", "batch_id", "work_date"),)

    batch_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_payroll_batch.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Optional link to a resource record (person/crew). Plain UUID, no FK -
    # the resource may be archived while the pay history survives.
    resource_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True, index=True)
    worker: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    work_date: Mapped[str | None] = mapped_column(String(20), nullable=True, doc="ISO YYYY-MM-DD")
    hours: Mapped[str] = mapped_column(String(50), nullable=False, default="0", server_default="0")
    rate: Mapped[str] = mapped_column(String(50), nullable=False, default="0", server_default="0")
    amount: Mapped[str] = mapped_column(String(50), nullable=False, default="0", server_default="0")
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="", server_default="")
    source: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="fieldreport",
        server_default="fieldreport",
        doc="fieldreport | field_diary",
    )
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug repr
        return f"<PayrollEntry {self.worker} {self.work_date} {self.hours}h={self.amount}>"

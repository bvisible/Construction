# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""Async SQLAlchemy repositories for the Payroll module."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payroll.models import PayrollBatch, PayrollEntry


class PayrollBatchRepository:
    """Data access for PayrollBatch."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, batch: PayrollBatch) -> PayrollBatch:
        self.session.add(batch)
        await self.session.flush()
        await self.session.refresh(batch)
        return batch

    async def get_by_id(self, batch_id: uuid.UUID) -> PayrollBatch | None:
        return await self.session.get(PayrollBatch, batch_id)

    async def list_for_project(
        self,
        project_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[PayrollBatch], int]:
        base = select(PayrollBatch).where(PayrollBatch.project_id == project_id)
        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self.session.execute(count_stmt)).scalar_one()
        stmt = base.order_by(PayrollBatch.created_at.desc()).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), int(total)

    async def update_fields(self, batch_id: uuid.UUID, **fields: Any) -> None:
        batch = await self.session.get(PayrollBatch, batch_id)
        if batch is None:
            return
        for key, value in fields.items():
            attr = "metadata_" if key == "metadata" else key
            setattr(batch, attr, value)
        await self.session.flush()


class PayrollEntryRepository:
    """Data access for PayrollEntry."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def bulk_create(self, entries: list[PayrollEntry]) -> list[PayrollEntry]:
        if not entries:
            return []
        self.session.add_all(entries)
        await self.session.flush()
        return entries

    async def list_for_batch(self, batch_id: uuid.UUID) -> list[PayrollEntry]:
        stmt = (
            select(PayrollEntry)
            .where(PayrollEntry.batch_id == batch_id)
            .order_by(PayrollEntry.work_date.asc(), PayrollEntry.worker.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

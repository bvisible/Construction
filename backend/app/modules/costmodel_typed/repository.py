"""Repositories for the costmodel_typed module.

Async SQLAlchemy 2.0 patterns mirroring ``app.modules.costmodel.repository``.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.costmodel_typed.models import AssemblyComponent, YieldLibraryEntry


class AssemblyComponentRepository:
    """CRUD + listing for typed components attached to CostLines."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, component_id: uuid.UUID) -> AssemblyComponent | None:
        result = await self.session.execute(
            select(AssemblyComponent).where(AssemblyComponent.id == component_id)
        )
        return result.scalar_one_or_none()

    async def list_for_cost_line(
        self, cost_line_id: uuid.UUID
    ) -> list[AssemblyComponent]:
        result = await self.session.execute(
            select(AssemblyComponent)
            .where(AssemblyComponent.cost_line_id == cost_line_id)
            .order_by(AssemblyComponent.sort_order, AssemblyComponent.created_at)
        )
        return list(result.scalars().all())

    async def list_for_project(
        self,
        project_id: uuid.UUID,
        component_type: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[AssemblyComponent], int]:
        """List components of a project (join through CostLine.project_id)."""
        from app.modules.costmodel.models import CostLine

        base = (
            select(AssemblyComponent)
            .join(CostLine, AssemblyComponent.cost_line_id == CostLine.id)
            .where(CostLine.project_id == project_id)
        )
        if component_type:
            base = base.where(AssemblyComponent.component_type == component_type)

        total_q = select(func.count()).select_from(base.subquery())
        total = (await self.session.execute(total_q)).scalar_one()

        result = await self.session.execute(
            base.order_by(
                AssemblyComponent.cost_line_id,
                AssemblyComponent.sort_order,
                AssemblyComponent.created_at,
            )
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), int(total)

    async def create(self, component: AssemblyComponent) -> AssemblyComponent:
        self.session.add(component)
        await self.session.flush()
        await self.session.refresh(component)
        return component

    async def update_fields(
        self, component_id: uuid.UUID, **fields: object
    ) -> AssemblyComponent | None:
        comp = await self.get_by_id(component_id)
        if comp is None:
            return None
        for k, v in fields.items():
            if hasattr(comp, k):
                setattr(comp, k, v)
        await self.session.flush()
        await self.session.refresh(comp)
        return comp

    async def delete(self, component_id: uuid.UUID) -> bool:
        comp = await self.get_by_id(component_id)
        if comp is None:
            return False
        await self.session.delete(comp)
        await self.session.flush()
        return True

    async def delete_for_cost_line(self, cost_line_id: uuid.UUID) -> int:
        result = await self.session.execute(
            delete(AssemblyComponent).where(
                AssemblyComponent.cost_line_id == cost_line_id
            )
        )
        await self.session.flush()
        return int(result.rowcount or 0)


class YieldLibraryRepository:
    """CRUD + search for yield library entries (productivity rates)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, entry_id: uuid.UUID) -> YieldLibraryEntry | None:
        result = await self.session.execute(
            select(YieldLibraryEntry).where(YieldLibraryEntry.id == entry_id)
        )
        return result.scalar_one_or_none()

    async def list_for_project(
        self,
        project_id: uuid.UUID | None,
        include_global: bool = True,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[YieldLibraryEntry], int]:
        """List yields for a project. ``include_global=True`` also returns NULL-project rows."""
        if project_id is None:
            base = select(YieldLibraryEntry).where(YieldLibraryEntry.project_id.is_(None))
        elif include_global:
            base = select(YieldLibraryEntry).where(
                (YieldLibraryEntry.project_id == project_id)
                | (YieldLibraryEntry.project_id.is_(None))
            )
        else:
            base = select(YieldLibraryEntry).where(
                YieldLibraryEntry.project_id == project_id
            )

        total_q = select(func.count()).select_from(base.subquery())
        total = (await self.session.execute(total_q)).scalar_one()

        result = await self.session.execute(
            base.order_by(YieldLibraryEntry.task_label).offset(offset).limit(limit)
        )
        return list(result.scalars().all()), int(total)

    async def search_by_task(
        self, query: str, limit: int = 50
    ) -> list[YieldLibraryEntry]:
        """Case-insensitive fuzzy search on task_label (ILIKE pattern)."""
        like = f"%{query}%"
        result = await self.session.execute(
            select(YieldLibraryEntry)
            .where(YieldLibraryEntry.task_label.ilike(like))
            .order_by(YieldLibraryEntry.task_label)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def create(self, entry: YieldLibraryEntry) -> YieldLibraryEntry:
        self.session.add(entry)
        await self.session.flush()
        await self.session.refresh(entry)
        return entry

    async def bulk_create(
        self, entries: list[YieldLibraryEntry]
    ) -> list[YieldLibraryEntry]:
        if not entries:
            return []
        self.session.add_all(entries)
        await self.session.flush()
        return entries

    async def update_fields(
        self, entry_id: uuid.UUID, **fields: object
    ) -> YieldLibraryEntry | None:
        entry = await self.get_by_id(entry_id)
        if entry is None:
            return None
        for k, v in fields.items():
            if hasattr(entry, k):
                setattr(entry, k, v)
        await self.session.flush()
        await self.session.refresh(entry)
        return entry

    async def delete(self, entry_id: uuid.UUID) -> bool:
        entry = await self.get_by_id(entry_id)
        if entry is None:
            return False
        await self.session.delete(entry)
        await self.session.flush()
        return True

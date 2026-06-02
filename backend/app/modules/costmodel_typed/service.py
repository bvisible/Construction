"""Service layer for the costmodel_typed module.

Wraps the repositories with business logic, publishes events on the EventBus
so downstream / private modules can react (apply pricing rules, calibrate
rates, …) without modifying this generic core.
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import event_bus
from app.modules.costmodel.repository import CostLineRepository
from app.modules.costmodel_typed.models import (
    COMPONENT_TYPES,
    AssemblyComponent,
    YieldLibraryEntry,
)
from app.modules.costmodel_typed.repository import (
    AssemblyComponentRepository,
    YieldLibraryRepository,
)
from app.modules.costmodel_typed.schemas import (
    AssemblyComponentCreate,
    AssemblyComponentUpdate,
    YieldLibraryEntryCreate,
    YieldLibraryEntryUpdate,
)

logger = logging.getLogger(__name__)


def _safe_publish(name: str, data: dict[str, Any]) -> None:
    """Wrap ``event_bus.publish_detached`` so a faulty subscriber does not
    leak into the request flow."""
    try:
        event_bus.publish_detached(name, data, source_module="oe_costmodel_typed")
    except Exception:  # noqa: BLE001 — defensive; mirrors costmodel service
        logger.exception("Failed to publish event %s", name)


def _to_dec_str(v: Decimal | str | int | float | None) -> str | None:
    """Coerce numeric → Decimal-as-string for storage."""
    if v is None:
        return None
    if isinstance(v, str):
        return v
    if isinstance(v, Decimal):
        return format(v, "f") if v.is_finite() else "0"
    try:
        return format(Decimal(str(v)), "f")
    except (InvalidOperation, ValueError):
        return "0"


class AssemblyComponentService:
    """Business logic for typed AssemblyComponents."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = AssemblyComponentRepository(session)
        self.cost_line_repo = CostLineRepository(session)

    async def create(
        self, cost_line_id: uuid.UUID, payload: AssemblyComponentCreate
    ) -> AssemblyComponent:
        if payload.component_type not in COMPONENT_TYPES:
            raise ValueError(
                f"Unknown component_type: {payload.component_type}. "
                f"Allowed: {COMPONENT_TYPES}"
            )

        # Verify the CostLine exists (guard against orphan components)
        cost_line = await self.cost_line_repo.get_by_id(cost_line_id)
        if cost_line is None:
            raise LookupError(f"CostLine {cost_line_id} not found")

        component = AssemblyComponent(
            cost_line_id=cost_line_id,
            sub_block_label=payload.sub_block_label,
            component_type=payload.component_type,
            description=payload.description,
            unit=payload.unit,
            unit_rate=_to_dec_str(payload.unit_rate) or "0",
            discount=_to_dec_str(payload.discount),
            qty=_to_dec_str(payload.qty),
            yield_per_hour=_to_dec_str(payload.yield_per_hour),
            amount=_to_dec_str(payload.amount) or "0",
            sort_order=payload.sort_order,
            metadata_=payload.metadata or {},
        )
        created = await self.repo.create(component)
        _safe_publish(
            "costmodel_typed.component.created",
            {
                "component_id": str(created.id),
                "cost_line_id": str(cost_line_id),
                "project_id": str(cost_line.project_id),
                "component_type": created.component_type,
            },
        )
        return created

    async def update(
        self, component_id: uuid.UUID, payload: AssemblyComponentUpdate
    ) -> AssemblyComponent | None:
        fields: dict[str, Any] = {}
        if payload.sub_block_label is not None:
            fields["sub_block_label"] = payload.sub_block_label
        if payload.component_type is not None:
            if payload.component_type not in COMPONENT_TYPES:
                raise ValueError(f"Unknown component_type: {payload.component_type}")
            fields["component_type"] = payload.component_type
        if payload.description is not None:
            fields["description"] = payload.description
        if payload.unit is not None:
            fields["unit"] = payload.unit
        if payload.unit_rate is not None:
            fields["unit_rate"] = _to_dec_str(payload.unit_rate)
        if payload.discount is not None:
            fields["discount"] = _to_dec_str(payload.discount)
        if payload.qty is not None:
            fields["qty"] = _to_dec_str(payload.qty)
        if payload.yield_per_hour is not None:
            fields["yield_per_hour"] = _to_dec_str(payload.yield_per_hour)
        if payload.amount is not None:
            fields["amount"] = _to_dec_str(payload.amount)
        if payload.sort_order is not None:
            fields["sort_order"] = payload.sort_order
        if payload.metadata is not None:
            fields["metadata_"] = payload.metadata

        updated = await self.repo.update_fields(component_id, **fields)
        if updated is not None:
            _safe_publish(
                "costmodel_typed.component.updated",
                {
                    "component_id": str(updated.id),
                    "cost_line_id": str(updated.cost_line_id),
                    "fields": sorted(fields.keys()),
                },
            )
        return updated

    async def delete(self, component_id: uuid.UUID) -> bool:
        comp = await self.repo.get_by_id(component_id)
        if comp is None:
            return False
        cost_line_id = comp.cost_line_id
        ok = await self.repo.delete(component_id)
        if ok:
            _safe_publish(
                "costmodel_typed.component.deleted",
                {"component_id": str(component_id), "cost_line_id": str(cost_line_id)},
            )
        return ok

    async def list_for_cost_line(
        self, cost_line_id: uuid.UUID
    ) -> list[AssemblyComponent]:
        return await self.repo.list_for_cost_line(cost_line_id)

    async def list_for_project(
        self,
        project_id: uuid.UUID,
        component_type: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[AssemblyComponent], int]:
        return await self.repo.list_for_project(
            project_id, component_type=component_type, offset=offset, limit=limit
        )

    async def recompute_cost_line(self, cost_line_id: uuid.UUID) -> dict[str, Any]:
        """Sum component amounts → publish ``cost_line.recomputed`` event.

        Returns a summary that includes ``components_total`` (sum of stored
        component amounts) so callers can use it without re-querying.
        The CostLine ``estimate_amount`` itself is NOT mutated here — that is
        the responsibility of the downstream pricing module (which knows
        about R&B, margins, rounding rules).
        """
        cost_line = await self.cost_line_repo.get_by_id(cost_line_id)
        if cost_line is None:
            raise LookupError(f"CostLine {cost_line_id} not found")

        components = await self.repo.list_for_cost_line(cost_line_id)
        total = Decimal("0")
        for c in components:
            try:
                total += Decimal(c.amount or "0")
            except (InvalidOperation, ValueError):
                continue

        result = {
            "cost_line_id": str(cost_line_id),
            "project_id": str(cost_line.project_id),
            "components_count": len(components),
            "components_total": format(total, "f"),
        }
        _safe_publish("costmodel_typed.cost_line.recomputed", result)
        return result


class YieldLibraryService:
    """Business logic for the YieldLibrary."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = YieldLibraryRepository(session)

    async def create(
        self, payload: YieldLibraryEntryCreate
    ) -> YieldLibraryEntry:
        entry = YieldLibraryEntry(
            project_id=payload.project_id,
            task_label=payload.task_label,
            unit=payload.unit,
            yield_per_hour=_to_dec_str(payload.yield_per_hour) or "0",
            source=payload.source,
            source_ref=payload.source_ref,
            metadata_=payload.metadata or {},
        )
        created = await self.repo.create(entry)
        _safe_publish(
            "costmodel_typed.yield_library.entry_created",
            {
                "entry_id": str(created.id),
                "project_id": str(created.project_id) if created.project_id else None,
                "task_label": created.task_label,
            },
        )
        return created

    async def bulk_create(
        self, payloads: list[YieldLibraryEntryCreate]
    ) -> list[YieldLibraryEntry]:
        entries = [
            YieldLibraryEntry(
                project_id=p.project_id,
                task_label=p.task_label,
                unit=p.unit,
                yield_per_hour=_to_dec_str(p.yield_per_hour) or "0",
                source=p.source,
                source_ref=p.source_ref,
                metadata_=p.metadata or {},
            )
            for p in payloads
        ]
        return await self.repo.bulk_create(entries)

    async def update(
        self, entry_id: uuid.UUID, payload: YieldLibraryEntryUpdate
    ) -> YieldLibraryEntry | None:
        fields: dict[str, Any] = {}
        if payload.task_label is not None:
            fields["task_label"] = payload.task_label
        if payload.unit is not None:
            fields["unit"] = payload.unit
        if payload.yield_per_hour is not None:
            fields["yield_per_hour"] = _to_dec_str(payload.yield_per_hour)
        if payload.source is not None:
            fields["source"] = payload.source
        if payload.source_ref is not None:
            fields["source_ref"] = payload.source_ref
        if payload.last_calibrated_at is not None:
            fields["last_calibrated_at"] = payload.last_calibrated_at
        if payload.metadata is not None:
            fields["metadata_"] = payload.metadata
        return await self.repo.update_fields(entry_id, **fields)

    async def delete(self, entry_id: uuid.UUID) -> bool:
        return await self.repo.delete(entry_id)

    async def search(self, query: str, limit: int = 50) -> list[YieldLibraryEntry]:
        return await self.repo.search_by_task(query, limit=limit)

    async def list_for_project(
        self,
        project_id: uuid.UUID | None,
        include_global: bool = True,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[YieldLibraryEntry], int]:
        return await self.repo.list_for_project(
            project_id, include_global=include_global, offset=offset, limit=limit
        )

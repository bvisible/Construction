"""NEOFFICE FILE — Owned 100% by Neoservice. Not from upstream OpenConstructionERP.

Neoconstruction -> Activity bridge: subscribes to schedule EventBus events
and mirrors Work Orders / Schedule Activities into the Frappe Activity app.

Subscriptions register at import time. The module is reached because
`app/modules/neoffice/events.py` imports this package and the module loader
auto-imports `neoffice/events.py`.

A Schedule Activity is mirrored only when it owns no Work Order: otherwise
its Work Orders carry the finer-grained mirror (anti-duplication). Known
edge case: a Schedule Activity mirrored while empty, then given a Work
Order, leaves a stale Activity mirror — deferred to a later refinement.

Every handler swallows its exceptions — a bridge failure must never break
the Neoconstruction flow that triggered it.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from app.core.events import Event, event_bus
from app.database import async_session_factory
from app.modules.neoffice.bridge import frappe_client, mappers
from app.modules.schedule.models import Activity, Schedule, WorkOrder

logger = logging.getLogger(__name__)


async def _on_work_order_event(event: Event) -> None:
    """Mirror a Work Order create / update / status change (detached task)."""
    asyncio.create_task(_mirror_work_order(event))


async def _on_schedule_activity_event(event: Event) -> None:
    """Mirror a Schedule Activity create / update (detached task)."""
    asyncio.create_task(_mirror_schedule_activity(event))


async def _mirror_work_order(event: Event) -> None:
    work_order_id = (event.data or {}).get("work_order_id")
    if not work_order_id:
        return
    try:
        async with async_session_factory() as session:
            work_order = await session.get(WorkOrder, uuid.UUID(str(work_order_id)))
            if work_order is None:
                logger.warning("bridge: work order %s not found — skipped", work_order_id)
                return
            activity = await session.get(Activity, work_order.activity_id)
            schedule = (
                await session.get(Schedule, activity.schedule_id) if activity else None
            )
            if activity is None or schedule is None:
                logger.warning(
                    "bridge: parent activity/schedule missing for work order %s — skipped",
                    work_order_id,
                )
                return
            payload = mappers.work_order_to_activity_payload(work_order, activity, schedule)
        await frappe_client.push_activity(payload)
    except Exception:
        logger.exception("bridge: work order mirror failed for %s", work_order_id)


async def _mirror_schedule_activity(event: Event) -> None:
    activity_id = (event.data or {}).get("activity_id")
    if not activity_id:
        return
    try:
        async with async_session_factory() as session:
            activity = await session.get(Activity, uuid.UUID(str(activity_id)))
            if activity is None:
                logger.warning("bridge: activity %s not found — skipped", activity_id)
                return
            # Anti-duplication: a Schedule Activity that owns Work Orders is
            # mirrored through those instead (finer operational granularity).
            if activity.work_orders:
                logger.info(
                    "bridge: activity %s has %d work order(s) — mirrored via them",
                    activity_id,
                    len(activity.work_orders),
                )
                return
            schedule = await session.get(Schedule, activity.schedule_id)
            if schedule is None:
                logger.warning(
                    "bridge: schedule %s not found — skipped", activity.schedule_id
                )
                return
            payload = mappers.schedule_activity_to_activity_payload(activity, schedule)
        await frappe_client.push_activity(payload)
    except Exception:
        logger.exception("bridge: schedule activity mirror failed for %s", activity_id)


event_bus.subscribe("schedule.work_order.created", _on_work_order_event)
event_bus.subscribe("schedule.work_order.updated", _on_work_order_event)
event_bus.subscribe("schedule.work_order.status_changed", _on_work_order_event)
event_bus.subscribe("schedule.activity.created", _on_schedule_activity_event)
event_bus.subscribe("schedule.activity.updated", _on_schedule_activity_event)

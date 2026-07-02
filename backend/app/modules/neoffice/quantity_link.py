"""Live "linked quantity": one source quantity drives MANY BOQ positions.

Upstream OCE links a takeoff measurement to at most ONE position
(``link_measurement_to_boq`` — a single ``linked_boq_position_id`` column). A real
quantity survey routinely needs the SAME quantity to drive several positions — a
slab area feeds a *concrete* position AND a *screed* AND a *parquet* — each with
its own factor (parquet ×1 in m², concrete × thickness in m³, a waste %).

The SOURCE of that quantity is either:
  * a **takeoff measurement** (a zone/area extracted from a PDF plan), or
  * **another BOQ position** (reuse an existing position's quantity, e.g. a
    "Surface 2" position drives all the finishes laid on it).

We store the link on the DRIVEN position, in ``position.metadata_`` under
``neoffice_driven_by`` = ``{source_type, source_id, factor, …}``, so ONE source
can be referenced by ANY number of positions (one-to-many) **without a schema
change** (osiris is a deploy target where alembic migrations are patched at
install). ``refresh`` re-reads each source's current value × factor and re-pushes
it into every driven position, so re-measuring / re-pricing updates the whole
devis (live).

NEOFFICE — Neoffice-only module, no core OCE patch.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

# Key under which a position records the source that drives its quantity.
_DRIVEN_KEY = "neoffice_driven_by"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_driven_link(position: Any) -> dict[str, Any] | None:
    """Return the ``neoffice_driven_by`` link recorded on a position, if any."""
    meta = getattr(position, "metadata_", None) or {}
    link = meta.get(_DRIVEN_KEY)
    return link if isinstance(link, dict) else None


def _measurement_label(measurement: Any) -> str:
    for attr in ("annotation", "group_name", "type"):
        val = getattr(measurement, attr, None)
        if val:
            return str(val)
    return "mesure"


def _position_label(position: Any) -> str:
    for attr in ("designation", "description"):
        val = getattr(position, attr, None)
        if val:
            return str(val)[:80]
    return str(getattr(position, "ordinal", "") or "position")


async def _resolve_source_value(
    session: Any, source_type: str, source_id: str
) -> tuple[float, str | None, str] | None:
    """Return ``(value, unit, label)`` for a link source, or None if unusable.

    ``measurement`` → the picked takeoff scalar; ``position`` → the source
    position's stored quantity. A missing/empty source returns None (the caller
    then flags the link stale — never zeroes a driven quantity).
    """
    if source_type == "position":
        from app.modules.boq.service import BOQService  # noqa: PLC0415

        pos = await BOQService(session).position_repo.get_by_id(uuid.UUID(str(source_id)))
        if pos is None:
            return None
        try:
            value = float(pos.quantity)
        except (TypeError, ValueError):
            return None
        return value, getattr(pos, "unit", None), _position_label(pos)

    # default: measurement
    from app.modules.takeoff.service import TakeoffService, _pick_takeoff_value  # noqa: PLC0415

    measurement = await TakeoffService(session).get_measurement(uuid.UUID(str(source_id)))
    value = _pick_takeoff_value(measurement)
    if value is None:
        return None
    return float(value), getattr(measurement, "measurement_unit", None), _measurement_label(measurement)


async def _apply_link(
    session: Any,
    position_id: uuid.UUID,
    source_type: str,
    source_id: str,
    factor: float,
    *,
    project_id: Any,
) -> dict[str, Any]:
    """Push (source value × factor) into a position and record the link."""
    from app.modules.boq.service import BOQService  # noqa: PLC0415
    from app.modules.takeoff.service import TakeoffService  # noqa: PLC0415

    boq = BOQService(session)
    position = await boq.position_repo.get_by_id(position_id)
    if position is None:
        raise ValueError("position_not_found")
    # IDOR: the driven position must live in the source's project. Reuse the
    # takeoff guard (raises 404 on a cross-project attempt).
    await TakeoffService(session)._assert_position_in_project(str(position_id), project_id)  # noqa: SLF001

    resolved = await _resolve_source_value(session, source_type, source_id)
    if resolved is None:
        raise ValueError("source_has_no_value")
    value, unit, label = resolved
    factor = float(factor) if factor else 1.0
    driven = value * factor

    meta = dict(getattr(position, "metadata_", None) or {})
    meta[_DRIVEN_KEY] = {
        "source_type": source_type,
        "source_id": str(source_id),
        # Legacy alias so older reads still resolve a measurement source.
        "measurement_id": str(source_id) if source_type == "measurement" else None,
        "label": label,
        "factor": factor,
        "source_value": value,
        "source_unit": unit,
        "linked_at": _now_iso(),
    }
    await boq.position_repo.update_fields(position_id, quantity=str(driven), metadata_=meta)
    await session.refresh(position)
    await boq._recompute_position_total(position)  # noqa: SLF001 - canonical recompute
    return {
        "position_id": str(position_id),
        "source_type": source_type,
        "source_id": str(source_id),
        "source_value": value,
        "factor": factor,
        "quantity": driven,
    }


async def link_position_to_measurement(
    session: Any, position_id: uuid.UUID, measurement_id: uuid.UUID, factor: float = 1.0
) -> dict[str, Any]:
    """Drive a position's quantity from a takeoff MEASUREMENT × factor."""
    from app.modules.takeoff.service import TakeoffService  # noqa: PLC0415

    measurement = await TakeoffService(session).get_measurement(measurement_id)  # 404 if missing
    return await _apply_link(
        session, position_id, "measurement", str(measurement_id), factor,
        project_id=measurement.project_id,
    )


async def link_position_to_position(
    session: Any, position_id: uuid.UUID, source_position_id: uuid.UUID, factor: float = 1.0
) -> dict[str, Any]:
    """Drive a position's quantity from ANOTHER position's quantity × factor."""
    from app.modules.boq.service import BOQService  # noqa: PLC0415

    if position_id == source_position_id:
        raise ValueError("cannot_link_to_self")
    boq = BOQService(session)
    source = await boq.position_repo.get_by_id(source_position_id)
    if source is None:
        raise ValueError("source_not_found")
    project_id = await boq.position_repo.project_id_for_boq(source.boq_id)
    return await _apply_link(
        session, position_id, "position", str(source_position_id), factor, project_id=project_id,
    )


async def unlink_position(session: Any, position_id: uuid.UUID) -> dict[str, Any]:
    """Remove the driven-by link from a position (leaves its quantity as-is)."""
    from app.modules.boq.service import BOQService  # noqa: PLC0415

    boq = BOQService(session)
    position = await boq.position_repo.get_by_id(position_id)
    if position is None:
        raise ValueError("position_not_found")
    meta = dict(getattr(position, "metadata_", None) or {})
    had = meta.pop(_DRIVEN_KEY, None) is not None
    if had:
        await boq.position_repo.update_fields(position_id, metadata_=meta)
    return {"position_id": str(position_id), "unlinked": had}


async def refresh_driven_quantities(session: Any, boq_id: uuid.UUID) -> dict[str, Any]:
    """Re-push each source's current value × factor into every driven position of
    one BOQ. The "live" part: after re-measuring / re-pricing, one refresh updates
    the whole devis. A source that vanished flags the link ``stale`` (quantity is
    left untouched — never silently zeroed).
    """
    from app.modules.boq.service import BOQService  # noqa: PLC0415

    boq = BOQService(session)
    positions = await boq.position_repo.list_all_for_boq(boq_id)
    # Snapshot (id, link) BEFORE mutating: update_fields calls expire_all(), so a
    # mid-loop read of a not-yet-processed position's metadata_ would fire a sync
    # lazy-reload on the async session → MissingGreenlet. Re-fetch each fresh.
    driven: list[tuple[uuid.UUID, dict[str, Any]]] = [
        (p.id, link) for p in positions if (link := get_driven_link(p))
    ]

    updated: list[str] = []
    stale: list[str] = []
    for position_id, link in driven:
        source_type = link.get("source_type") or "measurement"
        source_id = link.get("source_id") or link.get("measurement_id")
        resolved = None
        if source_id:
            try:
                resolved = await _resolve_source_value(session, source_type, str(source_id))
            except Exception:  # noqa: BLE001 - source gone/inaccessible → stale
                resolved = None
        if resolved is None:
            fresh = await boq.position_repo.get_by_id(position_id)
            meta = dict(getattr(fresh, "metadata_", None) or {})
            meta[_DRIVEN_KEY] = {**link, "stale": True, "refreshed_at": _now_iso()}
            await boq.position_repo.update_fields(position_id, metadata_=meta)
            stale.append(str(position_id))
            continue
        value, unit, label = resolved
        factor = float(link.get("factor") or 1.0)
        meta = {
            **link,
            "label": label,
            "source_value": value,
            "source_unit": unit,
            "factor": factor,
            "stale": False,
            "refreshed_at": _now_iso(),
        }
        await boq.position_repo.update_fields(position_id, quantity=str(value * factor), metadata_=meta)
        fresh = await boq.position_repo.get_by_id(position_id)  # reload (expired by update)
        if fresh is not None:
            await boq._recompute_position_total(fresh)  # noqa: SLF001
        updated.append(str(position_id))

    return {"boq_id": str(boq_id), "updated": len(updated), "stale": len(stale),
            "updated_ids": updated, "stale_ids": stale}

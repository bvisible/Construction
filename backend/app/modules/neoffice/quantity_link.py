"""Live "linked quantity": one measured takeoff value drives MANY BOQ positions.

Upstream OCE links a takeoff measurement to at most ONE position
(``link_measurement_to_boq`` — a single ``linked_boq_position_id`` column). A real
quantity survey routinely needs the SAME measured area to drive several positions
— a slab area feeds a *concrete* position AND a *screed* AND a *parquet* — each
with its own factor (parquet ×1 in m², concrete × thickness in m³, a waste %).

We store the link on the POSITION side, in ``position.metadata_`` under
``neoffice_driven_by``, so ONE measurement can be referenced by ANY number of
positions (one-to-many) **without a schema change** (important: osiris is a
deploy target where alembic migrations are patched at install). ``refresh`` then
re-reads each source measurement's current value × factor and re-pushes it into
every driven position, so re-measuring the plan updates the whole devis (live).

NEOFFICE — Neoffice-only module, no core OCE patch.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

# Key under which a position records the measurement that drives its quantity.
_DRIVEN_KEY = "neoffice_driven_by"


def _measurement_label(measurement: Any) -> str:
    """A short human label for the source measurement (for the badge/UI)."""
    for attr in ("annotation", "group_name", "type"):
        val = getattr(measurement, attr, None)
        if val:
            return str(val)
    return "mesure"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_driven_link(position: Any) -> dict[str, Any] | None:
    """Return the ``neoffice_driven_by`` link recorded on a position, if any."""
    meta = getattr(position, "metadata_", None) or {}
    link = meta.get(_DRIVEN_KEY)
    return link if isinstance(link, dict) else None


async def link_position_to_measurement(
    session: Any,
    position_id: uuid.UUID,
    measurement_id: uuid.UUID,
    factor: float = 1.0,
) -> dict[str, Any]:
    """Drive a BOQ position's quantity from a takeoff measurement (× factor).

    Pushes ``measured_value × factor`` into the position quantity, recomputes the
    position total, and records the link in ``position.metadata_`` so it can be
    refreshed later. Because the link lives on the position, calling this for the
    same measurement on several positions gives the desired one-to-many drive.

    Raises ValueError('position_not_found' | 'measurement_has_no_value').
    """
    # Lazy imports: reuse the canonical takeoff value picker + BOQ recompute path
    # (single source of truth for the money math), avoiding an import cycle.
    from app.modules.boq.service import BOQService  # noqa: PLC0415
    from app.modules.takeoff.service import TakeoffService, _pick_takeoff_value  # noqa: PLC0415

    takeoff = TakeoffService(session)
    measurement = await takeoff.get_measurement(measurement_id)  # 404 if missing

    boq = BOQService(session)
    position = await boq.position_repo.get_by_id(position_id)
    if position is None:
        raise ValueError("position_not_found")

    # IDOR: the position must live in the measurement's project (the router has
    # only verified access to the measurement's project). Reuses the takeoff
    # guard, which raises 404 on a cross-project attempt.
    await takeoff._assert_position_in_project(str(position_id), measurement.project_id)  # noqa: SLF001

    value = _pick_takeoff_value(measurement)
    if value is None:
        raise ValueError("measurement_has_no_value")
    factor = float(factor) if factor else 1.0
    driven = float(value) * factor

    meta = dict(getattr(position, "metadata_", None) or {})
    meta[_DRIVEN_KEY] = {
        "measurement_id": str(measurement_id),
        "measurement_label": _measurement_label(measurement),
        "factor": factor,
        "source_value": float(value),
        "source_unit": getattr(measurement, "measurement_unit", None),
        "linked_at": _now_iso(),
    }
    await boq.position_repo.update_fields(position_id, quantity=str(driven), metadata_=meta)
    await session.refresh(position)
    await boq._recompute_position_total(position)  # noqa: SLF001 - canonical recompute
    return {
        "position_id": str(position_id),
        "measurement_id": str(measurement_id),
        "source_value": float(value),
        "factor": factor,
        "quantity": driven,
    }


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
    """Re-push each source measurement's current value × factor into every driven
    position of one BOQ. This is the "live" part: after re-measuring the plan,
    one refresh updates the whole devis.

    A position whose source measurement was deleted is flagged ``stale`` in its
    link (quantity left untouched — never silently zeroed).
    """
    from app.modules.boq.service import BOQService  # noqa: PLC0415
    from app.modules.takeoff.service import TakeoffService, _pick_takeoff_value  # noqa: PLC0415

    boq = BOQService(session)
    takeoff = TakeoffService(session)
    positions = await boq.position_repo.list_all_for_boq(boq_id)

    # Snapshot (id, link) for every driven position BEFORE mutating anything: the
    # update_fields below calls session.expire_all(), so re-reading a not-yet-
    # processed position's metadata_ mid-loop would fire a sync lazy-reload on
    # the async session → MissingGreenlet. We read links once, then re-fetch each
    # position fresh right before its recompute.
    driven: list[tuple[uuid.UUID, dict[str, Any]]] = [
        (p.id, link) for p in positions if (link := get_driven_link(p))
    ]

    updated: list[str] = []
    stale: list[str] = []
    for position_id, link in driven:
        raw_id = link.get("measurement_id")
        try:
            measurement = await takeoff.get_measurement(uuid.UUID(str(raw_id)))
        except Exception:  # noqa: BLE001 - measurement gone/inaccessible → stale
            fresh = await boq.position_repo.get_by_id(position_id)
            meta = dict(getattr(fresh, "metadata_", None) or {})
            meta[_DRIVEN_KEY] = {**link, "stale": True, "refreshed_at": _now_iso()}
            await boq.position_repo.update_fields(position_id, metadata_=meta)
            stale.append(str(position_id))
            continue
        value = _pick_takeoff_value(measurement)
        if value is None:
            continue
        factor = float(link.get("factor") or 1.0)
        driven_qty = float(value) * factor
        meta = {
            **link,
            "source_value": float(value),
            "source_unit": getattr(measurement, "measurement_unit", None),
            "factor": factor,
            "stale": False,
            "refreshed_at": _now_iso(),
        }
        await boq.position_repo.update_fields(position_id, quantity=str(driven_qty), metadata_=meta)
        fresh = await boq.position_repo.get_by_id(position_id)  # reload (expired by update)
        if fresh is not None:
            await boq._recompute_position_total(fresh)  # noqa: SLF001
        updated.append(str(position_id))

    return {"boq_id": str(boq_id), "updated": len(updated), "stale": len(stale),
            "updated_ids": updated, "stale_ids": stale}

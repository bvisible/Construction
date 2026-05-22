"""‌⁠‍Audit log API routes (admin-only).

Endpoints:
    GET /api/v1/audit                          — list audit entries with filters
    GET /api/v1/audit/count                    — count rows matching the same filter set
    GET /api/v1/audit/{entity_type}/{entity_id} — audit trail for a specific entity

Filter params accepted by ``GET /v1/audit`` and ``/v1/audit/count``:

* ``entity_type`` — logical entity name (boq / project / …)
* ``entity_id`` — single UUID
* ``user_id_filter`` — UUID of the acting user (aliased to avoid colliding
  with the path-param of the entity trail route)
* ``action`` — verb (create / update / …)
* ``date_from`` / ``date_to`` — ISO-8601 inclusive bounds on ``created_at``
* ``sort`` — ``desc`` (default) or ``asc`` — list only
* ``limit`` / ``offset`` — pagination, list only

The frontend's filter bar in ``AuditLogPage.tsx`` is the canonical
consumer — keep this signature in sync with that page's ``AuditFilters``
type when adding new params.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.core.audit import (
    AuditEntry,
    count_audit_entries,
    get_audit_entries,
)
from app.dependencies import CurrentUserId, RequirePermission, SessionDep

router = APIRouter(prefix="/api/v1/audit", tags=["Audit"])
logger = logging.getLogger(__name__)


def _entry_to_dict(entry: AuditEntry) -> dict[str, Any]:
    """‌⁠‍Serialise an ``AuditEntry`` to a plain dict for JSON response."""
    return {
        "id": str(entry.id),
        "action": entry.action,
        "entity_type": entry.entity_type,
        "entity_id": entry.entity_id,
        "user_id": str(entry.user_id) if entry.user_id else None,
        "ip_address": entry.ip_address,
        "details": entry.details,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }


@router.get("", response_model=list[dict[str, Any]])
async def list_audit_entries(
    session: SessionDep,
    _user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("audit.view")),
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    user_id: str | None = Query(default=None, alias="user_id_filter"),
    action: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    sort: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    """‌⁠‍List audit log entries with optional filters (admin only)."""
    entries = await get_audit_entries(
        session,
        entity_type=entity_type,
        entity_id=entity_id,
        user_id=user_id,
        action=action,
        date_from=date_from,
        date_to=date_to,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return [_entry_to_dict(e) for e in entries]


@router.get("/count", response_model=dict[str, int])
async def count_audit(
    session: SessionDep,
    _user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("audit.view")),
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    user_id: str | None = Query(default=None, alias="user_id_filter"),
    action: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
) -> dict[str, int]:
    """‌⁠‍Total rows matching the current filter (used by the admin pager)."""
    total = await count_audit_entries(
        session,
        entity_type=entity_type,
        entity_id=entity_id,
        user_id=user_id,
        action=action,
        date_from=date_from,
        date_to=date_to,
    )
    return {"total": total}


@router.get("/{entity_type}/{entity_id}", response_model=list[dict[str, Any]])
async def entity_audit_trail(
    entity_type: str,
    entity_id: str,
    session: SessionDep,
    _user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("audit.view")),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    """Get the full audit trail for a specific entity."""
    entries = await get_audit_entries(
        session,
        entity_type=entity_type,
        entity_id=entity_id,
        limit=limit,
        offset=offset,
    )
    return [_entry_to_dict(e) for e in entries]

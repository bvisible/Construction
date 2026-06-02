"""HTTP routes for the costmodel_typed module.

Endpoints:
    POST   /spine/lines/{cost_line_id}/components            — attach typed component to a CostLine
    GET    /spine/lines/{cost_line_id}/components            — list components of a CostLine
    POST   /spine/lines/{cost_line_id}/recompute             — recompute CostLine total from components
    PATCH  /typed/components/{component_id}                  — update a component
    DELETE /typed/components/{component_id}                  — delete a component
    GET    /projects/{project_id}/typed/components           — list components of a project (filterable)
    POST   /yield-library                                    — create a yield entry
    GET    /yield-library                                    — list (project-scoped + global, paginated)
    GET    /yield-library/search                             — fuzzy search on task_label
    PATCH  /yield-library/{entry_id}                         — update a yield entry
    DELETE /yield-library/{entry_id}                         — delete a yield entry
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import CurrentUserId, RequirePermission, SessionDep, verify_project_access
from app.modules.costmodel_typed.schemas import (
    AssemblyComponentCreate,
    AssemblyComponentResponse,
    AssemblyComponentUpdate,
    YieldLibraryEntryCreate,
    YieldLibraryEntryResponse,
    YieldLibraryEntryUpdate,
)
from app.modules.costmodel_typed.service import (
    AssemblyComponentService,
    YieldLibraryService,
)

router = APIRouter(tags=["costmodel_typed"])


def _get_component_service(session: SessionDep) -> AssemblyComponentService:
    return AssemblyComponentService(session)


def _get_yield_service(session: SessionDep) -> YieldLibraryService:
    return YieldLibraryService(session)


# ── AssemblyComponent ────────────────────────────────────────────────────────


@router.post(
    "/spine/lines/{cost_line_id}/components",
    response_model=AssemblyComponentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Attach a typed component to a CostLine",
    dependencies=[Depends(RequirePermission("costmodel_typed.write"))],
)
async def create_component_on_cost_line(
    cost_line_id: uuid.UUID,
    payload: AssemblyComponentCreate,
    service: AssemblyComponentService = Depends(_get_component_service),
) -> AssemblyComponentResponse:
    try:
        created = await service.create(cost_line_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return AssemblyComponentResponse.model_validate(created)


@router.get(
    "/spine/lines/{cost_line_id}/components",
    response_model=list[AssemblyComponentResponse],
    summary="List typed components of a CostLine",
    dependencies=[Depends(RequirePermission("costmodel_typed.read"))],
)
async def list_components_for_cost_line(
    cost_line_id: uuid.UUID,
    service: AssemblyComponentService = Depends(_get_component_service),
) -> list[AssemblyComponentResponse]:
    items = await service.list_for_cost_line(cost_line_id)
    return [AssemblyComponentResponse.model_validate(it) for it in items]


@router.post(
    "/spine/lines/{cost_line_id}/recompute",
    summary="Recompute a CostLine total from its typed components",
    response_model=None,  # plain dict — opt out of automatic response_model inference
    dependencies=[Depends(RequirePermission("costmodel_typed.write"))],
)
async def recompute_cost_line(
    cost_line_id: uuid.UUID,
    service: AssemblyComponentService = Depends(_get_component_service),
) -> dict[str, object]:
    try:
        return await service.recompute_cost_line(cost_line_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch(
    "/typed/components/{component_id}",
    response_model=AssemblyComponentResponse,
    summary="Update a typed component",
    dependencies=[Depends(RequirePermission("costmodel_typed.write"))],
)
async def update_component(
    component_id: uuid.UUID,
    payload: AssemblyComponentUpdate,
    service: AssemblyComponentService = Depends(_get_component_service),
) -> AssemblyComponentResponse:
    try:
        updated = await service.update(component_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="Component not found")
    return AssemblyComponentResponse.model_validate(updated)


@router.delete(
    "/typed/components/{component_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a typed component",
    dependencies=[Depends(RequirePermission("costmodel_typed.write"))],
)
async def delete_component(
    component_id: uuid.UUID,
    service: AssemblyComponentService = Depends(_get_component_service),
):
    ok = await service.delete(component_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Component not found")


@router.get(
    "/projects/{project_id}/typed/components",
    response_model=list[AssemblyComponentResponse],
    summary="List typed components for a project (filterable by type)",
    dependencies=[Depends(RequirePermission("costmodel_typed.read"))],
)
async def list_components_for_project(
    project_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    component_type: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    service: AssemblyComponentService = Depends(_get_component_service),
) -> list[AssemblyComponentResponse]:
    await verify_project_access(project_id, user_id, session)
    items, _total = await service.list_for_project(
        project_id, component_type=component_type, offset=offset, limit=limit
    )
    return [AssemblyComponentResponse.model_validate(it) for it in items]


# ── YieldLibrary ─────────────────────────────────────────────────────────────


@router.post(
    "/yield-library",
    response_model=YieldLibraryEntryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a yield library entry",
    dependencies=[Depends(RequirePermission("costmodel_typed.write"))],
)
async def create_yield_entry(
    payload: YieldLibraryEntryCreate,
    service: YieldLibraryService = Depends(_get_yield_service),
) -> YieldLibraryEntryResponse:
    created = await service.create(payload)
    return YieldLibraryEntryResponse.model_validate(created)


@router.get(
    "/yield-library",
    response_model=list[YieldLibraryEntryResponse],
    summary="List yield library entries (filterable by project + global rollup)",
    dependencies=[Depends(RequirePermission("costmodel_typed.read"))],
)
async def list_yield_entries(
    project_id: uuid.UUID | None = Query(default=None),
    include_global: bool = Query(default=True),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    service: YieldLibraryService = Depends(_get_yield_service),
) -> list[YieldLibraryEntryResponse]:
    items, _total = await service.list_for_project(
        project_id, include_global=include_global, offset=offset, limit=limit
    )
    return [YieldLibraryEntryResponse.model_validate(it) for it in items]


@router.get(
    "/yield-library/search",
    response_model=list[YieldLibraryEntryResponse],
    summary="Fuzzy search yield library by task label",
    dependencies=[Depends(RequirePermission("costmodel_typed.read"))],
)
async def search_yield_entries(
    q: str = Query(..., min_length=1, max_length=255),
    limit: int = Query(default=50, ge=1, le=200),
    service: YieldLibraryService = Depends(_get_yield_service),
) -> list[YieldLibraryEntryResponse]:
    items = await service.search(q, limit=limit)
    return [YieldLibraryEntryResponse.model_validate(it) for it in items]


@router.patch(
    "/yield-library/{entry_id}",
    response_model=YieldLibraryEntryResponse,
    summary="Update a yield library entry",
    dependencies=[Depends(RequirePermission("costmodel_typed.write"))],
)
async def update_yield_entry(
    entry_id: uuid.UUID,
    payload: YieldLibraryEntryUpdate,
    service: YieldLibraryService = Depends(_get_yield_service),
) -> YieldLibraryEntryResponse:
    updated = await service.update(entry_id, payload)
    if updated is None:
        raise HTTPException(status_code=404, detail="Yield entry not found")
    return YieldLibraryEntryResponse.model_validate(updated)


@router.delete(
    "/yield-library/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a yield library entry",
    dependencies=[Depends(RequirePermission("costmodel_typed.write"))],
)
async def delete_yield_entry(
    entry_id: uuid.UUID,
    service: YieldLibraryService = Depends(_get_yield_service),
):
    ok = await service.delete(entry_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Yield entry not found")

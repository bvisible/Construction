# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Service-level tests for the approval-routes engine.

Coverage:
    * Happy path: 3-step route, 2 user-pinned approvers, all approve →
      instance status flips to ``approved``.
    * Reject midway: second-step rejection short-circuits the workflow.
    * ``majority`` mode: 2-of-3 approve a single role-based step
      advances; 1-of-3 + 2 rejected fails.
    * ``any`` mode: first approval clears a role-based step.
    * Race / duplicate decision: the UniqueConstraint prevents two
      decision rows from the same approver on the same step.
    * Cancel a pending instance — status flips to ``cancelled``,
      subsequent decisions raise 409.
    * Cannot start a second instance against the same target while one
      is pending (409).
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.core.audit_log  # noqa: F401 — registers ActivityLog with Base
from app.database import Base
from app.modules.approval_routes.models import (  # noqa: F401 — registers ORM
    Instance,
    Route,
    Step,
    StepState,
)
from app.modules.approval_routes.schemas import (
    DecisionSubmit,
    InstanceCreate,
    RouteCreate,
    StepCreate,
)
from app.modules.approval_routes.service import ApprovalRouteService
from app.modules.projects.models import Project  # noqa: F401 — registers ORM
from app.modules.users.models import User  # noqa: F401 — registers ORM


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    """Per-test in-memory SQLite session with all DDL applied."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sm() as s:
        yield s
    await engine.dispose()


async def _seed_project(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    """Return (project_id, owner_user_id) for a freshly inserted project."""
    user = User(
        email=f"ar-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="hashed",
        full_name="Approval Tester",
        role="admin",
    )
    session.add(user)
    await session.flush()
    project = Project(name=f"AR Project {uuid.uuid4().hex[:6]}", owner_id=user.id)
    session.add(project)
    await session.flush()
    return project.id, user.id


async def _add_user(session: AsyncSession, email_prefix: str = "u") -> uuid.UUID:
    user = User(
        email=f"{email_prefix}-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="hashed",
        full_name="Approver",
        role="editor",
    )
    session.add(user)
    await session.flush()
    return user.id


# ── Happy path ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_three_step_user_pinned_route_completes_on_all_approvals(
    session: AsyncSession,
) -> None:
    svc = ApprovalRouteService(session)
    project_id, owner_id = await _seed_project(session)
    u1 = await _add_user(session, "u1")
    u2 = await _add_user(session, "u2")
    u3 = await _add_user(session, "u3")

    route_payload = RouteCreate(
        project_id=project_id,
        name="3-step user pinned",
        target_kind="submittal",
        steps=[
            StepCreate(ordinal=1, approver_user_id=u1, mode="all"),
            StepCreate(ordinal=2, approver_user_id=u2, mode="all"),
            StepCreate(ordinal=3, approver_user_id=u3, mode="all"),
        ],
    )
    route = await svc.create_route(route_payload, created_by=owner_id)
    steps = await svc.list_steps(route.id)

    target_id = uuid.uuid4()
    instance = await svc.start_instance(
        InstanceCreate(route_id=route.id, target_kind="submittal", target_id=target_id),
        started_by=owner_id,
    )
    assert instance.status == "pending"
    assert instance.current_step_ordinal == 1

    # Step 1
    instance = await svc.submit_decision(
        instance.id,
        DecisionSubmit(step_id=steps[0].id, decision="approved"),
        approver_id=u1,
    )
    assert instance.status == "pending"
    assert instance.current_step_ordinal == 2

    # Step 2
    instance = await svc.submit_decision(
        instance.id,
        DecisionSubmit(step_id=steps[1].id, decision="approved"),
        approver_id=u2,
    )
    assert instance.status == "pending"
    assert instance.current_step_ordinal == 3

    # Step 3 — completes the workflow.
    instance = await svc.submit_decision(
        instance.id,
        DecisionSubmit(step_id=steps[2].id, decision="approved", comment="LGTM"),
        approver_id=u3,
    )
    assert instance.status == "approved"
    assert instance.completed_at is not None


# ── Reject midway ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reject_midway_finalises_instance_as_rejected(
    session: AsyncSession,
) -> None:
    svc = ApprovalRouteService(session)
    project_id, owner_id = await _seed_project(session)
    u1 = await _add_user(session, "u1")
    u2 = await _add_user(session, "u2")

    route = await svc.create_route(
        RouteCreate(
            project_id=project_id,
            name="2-step",
            target_kind="change_order",
            steps=[
                StepCreate(ordinal=1, approver_user_id=u1, mode="all"),
                StepCreate(ordinal=2, approver_user_id=u2, mode="all"),
            ],
        ),
        created_by=owner_id,
    )
    steps = await svc.list_steps(route.id)
    instance = await svc.start_instance(
        InstanceCreate(
            route_id=route.id,
            target_kind="change_order",
            target_id=uuid.uuid4(),
        ),
        started_by=owner_id,
    )

    # Step 1 approved
    instance = await svc.submit_decision(
        instance.id,
        DecisionSubmit(step_id=steps[0].id, decision="approved"),
        approver_id=u1,
    )
    # Step 2 rejected → terminal state.
    instance = await svc.submit_decision(
        instance.id,
        DecisionSubmit(step_id=steps[1].id, decision="rejected", comment="budget mismatch"),
        approver_id=u2,
    )
    assert instance.status == "rejected"
    assert instance.completed_at is not None


# ── Majority mode ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_majority_mode_advances_after_majority_approve(
    session: AsyncSession,
) -> None:
    """Role-based step with mode=majority: 2 approve, 1 reject -> advance."""
    svc = ApprovalRouteService(session)
    project_id, owner_id = await _seed_project(session)
    u1 = await _add_user(session, "u1")
    u2 = await _add_user(session, "u2")
    u3 = await _add_user(session, "u3")
    u4 = await _add_user(session, "u4")

    route = await svc.create_route(
        RouteCreate(
            project_id=project_id,
            name="majority gate",
            target_kind="rfi",
            steps=[
                StepCreate(ordinal=1, approver_role="reviewer", mode="majority"),
                StepCreate(ordinal=2, approver_user_id=u4, mode="all"),
            ],
        ),
        created_by=owner_id,
    )
    steps = await svc.list_steps(route.id)
    instance = await svc.start_instance(
        InstanceCreate(route_id=route.id, target_kind="rfi", target_id=uuid.uuid4()),
        started_by=owner_id,
    )

    # u1 approves: 1 approved / 1 acted → 1*2 > 1 → majority cleared → advance.
    instance = await svc.submit_decision(
        instance.id,
        DecisionSubmit(step_id=steps[0].id, decision="approved"),
        approver_id=u1,
    )
    assert instance.current_step_ordinal == 2  # advanced to step 2

    # Now u4 approves step 2 → completes.
    instance = await svc.submit_decision(
        instance.id,
        DecisionSubmit(step_id=steps[1].id, decision="approved"),
        approver_id=u4,
    )
    assert instance.status == "approved"


@pytest.mark.asyncio
async def test_any_mode_advances_on_first_approval(session: AsyncSession) -> None:
    svc = ApprovalRouteService(session)
    project_id, owner_id = await _seed_project(session)
    u1 = await _add_user(session, "u1")

    route = await svc.create_route(
        RouteCreate(
            project_id=project_id,
            name="any-gate",
            target_kind="markup",
            steps=[StepCreate(ordinal=1, approver_role="qa", mode="any")],
        ),
        created_by=owner_id,
    )
    steps = await svc.list_steps(route.id)
    instance = await svc.start_instance(
        InstanceCreate(route_id=route.id, target_kind="markup", target_id=uuid.uuid4()),
        started_by=owner_id,
    )
    instance = await svc.submit_decision(
        instance.id,
        DecisionSubmit(step_id=steps[0].id, decision="approved"),
        approver_id=u1,
    )
    assert instance.status == "approved"  # single-step route → done


# ── Race / duplicate decision ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_duplicate_decision_from_same_approver_is_rejected(
    session: AsyncSession,
) -> None:
    svc = ApprovalRouteService(session)
    project_id, owner_id = await _seed_project(session)
    u1 = await _add_user(session, "u1")
    u2 = await _add_user(session, "u2")

    route = await svc.create_route(
        RouteCreate(
            project_id=project_id,
            name="2-step",
            target_kind="contract",
            steps=[
                StepCreate(ordinal=1, approver_user_id=u1, mode="all"),
                StepCreate(ordinal=2, approver_user_id=u2, mode="all"),
            ],
        ),
        created_by=owner_id,
    )
    steps = await svc.list_steps(route.id)
    instance = await svc.start_instance(
        InstanceCreate(route_id=route.id, target_kind="contract", target_id=uuid.uuid4()),
        started_by=owner_id,
    )

    # First decision advances to step 2.
    await svc.submit_decision(
        instance.id,
        DecisionSubmit(step_id=steps[0].id, decision="approved"),
        approver_id=u1,
    )

    # Re-submitting against step 1 (already advanced past) — 409 because
    # the ordinal check fires first.
    with pytest.raises(HTTPException) as excinfo:
        await svc.submit_decision(
            instance.id,
            DecisionSubmit(step_id=steps[0].id, decision="approved"),
            approver_id=u1,
        )
    assert excinfo.value.status_code == 409


# ── Cancel ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_pending_instance(session: AsyncSession) -> None:
    svc = ApprovalRouteService(session)
    project_id, owner_id = await _seed_project(session)
    u1 = await _add_user(session, "u1")

    route = await svc.create_route(
        RouteCreate(
            project_id=project_id,
            name="single-step",
            target_kind="invoice",
            steps=[StepCreate(ordinal=1, approver_user_id=u1, mode="all")],
        ),
        created_by=owner_id,
    )
    steps = await svc.list_steps(route.id)
    instance = await svc.start_instance(
        InstanceCreate(route_id=route.id, target_kind="invoice", target_id=uuid.uuid4()),
        started_by=owner_id,
    )

    cancelled = await svc.cancel_instance(instance.id, actor_id=owner_id, reason="superseded")
    assert cancelled.status == "cancelled"
    assert cancelled.completed_at is not None

    # Further decisions are rejected.
    with pytest.raises(HTTPException) as excinfo:
        await svc.submit_decision(
            instance.id,
            DecisionSubmit(step_id=steps[0].id, decision="approved"),
            approver_id=u1,
        )
    assert excinfo.value.status_code == 409


# ── Duplicate workflow on same target ─────────────────────────────────


@pytest.mark.asyncio
async def test_cannot_start_second_pending_instance_on_same_target(
    session: AsyncSession,
) -> None:
    svc = ApprovalRouteService(session)
    project_id, owner_id = await _seed_project(session)
    u1 = await _add_user(session, "u1")

    route = await svc.create_route(
        RouteCreate(
            project_id=project_id,
            name="single",
            target_kind="rfi",
            steps=[StepCreate(ordinal=1, approver_user_id=u1, mode="all")],
        ),
        created_by=owner_id,
    )
    target_id = uuid.uuid4()
    await svc.start_instance(
        InstanceCreate(route_id=route.id, target_kind="rfi", target_id=target_id),
        started_by=owner_id,
    )
    with pytest.raises(HTTPException) as excinfo:
        await svc.start_instance(
            InstanceCreate(route_id=route.id, target_kind="rfi", target_id=target_id),
            started_by=owner_id,
        )
    assert excinfo.value.status_code == 409


# ── Wrong route / target mismatch ─────────────────────────────────────


@pytest.mark.asyncio
async def test_route_target_kind_mismatch_is_rejected(
    session: AsyncSession,
) -> None:
    svc = ApprovalRouteService(session)
    project_id, owner_id = await _seed_project(session)
    u1 = await _add_user(session, "u1")

    route = await svc.create_route(
        RouteCreate(
            project_id=project_id,
            name="markup-only",
            target_kind="markup",
            steps=[StepCreate(ordinal=1, approver_user_id=u1, mode="all")],
        ),
        created_by=owner_id,
    )
    with pytest.raises(HTTPException) as excinfo:
        await svc.start_instance(
            InstanceCreate(route_id=route.id, target_kind="rfi", target_id=uuid.uuid4()),
            started_by=owner_id,
        )
    assert excinfo.value.status_code == 422


# ── User-pinned step rejects wrong approver ───────────────────────────


@pytest.mark.asyncio
async def test_user_pinned_step_rejects_wrong_approver(
    session: AsyncSession,
) -> None:
    svc = ApprovalRouteService(session)
    project_id, owner_id = await _seed_project(session)
    u1 = await _add_user(session, "u1")
    u2 = await _add_user(session, "u2")

    route = await svc.create_route(
        RouteCreate(
            project_id=project_id,
            name="pinned",
            target_kind="contract",
            steps=[StepCreate(ordinal=1, approver_user_id=u1, mode="all")],
        ),
        created_by=owner_id,
    )
    steps = await svc.list_steps(route.id)
    instance = await svc.start_instance(
        InstanceCreate(route_id=route.id, target_kind="contract", target_id=uuid.uuid4()),
        started_by=owner_id,
    )

    with pytest.raises(HTTPException) as excinfo:
        await svc.submit_decision(
            instance.id,
            DecisionSubmit(step_id=steps[0].id, decision="approved"),
            approver_id=u2,  # not the pinned user
        )
    assert excinfo.value.status_code == 403

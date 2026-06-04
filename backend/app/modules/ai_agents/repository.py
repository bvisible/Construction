"""AI Agents data-access layer."""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_agents.models import AgentRun, AgentStep, CustomAgent


class AgentRunRepository:
    """CRUD-style helpers for :class:`AgentRun`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, run: AgentRun) -> AgentRun:
        """Insert a new run row and flush so it has an id."""
        self.session.add(run)
        await self.session.flush()
        return run

    async def get_by_id(self, run_id: uuid.UUID) -> AgentRun | None:
        stmt = select(AgentRun).where(AgentRun.id == run_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_runs(
        self,
        *,
        user_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list[AgentRun]:
        """Return runs ordered newest-first, scoped by user/project."""
        stmt = select(AgentRun).order_by(AgentRun.created_at.desc()).limit(limit)
        if user_id is not None:
            stmt = stmt.where(AgentRun.user_id == user_id)
        if project_id is not None:
            stmt = stmt.where(AgentRun.project_id == project_id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def update_fields(self, run_id: uuid.UUID, **fields: object) -> None:
        """Patch arbitrary scalar fields on a run row."""
        stmt = update(AgentRun).where(AgentRun.id == run_id).values(**fields)
        await self.session.execute(stmt)
        await self.session.flush()
        self.session.expire_all()


class AgentStepRepository:
    """CRUD-style helpers for :class:`AgentStep`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, step: AgentStep) -> AgentStep:
        self.session.add(step)
        await self.session.flush()
        return step

    async def list_for_run(self, run_id: uuid.UUID) -> list[AgentStep]:
        """Return every step for a run in chronological order."""
        stmt = select(AgentStep).where(AgentStep.run_id == run_id).order_by(AgentStep.step_idx.asc())
        return list((await self.session.execute(stmt)).scalars().all())


class CustomAgentRepository:
    """CRUD helpers for user-authored :class:`CustomAgent` rows.

    Every read is scoped by ``user_id`` so a caller can only ever see, run,
    edit, or delete their own custom agents (per-user privacy model shared
    with agent runs).
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, agent: CustomAgent) -> CustomAgent:
        self.session.add(agent)
        await self.session.flush()
        return agent

    async def get_for_user(self, agent_id: uuid.UUID, user_id: uuid.UUID) -> CustomAgent | None:
        """Return the custom agent if it exists AND belongs to ``user_id``."""
        stmt = select(CustomAgent).where(
            CustomAgent.id == agent_id,
            CustomAgent.user_id == user_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_for_user(self, user_id: uuid.UUID) -> list[CustomAgent]:
        """Return the caller's custom agents, newest first."""
        stmt = select(CustomAgent).where(CustomAgent.user_id == user_id).order_by(CustomAgent.created_at.desc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def update(self, agent: CustomAgent, **fields: object) -> CustomAgent:
        """Patch scalar fields on an owned custom agent and flush."""
        for key, value in fields.items():
            setattr(agent, key, value)
        await self.session.flush()
        return agent

    async def delete(self, agent: CustomAgent) -> None:
        await self.session.delete(agent)
        await self.session.flush()

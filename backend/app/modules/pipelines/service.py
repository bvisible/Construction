# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pipeline Builder business logic.

Owns: graph validation (registry + structural ``pipeline`` rule), JobRun
submission, run snapshotting and the read-model assembly that the router
serialises. Stateless — a fresh instance per request, like the other
modules' services.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pipeline.executor import (
    PIPELINE_JOB_KIND,
    GraphValidationError,
    validate_graph,
)
from app.core.validation.engine import validation_engine
from app.modules.pipelines.models import Pipeline, PipelineRun
from app.modules.pipelines.repository import PipelineRepository


def _node_count(graph: dict[str, Any]) -> int:
    return len(graph.get("nodes") or [])


def _as_uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


class PipelineService:
    """Stateless service for pipeline CRUD + run orchestration."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = PipelineRepository(session)

    # ── CRUD ─────────────────────────────────────────────────────────────

    async def create(
        self,
        *,
        name: str,
        description: str | None,
        project_id: str | None,
        graph: dict[str, Any],
        policy: dict[str, Any],
        created_by: str | None,
    ) -> Pipeline:
        """Create a pipeline (always starts unpublished)."""
        pipeline = Pipeline(
            name=name,
            description=description,
            project_id=_as_uuid(project_id),
            graph=graph,
            policy=policy or {},
            is_published=False,
            version=1,
            created_by=_as_uuid(created_by),
        )
        await self.repo.add(pipeline)
        await self.session.commit()
        await self.session.refresh(pipeline)
        return pipeline

    async def get(self, pipeline_id: uuid.UUID) -> Pipeline | None:
        return await self.repo.get(pipeline_id)

    async def list(
        self, *, project_id: str | None = None
    ) -> list[Pipeline]:
        return await self.repo.list(project_id=_as_uuid(project_id))

    async def update(
        self,
        pipeline: Pipeline,
        *,
        name: str | None = None,
        description: str | None = None,
        graph: dict[str, Any] | None = None,
        policy: dict[str, Any] | None = None,
        is_published: bool | None = None,
    ) -> Pipeline:
        """Patch a pipeline.

        Publishing is gated: a graph that fails the structural ``pipeline``
        validation rule (a side-effecting node without a gate on every path)
        cannot be published — :class:`GraphValidationError` is raised so the
        router returns 400 and the pipeline stays unpublished.
        """
        if name is not None:
            pipeline.name = name
        if description is not None:
            pipeline.description = description
        if graph is not None:
            pipeline.graph = graph
            pipeline.version += 1
        if policy is not None:
            pipeline.policy = policy
        if is_published is not None:
            if is_published:
                await self._assert_publishable(pipeline.graph or {})
            pipeline.is_published = is_published
        await self.session.commit()
        await self.session.refresh(pipeline)
        return pipeline

    async def delete(self, pipeline: Pipeline) -> None:
        await self.repo.delete(pipeline)
        await self.session.commit()

    # ── Validation ───────────────────────────────────────────────────────

    async def _assert_publishable(self, graph: dict[str, Any]) -> None:
        """Raise :class:`GraphValidationError` if the graph cannot publish.

        Two layers: (1) registry + acyclic check (``validate_graph``),
        (2) the structural ``pipeline`` rule ("every side-effecting node
        needs a gate on every path from a trigger/AI node"). The rule lives
        in the colocated core rule file and is run through the standard
        validation engine so the result format is identical to every other
        gate in the platform.
        """
        # Layer 1 — acyclic + all node types registered.
        validate_graph(graph)

        # Layer 2 — the "AI proposes, human confirms" structural gate.
        report = await validation_engine.validate(
            data={"graph": graph},
            rule_sets=["pipeline"],
            target_type="pipeline",
        )
        if report.has_errors:
            messages = "; ".join(r.message for r in report.errors)
            raise GraphValidationError(
                f"Pipeline graph fails the structural gate: {messages}"
            )

    # ── Runs ─────────────────────────────────────────────────────────────

    async def submit_run(
        self,
        pipeline: Pipeline,
        *,
        trigger: dict[str, Any],
        actor_id: str | None,
    ) -> tuple[PipelineRun, Any]:
        """Validate, snapshot and enqueue a run.

        The whole run is one ``JobRun`` of ``kind="pipeline.run"`` (§3.3).
        We freeze the graph into the run row first (immutable history),
        then submit the job with the run id in the payload. The idempotency
        key is the run id so a redelivered dispatch cannot double-run.

        Returns ``(pipeline_run, job_run)``.
        """
        graph = dict(pipeline.graph or {})
        # Reject a bad graph BEFORE creating the run (§3.5).
        validate_graph(graph)

        run = PipelineRun(
            pipeline_id=pipeline.id,
            graph_snapshot=graph,
            trigger=trigger,
            project_id=pipeline.project_id,
            tenant_id=pipeline.tenant_id,
            created_by=_as_uuid(actor_id),
        )
        await self.repo.add_run(run)
        await self.session.commit()
        await self.session.refresh(run)

        from app.core.job_runner import submit_job

        job = await submit_job(
            PIPELINE_JOB_KIND,
            {"run_id": str(run.id), "pipeline_id": str(pipeline.id)},
            idempotency_key=f"pipeline.run:{run.id}",
            tenant_id=pipeline.tenant_id,
        )

        run.job_run_id = job.id
        await self.session.commit()
        await self.session.refresh(run)
        return run, job

    async def get_run(self, run_id: uuid.UUID) -> PipelineRun | None:
        return await self.repo.get_run(run_id)

    async def list_runs(self, pipeline_id: uuid.UUID) -> list[PipelineRun]:
        return await self.repo.list_runs(pipeline_id)

    async def run_read_model(self, run: PipelineRun) -> dict[str, Any]:
        """Assemble the run-detail read model (run + JobRun + node states).

        Maps the durable ``JobRun`` lifecycle onto a UI-friendly status
        string and threads the per-node states in start order.
        """
        from app.core.job_run import JobRun

        job: JobRun | None = None
        if run.job_run_id is not None:
            job = await self.session.get(JobRun, run.job_run_id)

        node_states = await self.repo.list_node_states(run.id)
        nodes = [
            {
                "node_id": ns.node_id,
                "node_type": ns.node_type,
                "status": ns.status,
                "output": dict(ns.output or {}),
                "error": ns.error,
                "took_ms": ns.took_ms,
                "started_at": ns.started_at.isoformat()
                if ns.started_at
                else None,
                "finished_at": ns.finished_at.isoformat()
                if ns.finished_at
                else None,
            }
            for ns in node_states
        ]

        status = job.status if job is not None else "pending"
        progress = job.progress_percent if job is not None else 0
        error: str | None = None
        if job is not None and job.error_jsonb:
            error = job.error_jsonb.get("message")
        started_at = (
            job.started_at.isoformat()
            if job is not None and job.started_at
            else None
        )
        finished_at = (
            job.completed_at.isoformat()
            if job is not None and job.completed_at
            else None
        )

        return {
            "id": str(run.id),
            "pipeline_id": str(run.pipeline_id),
            "status": status,
            "progress_percent": progress,
            "started_at": started_at,
            "finished_at": finished_at,
            "error": error,
            "nodes": nodes,
        }

    async def run_summary(self, run: PipelineRun) -> dict[str, Any]:
        """Compact run row for the run-list endpoint."""
        from app.core.job_run import JobRun

        job: JobRun | None = None
        if run.job_run_id is not None:
            job = await self.session.get(JobRun, run.job_run_id)
        return {
            "id": str(run.id),
            "status": job.status if job is not None else "pending",
            "trigger": dict(run.trigger or {}),
            "started_at": job.started_at.isoformat()
            if job is not None and job.started_at
            else None,
            "finished_at": job.completed_at.isoformat()
            if job is not None and job.completed_at
            else None,
            "progress_percent": job.progress_percent if job is not None else 0,
        }

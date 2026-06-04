"""AI Agents service — business logic for starting and inspecting runs.

The service is what wires the in-process :class:`AgentRunner` to:
    1. The DB-backed :class:`AgentRun` / :class:`AgentStep` persistence.
    2. The production LLM bridge (or whichever bridge the caller injects).
    3. The user's AI settings (provider + api_key + model id).

Tests instantiate the service with a custom LLM bridge to avoid hitting
external providers; production passes ``None`` and the service resolves
the bridge via :mod:`app.modules.ai.ai_client`.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_agents.base import (
    Agent,
    AgentResult,
    AgentRunner,
    LLMBridge,
    StepRecord,
    ToolRegistry,
    get_agent,
    global_tool_registry,
    list_agents,
)
from app.modules.ai_agents.models import (
    CUSTOM_AGENT_PREFIX,
    AgentRun,
    AgentStep,
    CustomAgent,
)
from app.modules.ai_agents.repository import (
    AgentRunRepository,
    AgentStepRepository,
    CustomAgentRepository,
)

logger = logging.getLogger(__name__)


# Conservative caps for user-authored agents. They are prompt-only (no tools),
# so a single LLM turn is the normal path; the small loop cap is just a guard.
CUSTOM_AGENT_MAX_ITERATIONS = 3


def compile_guided_prompt(guided: dict[str, Any]) -> str:
    """Build a well-formed system prompt from the friendly guided-builder fields.

    A non-technical user never writes a raw prompt: they answer a few plain
    questions (role, goal, audience, output format, extra guidance) and this
    function assembles a coherent, instruction-style system prompt from
    whatever they filled in. Only ``goal`` is required; empty fields are
    skipped so a sparse spec still yields a clean prompt.

    The compiled prompt always ends with the platform's "assistant, not
    autopilot" guardrail (state assumptions, never fabricate project specifics)
    so user agents behave as safely as the built-in advisors.
    """
    role = (guided.get("role") or "").strip()
    goal = (guided.get("goal") or "").strip()
    audience = (guided.get("audience") or "").strip()
    output_format = (guided.get("output_format") or "").strip()
    extra = (guided.get("extra_guidance") or "").strip()

    parts: list[str] = []
    if role:
        parts.append(f"You are {role}.")
    else:
        parts.append("You are a knowledgeable construction assistant.")
    if goal:
        parts.append(f"Your job is to help with the following: {goal}")
    if audience:
        parts.append(f"Your answer is for: {audience}. Pitch it accordingly.")
    if output_format:
        parts.append(f"Present your answer like this: {output_format}.")
    if extra:
        parts.append(f"Also keep this in mind: {extra}")

    parts.append(
        "Be concrete and practical. State any assumptions explicitly. Do not "
        "invent project-specific facts, quantities, prices, names, or dates "
        "you were not given; where a real figure or a professional judgement "
        "is needed, ask for it or leave a clearly marked placeholder. The "
        "person you are helping will review and confirm your output."
    )
    return " ".join(parts)


def _resolve_system_prompt(
    *,
    guided: dict[str, Any] | None,
    raw_prompt: str,
) -> str:
    """Pick the effective system prompt for a custom agent.

    Guided spec wins (compiled); otherwise the raw prompt is used as-is. Raises
    ``ValueError`` when neither yields any prompt text so the API can 422.
    """
    if guided:
        compiled = compile_guided_prompt(guided)
        if compiled.strip():
            return compiled
    raw = (raw_prompt or "").strip()
    if raw:
        return raw
    msg = "A custom agent needs either a guided spec with a goal, or a system prompt."
    raise ValueError(msg)


def custom_agent_to_runtime(row: CustomAgent) -> Agent:
    """Project a DB :class:`CustomAgent` row into a runnable :class:`Agent`.

    The runner only ever sees a declarative :class:`Agent`; custom agents are
    prompt-only (``allowed_tools=[]``) so the loop returns the model's first
    answer. The runtime ``name`` is the ``custom:<id>`` slug so the run path
    and persisted ``AgentRun.agent_name`` round-trip unambiguously.
    """
    return Agent(
        name=row.agent_name,
        display_name=row.display_name,
        description=row.description or row.tagline or "",
        tagline=row.tagline or "",
        category=row.category or "general",
        icon=row.icon or "sparkles",
        example_prompts=list(row.example_prompts or []),
        system_prompt=row.system_prompt,
        allowed_tools=[],
        max_iterations=CUSTOM_AGENT_MAX_ITERATIONS,
    )


def _iso_now() -> str:
    """Wall-clock UTC ISO string (kept short to fit String(40))."""
    return _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds")


async def _resolve_production_llm(session: AsyncSession, user_id: uuid.UUID) -> LLMBridge | None:
    """Pull the user's AI settings and build a :class:`CallAILLM` bridge.

    Returns ``None`` when no API key is configured — the caller decides
    whether that's a hard error (it is, for ``run_agent``).
    """
    try:
        from app.modules.ai.ai_client import resolve_provider_key_model
        from app.modules.ai.repository import AISettingsRepository
        from app.modules.ai_agents.llm import CallAILLM
    except Exception as exc:  # pragma: no cover - import safety
        logger.warning("AI module unavailable for agent runner: %s", exc)
        return None

    settings = await AISettingsRepository(session).get_by_user_id(user_id)
    try:
        provider, api_key, model = resolve_provider_key_model(settings)
    except ValueError:
        return None
    return CallAILLM(provider=provider, api_key=api_key, model=model)


def _humanize_agent(name: str) -> str:
    """Turn an agent slug (``boq_generator``) into a label (``Boq Generator``)."""
    return name.replace("_", " ").replace("-", " ").strip().title() or "AI agent"


def _coerce_confidence(value: Any) -> float | None:
    """Normalise a confidence to the 0.0-1.0 range the UI expects.

    Agents emit confidence on either a 0-1 or a 0-100 scale; anything above 1
    is treated as a percentage and divided down. Non-numeric input yields None.
    """
    try:
        conf = float(value)
    except (TypeError, ValueError):
        return None
    if conf > 1.0:
        conf = conf / 100.0
    return max(0.0, min(conf, 1.0))


def _run_to_insight(run: AgentRun) -> dict[str, Any]:
    """Distill one completed :class:`AgentRun` into a project-insight card.

    Structured JSON output (``{"title", "summary", "confidence", "severity"}``)
    is used directly; plain-text output falls back to the agent's humanised name
    as the title and its first line as the summary. This is real run output, not
    a placeholder.
    """
    raw = (run.final_output or "").strip()
    title: str | None = None
    summary: str | None = None
    confidence: float | None = None
    severity: str | None = None

    if raw.startswith("{"):
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            payload = None
        if isinstance(payload, dict):
            title = payload.get("title") or payload.get("headline")
            summary = payload.get("summary") or payload.get("message") or payload.get("recommendation")
            confidence = _coerce_confidence(payload.get("confidence"))
            sev = payload.get("severity")
            severity = str(sev) if sev is not None else None

    if not title:
        title = _humanize_agent(run.agent_name)
    if not summary:
        first_line = next((ln.strip() for ln in raw.splitlines() if ln.strip()), "")
        summary = (first_line[:200] + "...") if len(first_line) > 200 else (first_line or None)
    if severity is None:
        severity = "info"

    return {
        "id": str(run.id),
        "title": str(title)[:200],
        "summary": summary,
        "confidence": confidence,
        "severity": severity,
    }


class AgentService:
    """High-level façade over the runner + persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.run_repo = AgentRunRepository(session)
        self.step_repo = AgentStepRepository(session)
        self.custom_repo = CustomAgentRepository(session)

    # ── Catalogue ────────────────────────────────────────────────────────

    def list_registered_agents(self) -> list[Agent]:
        return list_agents()

    async def list_custom_agents(self, user_id: uuid.UUID) -> list[CustomAgent]:
        """Return the caller's user-authored custom agent rows (newest first)."""
        return await self.custom_repo.list_for_user(user_id)

    async def list_catalogue_agents(self, user_id: uuid.UUID) -> list[tuple[Agent, CustomAgent | None]]:
        """Built-in + the caller's custom agents, as ``(Agent, row|None)`` pairs.

        Built-ins come from the in-memory registry (``row`` is ``None``); the
        caller's custom agents are projected to runnable :class:`Agent`\\s with
        their DB row attached so the router can flag them ``is_custom`` and
        surface the row id for edit/delete. Custom agents come first so a
        user's own helpers sit at the top of the catalogue.
        """
        custom_rows = await self.custom_repo.list_for_user(user_id)
        pairs: list[tuple[Agent, CustomAgent | None]] = [(custom_agent_to_runtime(row), row) for row in custom_rows]
        pairs.extend((a, None) for a in list_agents())
        return pairs

    async def resolve_agent(self, agent_name: str, user_id: uuid.UUID) -> Agent | None:
        """Resolve a runtime :class:`Agent` by name for a given caller.

        ``custom:<id>`` slugs resolve from the DB (and only if the agent
        belongs to ``user_id`` — a user cannot run another user's custom
        agent); everything else resolves from the built-in registry.
        """
        if agent_name.startswith(CUSTOM_AGENT_PREFIX):
            raw_id = agent_name[len(CUSTOM_AGENT_PREFIX) :]
            try:
                custom_id = uuid.UUID(raw_id)
            except (ValueError, TypeError):
                return None
            row = await self.custom_repo.get_for_user(custom_id, user_id)
            return custom_agent_to_runtime(row) if row is not None else None
        return get_agent(agent_name)

    # ── Custom-agent CRUD ─────────────────────────────────────────────────

    async def create_custom_agent(
        self,
        *,
        user_id: uuid.UUID,
        display_name: str,
        tagline: str,
        description: str,
        category: str,
        icon: str,
        example_prompts: list[str],
        guided: dict[str, Any] | None,
        system_prompt: str,
    ) -> CustomAgent:
        """Create a custom agent for ``user_id``. Raises ValueError on no prompt."""
        effective_prompt = _resolve_system_prompt(guided=guided, raw_prompt=system_prompt)
        row = CustomAgent(
            user_id=user_id,
            display_name=display_name,
            tagline=tagline,
            description=description,
            category=category or "general",
            icon=icon or "sparkles",
            example_prompts=[p for p in example_prompts if p and p.strip()],
            guided=guided,
            system_prompt=effective_prompt,
        )
        return await self.custom_repo.create(row)

    async def get_custom_agent(self, agent_id: uuid.UUID, user_id: uuid.UUID) -> CustomAgent | None:
        return await self.custom_repo.get_for_user(agent_id, user_id)

    async def update_custom_agent(
        self,
        *,
        agent_id: uuid.UUID,
        user_id: uuid.UUID,
        display_name: str,
        tagline: str,
        description: str,
        category: str,
        icon: str,
        example_prompts: list[str],
        guided: dict[str, Any] | None,
        system_prompt: str,
    ) -> CustomAgent | None:
        """Full-replace an owned custom agent. Returns None when not found/owned."""
        row = await self.custom_repo.get_for_user(agent_id, user_id)
        if row is None:
            return None
        effective_prompt = _resolve_system_prompt(guided=guided, raw_prompt=system_prompt)
        return await self.custom_repo.update(
            row,
            display_name=display_name,
            tagline=tagline,
            description=description,
            category=category or "general",
            icon=icon or "sparkles",
            example_prompts=[p for p in example_prompts if p and p.strip()],
            guided=guided,
            system_prompt=effective_prompt,
        )

    async def delete_custom_agent(self, agent_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Delete an owned custom agent. Returns False when not found/owned."""
        row = await self.custom_repo.get_for_user(agent_id, user_id)
        if row is None:
            return False
        await self.custom_repo.delete(row)
        return True

    def list_registered_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in global_tool_registry.all()
        ]

    # ── Run lifecycle ────────────────────────────────────────────────────

    async def start_run(
        self,
        *,
        user_id: uuid.UUID,
        agent_name: str,
        user_input: str,
        project_id: uuid.UUID | None = None,
        llm: LLMBridge | None = None,
        tool_registry: ToolRegistry | None = None,
    ) -> AgentRun:
        """Create the run row, execute the loop synchronously, and persist steps.

        "Background task" wiring (``BackgroundTasks.add_task``) lives in
        the router — here we just run the loop. The router can choose to
        ``await`` us inline (tests do) or schedule us for later.
        """
        agent = get_agent(agent_name)
        if agent is None:
            msg = f"Unknown agent: {agent_name}"
            raise ValueError(msg)

        run = AgentRun(
            agent_name=agent_name,
            project_id=project_id,
            user_id=user_id,
            status="running",
            user_input=user_input,
            iterations=0,
            total_tokens=0,
            started_at=_iso_now(),
        )
        run = await self.run_repo.create(run)
        run_id = run.id

        # Resolve LLM bridge (caller may inject one for tests).
        bridge = llm
        if bridge is None:
            bridge = await _resolve_production_llm(self.session, user_id)
        if bridge is None:
            await self.run_repo.update_fields(
                run_id,
                status="failed",
                failure_reason="no_llm",
                finished_at=_iso_now(),
            )
            refreshed = await self.run_repo.get_by_id(run_id)
            assert refreshed is not None  # noqa: S101
            return refreshed

        step_counter = {"i": 0}

        async def _persist(step: StepRecord) -> None:
            step_counter["i"] += 1
            await self.step_repo.create(
                AgentStep(
                    run_id=run_id,
                    step_idx=step_counter["i"],
                    role=step.role,
                    content=step.content,
                    token_count=step.token_count,
                )
            )

        runner = AgentRunner(bridge, on_step=_persist)
        context = {"project_id": str(project_id)} if project_id else None

        try:
            result: AgentResult = await runner.run(
                agent,
                user_input,
                context=context,
                tool_registry=tool_registry,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Agent run %s crashed", run_id)
            await self.run_repo.update_fields(
                run_id,
                status="failed",
                failure_reason="exception",
                final_output=str(exc)[:500],
                finished_at=_iso_now(),
            )
            refreshed = await self.run_repo.get_by_id(run_id)
            assert refreshed is not None  # noqa: S101
            return refreshed

        await self.run_repo.update_fields(
            run_id,
            status=result.status,
            failure_reason=result.failure_reason,
            final_output=result.final_output,
            iterations=result.iterations,
            total_tokens=result.total_tokens,
            finished_at=_iso_now(),
        )
        refreshed = await self.run_repo.get_by_id(run_id)
        assert refreshed is not None  # noqa: S101
        return refreshed

    # ── Read ─────────────────────────────────────────────────────────────

    async def get_run(self, run_id: uuid.UUID) -> AgentRun | None:
        return await self.run_repo.get_by_id(run_id)

    async def get_run_steps(self, run_id: uuid.UUID) -> list[AgentStep]:
        return await self.step_repo.list_for_run(run_id)

    async def list_runs(
        self,
        *,
        user_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list[AgentRun]:
        return await self.run_repo.list_runs(
            user_id=user_id,
            project_id=project_id,
            limit=limit,
        )

    async def project_insights(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        limit: int = 2,
    ) -> list[dict[str, Any]]:
        """Return the user's most recent useful AI results for a project.

        Only completed runs that produced output become insights, so we
        over-fetch recent runs and stop once ``limit`` real insights are
        collected. Scoped to the caller's own runs, mirroring the privacy
        model of the run-detail endpoint.
        """
        runs = await self.run_repo.list_runs(
            user_id=user_id,
            project_id=project_id,
            limit=max(limit * 5, 10),
        )
        insights: list[dict[str, Any]] = []
        for run in runs:
            if run.status != "completed" or not (run.final_output or "").strip():
                continue
            insights.append(_run_to_insight(run))
            if len(insights) >= limit:
                break
        return insights

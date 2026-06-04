"""AI Agents Pydantic schemas — request/response models."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ── Agent metadata ──────────────────────────────────────────────────────────


class AgentDescriptor(BaseModel):
    """A registered agent surfaced to clients.

    Both built-in agents (from the in-memory registry) and user-authored
    custom agents (from the DB) are serialised through this one schema so the
    frontend renders them identically in the catalogue. ``is_custom`` lets the
    UI show edit/delete affordances only on the caller's own custom agents.
    """

    name: str
    description: str
    system_prompt: str = ""
    max_iterations: int = 8
    allowed_tools: list[str] = Field(default_factory=list)

    # Presentation metadata for the catalogue UI (see base.Agent).
    display_name: str = ""
    category: str = "general"
    icon: str = "bot"
    tagline: str = ""
    example_prompts: list[str] = Field(default_factory=list)

    # True for user-authored agents (DB-backed, editable by their creator).
    is_custom: bool = False
    # Present only for custom agents — the row id, so the UI can edit/delete.
    custom_id: UUID | None = None


class ToolDescriptor(BaseModel):
    """A tool the agent runner can dispatch to."""

    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)


# ── Run create / read ───────────────────────────────────────────────────────


class CreateAgentRunRequest(BaseModel):
    """Request body for ``POST /ai-agents/runs/``."""

    model_config = ConfigDict(str_strip_whitespace=True)

    agent_name: str = Field(..., min_length=1, max_length=100)
    project_id: UUID | None = None
    user_input: str = Field(..., min_length=1, max_length=10_000)


class AgentStepResponse(BaseModel):
    """One step in a run's vertical timeline."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    step_idx: int
    role: str
    content: Any = None
    token_count: int = 0
    created_at: datetime


class AgentRunResponse(BaseModel):
    """Full run snapshot — status, totals, every step so far."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_name: str
    project_id: UUID | None = None
    user_id: UUID
    status: str
    failure_reason: str | None = None
    user_input: str
    final_output: str | None = None
    iterations: int = 0
    total_tokens: int = 0
    started_at: str | None = None
    finished_at: str | None = None
    created_at: datetime
    updated_at: datetime
    steps: list[AgentStepResponse] = Field(default_factory=list)


class AgentRunListItem(BaseModel):
    """Lightweight row for the run list endpoint (no steps)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_name: str
    project_id: UUID | None = None
    user_id: UUID
    status: str
    failure_reason: str | None = None
    iterations: int = 0
    total_tokens: int = 0
    created_at: datetime
    updated_at: datetime


class AgentInsightResponse(BaseModel):
    """One AI insight for a project, distilled from a completed agent run.

    Surfaced by ``GET /ai-agents/insights`` on the project dashboard. There is
    no separate "insight" table: each insight is the result of a real agent run
    the user executed against the project, so the widget reflects actual AI
    output rather than a placeholder.
    """

    id: str
    title: str
    summary: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    severity: str | None = None


# ── Health ──────────────────────────────────────────────────────────────────


class AgentHealthResponse(BaseModel):
    """Pre-flight check so the UI can warn before the user wastes a click.

    Returned by ``GET /ai-agents/health/``. ``llm_configured`` is the only
    field the UI strictly needs; ``provider`` / ``model`` are surfaced so
    the page can show "Will run on Anthropic claude-sonnet-4-5" reassurance.
    """

    llm_configured: bool
    provider: str | None = None
    model: str | None = None
    settings_url: str = "/settings?tab=ai"


# ── Custom agents (user-authored) ─────────────────────────────────────────────

# Catalogue categories a custom agent may be filed under. Kept in sync with the
# built-in agents' categories and the frontend category map so a custom agent
# slots into an existing section instead of spawning a lone group.
CUSTOM_AGENT_CATEGORIES = (
    "estimating",
    "quality",
    "documents",
    "analytics",
    "planning",
    "general",
)


class GuidedAgentSpec(BaseModel):
    """The friendly, guided builder input a non-technical user fills in.

    Rather than asking the user to write a raw system prompt, the builder
    collects a few plain-language fields and the backend compiles them into a
    well-formed system prompt (see ``service.compile_guided_prompt``). All
    fields except ``goal`` are optional so the form stays light; the more the
    user fills in, the sharper the resulting agent.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    # "Act as a ..." — the expert role the agent should play.
    role: str = Field("", max_length=200)
    # The single most important field: what should this agent help with / do.
    goal: str = Field(..., min_length=3, max_length=2000)
    # Who the answer is for (client, site team, junior estimator, ...).
    audience: str = Field("", max_length=200)
    # How the answer should be shaped (checklist, table, short email, ...).
    output_format: str = Field("", max_length=400)
    # Anything to avoid or always include (tone, length, must-nots).
    extra_guidance: str = Field("", max_length=2000)


class CustomAgentCreateRequest(BaseModel):
    """Request body for ``POST /ai-agents/custom/``.

    The caller supplies the card metadata plus EITHER a guided spec (preferred,
    compiled into a system prompt server-side) OR a ready-made ``system_prompt``
    (advanced escape hatch). At least one of the two must be present.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    display_name: str = Field(..., min_length=2, max_length=120)
    tagline: str = Field("", max_length=280)
    description: str = Field("", max_length=2000)
    category: str = Field("general", max_length=40)
    icon: str = Field("sparkles", max_length=40)
    example_prompts: list[str] = Field(default_factory=list, max_length=6)

    # Guided builder fields (preferred path).
    guided: GuidedAgentSpec | None = None
    # Advanced raw prompt (used as-is when no guided spec is given).
    system_prompt: str = Field("", max_length=8000)


class CustomAgentUpdateRequest(BaseModel):
    """Request body for ``PUT /ai-agents/custom/{id}`` — full replace.

    Same shape as create; the agent is rewritten from these values. Keeping it
    a full replace (rather than a sparse patch) matches how the builder form
    submits its complete state.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    display_name: str = Field(..., min_length=2, max_length=120)
    tagline: str = Field("", max_length=280)
    description: str = Field("", max_length=2000)
    category: str = Field("general", max_length=40)
    icon: str = Field("sparkles", max_length=40)
    example_prompts: list[str] = Field(default_factory=list, max_length=6)
    guided: GuidedAgentSpec | None = None
    system_prompt: str = Field("", max_length=8000)


class CustomAgentResponse(BaseModel):
    """A user-authored custom agent row, returned by the custom-agent CRUD.

    Carries the compiled ``system_prompt`` and the ``guided`` spec (when the
    agent was built with the guided flow) so the edit form can re-hydrate the
    friendly fields instead of confronting the user with the raw prompt.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    display_name: str
    tagline: str = ""
    description: str = ""
    category: str = "general"
    icon: str = "sparkles"
    example_prompts: list[str] = Field(default_factory=list)
    system_prompt: str = ""
    guided: GuidedAgentSpec | None = None
    created_at: datetime
    updated_at: datetime

"""‌⁠‍Risk Register Pydantic schemas — request/response models.

Defines create, update, and response schemas for risk register items.
Numeric values (probability, impact_cost, risk_score, response_cost) are exposed
as floats in the API but stored as strings in SQLite-compatible models.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ── Shared controlled vocabularies (single source of truth) ──────────────
#
# These tuples are the canonical vocabularies for risk severity and status.
# `service.py` builds its numeric scoring maps (SEVERITY_NUMERIC /
# IMPACT_SCORE_MAP) from SEVERITY_LEVELS so the request schema and the
# service-side mapping can never drift apart again (F-PFO-RISK-03 /
# F-PFO-RISK-05). schemas.py is imported by service.py (one direction
# only), so keeping the vocabulary here avoids a circular import.

# Canonical PMBOK 5-level severity scale, low→critical, ordered by rank.
SEVERITY_CANONICAL: tuple[str, ...] = (
    "very_low",
    "low",
    "medium",
    "high",
    "critical",
)
# Legacy / alternate enum spellings that map onto the canonical scale at
# the same rank (negligible≈very_low … catastrophic≈critical). Accepted on
# input so existing seed / demo / imported data keeps validating.
SEVERITY_ALIASES: tuple[str, ...] = (
    "negligible",
    "minor",
    "moderate",
    "major",
    "catastrophic",
)
SEVERITY_LEVELS: tuple[str, ...] = SEVERITY_CANONICAL + SEVERITY_ALIASES
_SEVERITY_PATTERN = r"^(?:" + "|".join(SEVERITY_LEVELS) + r")$"

# Risk lifecycle status vocabulary. The model default is "identified".
# Seed / demo rows are written with "open", "monitoring" and "mitigated"
# (see core/demo_projects.py), so those MUST be a subset of what
# RiskCreate / RiskUpdate accept or seeded risks become un-editable.
STATUS_VALUES: tuple[str, ...] = (
    "identified",
    "assessed",
    "mitigating",
    "monitoring",
    "mitigated",
    "open",
    "closed",
    "occurred",
)
_STATUS_PATTERN = r"^(?:" + "|".join(STATUS_VALUES) + r")$"

# ── Risk schemas ─────────────────────────────────────────────────────────


class RiskCreate(BaseModel):
    """‌⁠‍Create a new risk item."""

    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: UUID
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(default="", max_length=5000)
    category: str = Field(
        default="technical",
        pattern=r"^(technical|financial|schedule|regulatory|environmental|safety)$",
    )
    probability: float = Field(default=0.5, ge=0.0, le=1.0)
    impact_cost: float = Field(default=0.0, ge=0.0)
    impact_schedule_days: int = Field(default=0, ge=0)
    impact_severity: str = Field(
        default="medium",
        pattern=_SEVERITY_PATTERN,
    )
    status: str = Field(
        default="identified",
        pattern=_STATUS_PATTERN,
    )
    mitigation_strategy: str = Field(default="", max_length=5000)
    contingency_plan: str = Field(default="", max_length=5000)
    owner_name: str = Field(default="", max_length=255)
    owner_user_id: UUID | None = None
    response_cost: float = Field(default=0.0, ge=0.0)
    # Currency is data-driven: resolved from the owning project at create
    # time (see RiskService.create_risk). An explicit value here overrides
    # the project default; "" means "inherit from project / unknown".
    currency: str = Field(default="", max_length=10)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RiskUpdate(BaseModel):
    """‌⁠‍Partial update for a risk item."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    category: str | None = Field(
        default=None,
        pattern=r"^(technical|financial|schedule|regulatory|environmental|safety)$",
    )
    probability: float | None = Field(default=None, ge=0.0, le=1.0)
    impact_cost: float | None = Field(default=None, ge=0.0)
    impact_schedule_days: int | None = Field(default=None, ge=0)
    impact_severity: str | None = Field(
        default=None,
        pattern=_SEVERITY_PATTERN,
    )
    status: str | None = Field(
        default=None,
        pattern=_STATUS_PATTERN,
    )
    mitigation_strategy: str | None = Field(default=None, max_length=5000)
    contingency_plan: str | None = Field(default=None, max_length=5000)
    owner_name: str | None = Field(default=None, max_length=255)
    owner_user_id: UUID | None = None
    response_cost: float | None = Field(default=None, ge=0.0)
    currency: str | None = Field(default=None, max_length=10)
    metadata: dict[str, Any] | None = None


class RiskResponse(BaseModel):
    """Risk item returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    project_id: UUID
    code: str
    title: str
    description: str
    category: str
    probability: float = 0.5
    impact_cost: float = 0.0
    impact_schedule_days: int = 0
    impact_severity: str = "medium"
    risk_score: float = 0.0
    # 5x5 PMBOK matrix scoring — computed server-side from probability +
    # impact_severity. The frontend heatmap depends on these being present.
    probability_score: int | None = None
    impact_score_cost: int | None = None
    impact_score_time: int | None = None
    risk_tier: str | None = None
    status: str = "identified"
    mitigation_strategy: str = ""
    contingency_plan: str = ""
    owner_name: str = ""
    owner_user_id: UUID | None = None
    response_cost: float = 0.0
    currency: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


# ── Summary schema ───────────────────────────────────────────────────────


class TopRisk(BaseModel):
    """A high-scoring risk for display in stats."""

    title: str
    score: float


class RiskSummary(BaseModel):
    """Aggregated risk stats for a project."""

    total: int = 0
    total_risks: int = 0
    by_status: dict[str, int] = Field(default_factory=dict)
    by_tier: dict[str, int] = Field(default_factory=dict)
    by_category: dict[str, int] = Field(default_factory=dict)
    high_critical_count: int = 0
    avg_risk_score: float = 0.0
    total_exposure: float = 0.0
    with_mitigation: int = 0
    without_mitigation: int = 0
    mitigated_count: int = 0
    top_risks: list[TopRisk] = Field(default_factory=list)
    # Project currency (data-driven, resolved from the owning project).
    # "" means unknown — the UI must render a currency-less number rather
    # than mislabelling, e.g., AED exposure as EUR.
    currency: str = ""
    # Per-currency exposure breakdown. `total_exposure` is only meaningful
    # when every risk shares one currency; when they don't (mixed imports)
    # this map keeps each currency's exposure separate instead of summing
    # heterogeneous amounts under one last-wins label (F-PFO-RISK-04).
    exposure_by_currency: dict[str, float] = Field(default_factory=dict)


# ── Risk Matrix schema ───────────────────────────────────────────────────


class RiskMatrixCell(BaseModel):
    """Single cell in the 5x5 risk matrix."""

    probability_level: str
    impact_level: str
    count: int = 0
    risk_ids: list[UUID] = Field(default_factory=list)


class RiskMatrixResponse(BaseModel):
    """5x5 risk matrix data."""

    cells: list[RiskMatrixCell] = Field(default_factory=list)

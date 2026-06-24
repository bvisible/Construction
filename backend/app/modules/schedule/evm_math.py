"""Pure earned-value (EVM) math for the 4D schedule slice.

This module is deliberately dependency-free: it imports nothing from the ORM,
the DB engine, FastAPI or the rest of the app. That keeps the earned-value
rollup a *pure* function that can be unit-tested in isolation (and on Python
3.11 locally, where importing ``service_4d`` would otherwise pull in
``app.database`` and require a live PostgreSQL cluster).

``service_4d`` re-exports :class:`EvmCostRow`, :class:`EvmSummary` and
:func:`compute_evm_summary` so existing call sites keep working unchanged.

EVM identities used here (PMBOK):

* PV  (BCWS): budgeted cost of work *scheduled* by the data date.
* EV  (BCWP): budgeted cost of work *performed* = BAC * progress%.
* AC  (ACWP): actual cost incurred to date.
* BAC: Budget At Completion = Σ planned cost.
* SV  = EV - PV ; CV = EV - AC.
* SPI = EV / PV ; CPI = EV / AC.
* EAC = BAC / CPI (CPI method) ; ETC = EAC - AC ; VAC = BAC - EAC.

Ratio / forecast fields are ``None`` rather than ``0`` when a denominator is
zero (division by zero is undefined), so the UI can render "not available"
deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class EvmCostRow:
    """Minimal cost-loaded view of one activity for the EVM rollup.

    Decoupled from the ORM ``Activity`` so the rollup stays a pure function.
    ``cost_planned`` / ``cost_actual`` are the raw Decimal-or-None columns;
    ``progress_pct`` is the activity's stored progress string ("0".."100").
    """

    start_date: str | None
    end_date: str | None
    cost_planned: Decimal | None
    cost_actual: Decimal | None
    progress_pct: str | None


@dataclass
class EvmSummary:
    """Scalar earned-value metrics for a schedule at a data date.

    All money fields are plain floats (the router serialises them as strings
    to honour the Decimal-as-string wire contract). Ratio fields (``spi`` /
    ``cpi``) and the derived ``eac`` / ``etc`` / ``vac`` are ``None`` when the
    schedule carries no cost data or the denominator is zero.
    """

    planned_value: float  # PV / BCWS, time-phased to the data date
    earned_value: float  # EV / BCWP
    actual_cost: float  # AC / ACWP
    budget_at_completion: float  # BAC = Σ cost_planned
    schedule_variance: float  # SV = EV - PV
    cost_variance: float  # CV = EV - AC
    spi: float | None  # SPI = EV / PV
    cpi: float | None  # CPI = EV / AC
    estimate_at_completion: float | None  # EAC = BAC / CPI
    estimate_to_complete: float | None  # ETC = EAC - AC
    variance_at_completion: float | None  # VAC = BAC - EAC
    has_cost_data: bool

    def to_json(self) -> dict[str, Any]:
        return {
            "planned_value": self.planned_value,
            "earned_value": self.earned_value,
            "actual_cost": self.actual_cost,
            "budget_at_completion": self.budget_at_completion,
            "schedule_variance": self.schedule_variance,
            "cost_variance": self.cost_variance,
            "spi": self.spi,
            "cpi": self.cpi,
            "estimate_at_completion": self.estimate_at_completion,
            "estimate_to_complete": self.estimate_to_complete,
            "variance_at_completion": self.variance_at_completion,
            "has_cost_data": self.has_cost_data,
        }


def _parse_iso(value: str | None) -> date | None:
    """Parse an ISO ``YYYY-MM-DD`` (or full ISO datetime) prefix into a date."""
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _decimal_to_float(value: Decimal | None) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return 0.0


def coerce_progress_value(raw: str | None) -> float:
    """Coerce a stored ``progress_pct`` string to a 0..100 float (clamped)."""
    try:
        value = float(raw) if raw is not None else 0.0
    except (TypeError, ValueError):
        return 0.0
    if value < 0.0:
        return 0.0
    if value > 100.0:
        return 100.0
    return value


def planned_value_for_dates(
    start_date: str | None,
    end_date: str | None,
    bac: float,
    as_of_date: date,
) -> float:
    """Time-phased planned value for one activity given its raw date strings.

    An activity whose planned end is on or before the data date contributes its
    full budget; one in progress contributes a linear proration over its
    planned ``[start, end]`` span; one not yet started (or with unparseable
    dates) contributes nothing. This mirrors the S-curve PV proration so the
    scalar PV and the final S-curve point agree.
    """
    if not bac:
        return 0.0
    start = _parse_iso(start_date)
    end = _parse_iso(end_date)
    if start is None or end is None:
        return 0.0
    if as_of_date >= end:
        return bac
    if as_of_date < start:
        return 0.0
    duration = max((end - start).days, 1)
    elapsed = (as_of_date - start).days
    return bac * (elapsed / duration)


def compute_evm_summary(rows: list[EvmCostRow], as_of_date: date) -> EvmSummary:
    """Roll a schedule's cost-loaded activities up to scalar EVM metrics.

    Pure function (no DB / no I/O). PV is time-phased to ``as_of_date`` exactly
    as the 4D dashboard's S-curve does. EV is BAC * progress%. AC is the
    captured ``cost_actual``. The forecast block uses the CPI-based identities
    (EAC = BAC / CPI). All ratio / forecast fields are ``None`` when their
    denominator is zero so a caller never has to special-case divide-by-zero.
    """
    total_pv = 0.0
    total_ev = 0.0
    total_ac = 0.0
    total_bac = 0.0
    any_cost = False

    for row in rows:
        bac = _decimal_to_float(row.cost_planned)
        ac = _decimal_to_float(row.cost_actual)
        if row.cost_planned is not None or row.cost_actual is not None:
            any_cost = True
        progress = coerce_progress_value(row.progress_pct)
        pv = planned_value_for_dates(row.start_date, row.end_date, bac, as_of_date)
        ev = bac * (progress / 100.0) if bac else 0.0
        total_pv += pv
        total_ev += ev
        total_ac += ac
        total_bac += bac

    spi: float | None = (total_ev / total_pv) if (any_cost and total_pv > 0) else None
    cpi: float | None = (total_ev / total_ac) if (any_cost and total_ac > 0) else None

    # EAC via the CPI method: BAC / CPI. Undefined when CPI is unknown.
    eac: float | None = (total_bac / cpi) if (cpi is not None and cpi > 0) else None
    etc: float | None = (eac - total_ac) if eac is not None else None
    vac: float | None = (total_bac - eac) if eac is not None else None

    return EvmSummary(
        planned_value=round(total_pv, 4),
        earned_value=round(total_ev, 4),
        actual_cost=round(total_ac, 4),
        budget_at_completion=round(total_bac, 4),
        schedule_variance=round(total_ev - total_pv, 4),
        cost_variance=round(total_ev - total_ac, 4),
        spi=round(spi, 4) if spi is not None else None,
        cpi=round(cpi, 4) if cpi is not None else None,
        estimate_at_completion=round(eac, 4) if eac is not None else None,
        estimate_to_complete=round(etc, 4) if etc is not None else None,
        variance_at_completion=round(vac, 4) if vac is not None else None,
        has_cost_data=any_cost,
    )


__all__ = [
    "EvmCostRow",
    "EvmSummary",
    "coerce_progress_value",
    "compute_evm_summary",
    "planned_value_for_dates",
]

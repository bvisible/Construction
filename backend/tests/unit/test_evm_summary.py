"""Pure unit tests for the scalar EVM rollup (Section 6 - earned value).

These import only :mod:`app.modules.schedule.evm_math`, which is intentionally
free of ORM / DB imports, so the whole module runs without a PostgreSQL
cluster (and on Python 3.11 locally). They lock down the PMBOK identities:
PV/EV/AC, BAC, SV/CV, SPI/CPI and the CPI-method forecast (EAC/ETC/VAC),
plus the divide-by-zero -> None contract.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.modules.schedule.evm_math import (
    EvmCostRow,
    coerce_progress_value,
    compute_evm_summary,
    planned_value_for_dates,
)


def _row(
    start: str | None,
    end: str | None,
    planned: str | None,
    actual: str | None,
    progress: str | None,
) -> EvmCostRow:
    return EvmCostRow(
        start_date=start,
        end_date=end,
        cost_planned=Decimal(planned) if planned is not None else None,
        cost_actual=Decimal(actual) if actual is not None else None,
        progress_pct=progress,
    )


def test_spi_cpi_and_forecast_two_activities():
    """Two activities, data date past both ends so PV == BAC.

    A: 50%, PV=1000, AC=600  -> EV=500
    B: 100%, PV=2000, AC=1800 -> EV=2000
    Totals: PV=3000, EV=2500, AC=2400, BAC=3000.
    """
    rows = [
        _row("2026-01-01", "2026-02-01", "1000", "600", "50"),
        _row("2026-01-01", "2026-02-01", "2000", "1800", "100"),
    ]
    out = compute_evm_summary(rows, date(2026, 4, 1))

    assert out.has_cost_data is True
    assert out.planned_value == pytest.approx(3000.0)
    assert out.earned_value == pytest.approx(2500.0)
    assert out.actual_cost == pytest.approx(2400.0)
    assert out.budget_at_completion == pytest.approx(3000.0)
    assert out.schedule_variance == pytest.approx(-500.0)  # EV - PV
    assert out.cost_variance == pytest.approx(100.0)  # EV - AC
    assert out.spi == pytest.approx(2500.0 / 3000.0, rel=1e-3)
    assert out.cpi == pytest.approx(2500.0 / 2400.0, rel=1e-3)
    # EAC = BAC / CPI ; ETC = EAC - AC ; VAC = BAC - EAC.
    expected_eac = 3000.0 / (2500.0 / 2400.0)
    assert out.estimate_at_completion == pytest.approx(expected_eac, rel=1e-3)
    assert out.estimate_to_complete == pytest.approx(expected_eac - 2400.0, rel=1e-3)
    assert out.variance_at_completion == pytest.approx(3000.0 - expected_eac, rel=1e-3)


def test_pv_is_time_phased_to_data_date():
    """An in-progress activity contributes a prorated PV, not its full budget.

    10-day activity, BAC=1000, data date at day 4 -> PV = 1000 * 4/10 = 400.
    EV is BAC * progress% regardless of the data date: 30% -> 300.
    """
    rows = [_row("2026-01-01", "2026-01-11", "1000", "250", "30")]
    out = compute_evm_summary(rows, date(2026, 1, 5))  # 4 elapsed days

    assert out.planned_value == pytest.approx(400.0, rel=1e-3)
    assert out.earned_value == pytest.approx(300.0, rel=1e-3)
    assert out.budget_at_completion == pytest.approx(1000.0)
    # SV = 300 - 400 = -100 (behind schedule); CV = 300 - 250 = 50 (under cost).
    assert out.schedule_variance == pytest.approx(-100.0, rel=1e-3)
    assert out.cost_variance == pytest.approx(50.0, rel=1e-3)


def test_no_cost_data_yields_none_indices_and_forecast():
    """No cost columns at all -> has_cost_data False and all ratios None."""
    rows = [_row("2026-01-01", "2026-02-01", None, None, "40")]
    out = compute_evm_summary(rows, date(2026, 4, 1))

    assert out.has_cost_data is False
    assert out.planned_value == 0.0
    assert out.earned_value == 0.0
    assert out.actual_cost == 0.0
    assert out.budget_at_completion == 0.0
    assert out.spi is None
    assert out.cpi is None
    assert out.estimate_at_completion is None
    assert out.estimate_to_complete is None
    assert out.variance_at_completion is None


def test_zero_actual_cost_leaves_cpi_and_eac_none():
    """Cost-loaded plan but zero AC -> CPI undefined, so EAC/ETC/VAC are None.

    PV is present (SPI computable) but no actuals captured yet.
    """
    rows = [_row("2026-01-01", "2026-02-01", "1000", None, "50")]
    out = compute_evm_summary(rows, date(2026, 4, 1))

    assert out.has_cost_data is True
    assert out.budget_at_completion == pytest.approx(1000.0)
    assert out.earned_value == pytest.approx(500.0)
    assert out.actual_cost == 0.0
    assert out.spi == pytest.approx(500.0 / 1000.0, rel=1e-3)
    assert out.cpi is None  # EV / 0 is undefined
    assert out.estimate_at_completion is None
    assert out.estimate_to_complete is None
    assert out.variance_at_completion is None


def test_empty_rows_returns_zeroed_summary():
    out = compute_evm_summary([], date(2026, 4, 1))
    assert out.has_cost_data is False
    assert out.planned_value == 0.0
    assert out.budget_at_completion == 0.0
    assert out.spi is None
    assert out.cpi is None
    assert out.to_json()["estimate_at_completion"] is None


def test_progress_is_clamped_and_garbage_safe():
    assert coerce_progress_value("50") == 50.0
    assert coerce_progress_value("150") == 100.0  # clamp high
    assert coerce_progress_value("-10") == 0.0  # clamp low
    assert coerce_progress_value(None) == 0.0
    assert coerce_progress_value("not-a-number") == 0.0


def test_planned_value_for_dates_boundaries():
    bac = 1000.0
    # Before start -> 0.
    assert planned_value_for_dates("2026-01-10", "2026-01-20", bac, date(2026, 1, 1)) == 0.0
    # On/after end -> full BAC.
    assert planned_value_for_dates("2026-01-10", "2026-01-20", bac, date(2026, 1, 20)) == pytest.approx(bac)
    assert planned_value_for_dates("2026-01-10", "2026-01-20", bac, date(2026, 2, 1)) == pytest.approx(bac)
    # Unparseable dates or zero BAC -> 0 (defensive, never raises).
    assert planned_value_for_dates(None, "2026-01-20", bac, date(2026, 1, 15)) == 0.0
    assert planned_value_for_dates("2026-01-10", "2026-01-20", 0.0, date(2026, 1, 15)) == 0.0

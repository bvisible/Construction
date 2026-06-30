"""Unit tests for the assembly margin-cascade engine (margins.py).

Pure / standalone: no DB, no app fixtures. Proves the cascade math is exact
to the centime and that per-line overrides (disable / re-rate a margin)
behave as an estimator expects.
"""

from decimal import Decimal

import pytest

from app.modules.assemblies.margins import (
    SUBTOTAL_TOKEN,
    compute_margin_cascade,
    resolve_effective_margins,
)


# A realistic Protti-shaped default cascade: three cost-side margins that
# each sit on their own base, then R&B 7% on top of everything.
PROTTI_MARGINS = [
    {"key": "fg_admin", "label": "FG administratif", "kind": "percentage", "rate": "26.95", "base": ["labor"], "active": True},
    {"key": "ext", "label": "Marge externe", "kind": "percentage", "rate": "3", "base": ["material", "equipment"], "active": True},
    {"key": "sub", "label": "Marge sous-traitant", "kind": "percentage", "rate": "5", "base": ["subcontractor"], "active": True},
    {"key": "rb", "label": "R&B (Risque & Bénéfice)", "kind": "percentage", "rate": "7", "base": [SUBTOTAL_TOKEN], "active": True},
]

COST = {
    "labor": Decimal("100"),
    "material": Decimal("50"),
    "equipment": Decimal("20"),
    "subcontractor": Decimal("30"),
}


def test_full_cascade_to_the_centime():
    res = compute_margin_cascade(COST, PROTTI_MARGINS, decimals=2, currency="CHF")
    assert res["direct_total"] == "200.00"
    amounts = {s["key"]: s["amount"] for s in res["steps"]}
    assert amounts["fg_admin"] == "26.95"          # 26.95% × 100
    assert amounts["ext"] == "2.10"                 # 3% × (50+20)
    assert amounts["sub"] == "1.50"                 # 5% × 30
    # R&B 7% on (200 + 26.95 + 2.10 + 1.50 = 230.55) = 16.1385 -> 16.14
    assert amounts["rb"] == "16.14"
    assert res["margin_total"] == "46.69"
    assert res["grand_total"] == "246.69"


def test_disable_one_margin_per_line():
    overrides = {"sub": {"active": False}}
    eff = resolve_effective_margins(PROTTI_MARGINS, overrides)
    res = compute_margin_cascade(COST, eff, decimals=2)
    amounts = {s["key"]: s["amount"] for s in res["steps"]}
    assert amounts["sub"] == "0.00"
    # R&B now on (200 + 26.95 + 2.10 = 229.05) = 16.0335 -> 16.03
    assert amounts["rb"] == "16.03"
    assert res["grand_total"] == "245.08"
    # The disabled step is still reported (so the UI can show it greyed out).
    assert next(s for s in res["steps"] if s["key"] == "sub")["active"] is False


def test_re_rate_one_margin_per_line():
    overrides = {"rb": {"rate": "5"}}
    eff = resolve_effective_margins(PROTTI_MARGINS, overrides)
    res = compute_margin_cascade(COST, eff, decimals=2)
    amounts = {s["key"]: s["amount"] for s in res["steps"]}
    # R&B 5% on 230.55 = 11.5275 -> 11.53
    assert amounts["rb"] == "11.53"
    assert res["grand_total"] == "242.08"


def test_fixed_margin_kind():
    margins = [{"key": "lump", "label": "Forfait", "kind": "fixed", "amount": "12.50", "base": [], "active": True}]
    res = compute_margin_cascade({"labor": Decimal("100")}, margins)
    assert res["margin_total"] == "12.50"
    assert res["grand_total"] == "112.50"


def test_overrides_do_not_mutate_defaults():
    before = PROTTI_MARGINS[2]["active"]
    resolve_effective_margins(PROTTI_MARGINS, {"sub": {"active": False}})
    assert PROTTI_MARGINS[2]["active"] == before is True


def test_empty_margins_is_just_direct_cost():
    res = compute_margin_cascade(COST, [], decimals=2)
    assert res["margin_total"] == "0.00"
    assert res["grand_total"] == "200.00"


def test_non_finite_and_garbage_are_neutralised():
    # A poisoned rate / total must not produce NaN or Infinity strings.
    margins = [{"key": "x", "kind": "percentage", "rate": "not-a-number", "base": ["labor"], "active": True}]
    res = compute_margin_cascade({"labor": "oops"}, margins)
    assert res["direct_total"] == "0.00"
    assert res["grand_total"] == "0.00"


def test_unknown_base_token_contributes_zero():
    margins = [{"key": "x", "kind": "percentage", "rate": "10", "base": ["does_not_exist"], "active": True}]
    res = compute_margin_cascade(COST, margins)
    assert next(s for s in res["steps"] if s["key"] == "x")["amount"] == "0.00"

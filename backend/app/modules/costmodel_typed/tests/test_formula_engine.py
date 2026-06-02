"""Tests for the costmodel_typed formula engine.

The 24 cases below cover the shapes we observed in the Phase 1 parser corpus
(see ``~/GitHub/Protti/06-Generateurs/parser_devis_protti/output/protti_corpus.json``)
plus a guard set to make sure the evaluator stays narrow.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.costmodel_typed.formula_engine import FormulaError, evaluate


# ── Happy-path arithmetic ────────────────────────────────────────────────────


def test_constant():
    assert evaluate("42") == Decimal("42")


def test_negative_constant():
    assert evaluate("-3.5") == Decimal("-3.5")


def test_simple_add():
    assert evaluate("1 + 2") == Decimal("3")


def test_simple_mul():
    assert evaluate("2 * 3") == Decimal("6")


def test_mixed_priority():
    assert evaluate("2 + 3 * 4") == Decimal("14")


def test_parens_overrides():
    assert evaluate("(2 + 3) * 4") == Decimal("20")


def test_division_exact():
    assert evaluate("10 / 4") == Decimal("2.5")


def test_floor_div():
    assert evaluate("10 // 3") == Decimal("3")


def test_modulo():
    assert evaluate("10 % 3") == Decimal("1")


def test_power_int():
    assert evaluate("2 ** 8") == Decimal("256")


def test_decimal_precision():
    # 0.1 + 0.2 stays exact thanks to the Decimal path.
    assert evaluate("0.1 + 0.2") == Decimal("0.3")


# ── Named variables — Protti dimension patterns ──────────────────────────────


def test_single_variable():
    assert evaluate("L", {"L": Decimal("1.75")}) == Decimal("1.75")


def test_lh_product():
    # Surface = L * H
    assert evaluate("L * H", {"L": Decimal("1.75"), "H": Decimal("1.6")}) == Decimal(
        "2.8"
    )


def test_volume_with_thickness():
    # Volume = (L + I + I) * (W + I + I) * (E + 0.3)  — Protti fosse pattern
    res = evaluate(
        "(L + I + I) * (W + I + I) * (E + 0.3)",
        {"L": Decimal("1.75"), "W": Decimal("1.75"), "I": Decimal("0.3"), "E": Decimal("0.2")},
    )
    # 2.35 * 2.35 * 0.5 = 2.76125
    assert res == Decimal("2.76125")


def test_perimeter_pattern():
    # ((L + I) + (W + I)) * 2 * 2  — Protti joint d'étanchéité pattern
    res = evaluate(
        "((L + I) + (W + I)) * 2 * 2",
        {"L": Decimal("1.75"), "W": Decimal("1.75"), "I": Decimal("0.3")},
    )
    # (2.05 + 2.05) * 2 * 2 = 16.4
    assert res == Decimal("16.4")


def test_armature_weight():
    # Poids armature: ((surface * 0.2) + (perimeter * I * 2)) * 100
    res = evaluate(
        "((L * W * 0.2) + ((L + W) * I * 2)) * 100",
        {"L": Decimal("1.75"), "W": Decimal("1.75"), "I": Decimal("0.3")},
    )
    # ((1.75*1.75*0.2) + ((1.75+1.75)*0.3*2)) * 100 = (0.6125 + 2.1) * 100 = 271.25
    assert res == Decimal("271.25")


def test_leading_equals_stripped():
    # Spreadsheet pass-through — caller does not need to strip "=".
    assert evaluate("=2 + 3") == Decimal("5")


def test_extra_whitespace():
    assert evaluate("   2   +   3   ") == Decimal("5")


# ── Guard rails — disallowed inputs ──────────────────────────────────────────


def test_unknown_variable():
    with pytest.raises(FormulaError, match="Unknown variable"):
        evaluate("L + Z", {"L": Decimal("1")})


def test_function_call_rejected():
    with pytest.raises(FormulaError, match="Disallowed AST node"):
        evaluate("abs(-3)")


def test_attribute_access_rejected():
    with pytest.raises(FormulaError, match="Disallowed AST node"):
        evaluate("(1).real")


def test_boolean_rejected():
    with pytest.raises(FormulaError, match="Boolean"):
        evaluate("True")


def test_division_by_zero():
    with pytest.raises(FormulaError, match="Division by zero"):
        evaluate("1 / 0")


def test_empty_formula_rejected():
    with pytest.raises(FormulaError, match="Empty"):
        evaluate("")


def test_syntax_error():
    with pytest.raises(FormulaError, match="Syntax error"):
        evaluate("2 + ")

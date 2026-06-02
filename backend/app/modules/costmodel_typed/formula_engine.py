"""Safe arithmetic-formula evaluator used by the recompute pipeline.

The evaluator parses a textual quantity formula like
``(L + 0.6) * (H + 0.6) * (E + 0.3)`` and resolves it against a dictionary of
named dimensions like ``{"L": 1.75, "H": 1.6, "E": 0.2}``. It is intentionally
narrow: only arithmetic on numbers and bound names is allowed. No function
calls, attribute lookups, comprehensions, comparisons, or imports — that keeps
arbitrary remote-controlled inputs from turning into code execution.

Supported nodes:
    BinOp        + - * / // % **
    UnaryOp      + - (sign)
    Name         resolved from the variables dict
    Constant     int / float / Decimal-convertible string

Everything else raises ``FormulaError``.

Decimal arithmetic is used end-to-end so we keep the same precision pattern
as the rest of the cost-domain code (Decimal-as-string at the storage layer).
"""

from __future__ import annotations

import ast
from decimal import Decimal, InvalidOperation


class FormulaError(ValueError):
    """Raised when a formula is malformed or refers to unknown names / nodes."""


# ── Allowed AST node classes ─────────────────────────────────────────────────
_ALLOWED_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.Num,  # py < 3.8 — harmless on 3.12 but kept for safety
    ast.UAdd,
    ast.USub,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
)


def _to_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):  # bool is a subclass of int — reject explicitly
        raise FormulaError("Boolean values are not allowed in formulas")
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            return Decimal(value)
        except (InvalidOperation, ValueError) as exc:
            raise FormulaError(f"Cannot convert {value!r} to Decimal") from exc
    raise FormulaError(f"Unsupported value type for formula: {type(value).__name__}")


def _walk(node: ast.AST, variables: dict[str, Decimal]) -> Decimal:
    if not isinstance(node, _ALLOWED_NODES):
        raise FormulaError(
            f"Disallowed AST node in formula: {type(node).__name__}"
        )

    if isinstance(node, ast.Expression):
        return _walk(node.body, variables)

    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            raise FormulaError("Boolean constants are not allowed in formulas")
        if isinstance(node.value, (int, float)):
            return Decimal(str(node.value))
        if isinstance(node.value, str):
            return _to_decimal(node.value)
        raise FormulaError(
            f"Unsupported constant type: {type(node.value).__name__}"
        )

    if isinstance(node, ast.Name):
        if node.id not in variables:
            raise FormulaError(f"Unknown variable in formula: {node.id!r}")
        return _to_decimal(variables[node.id])

    if isinstance(node, ast.UnaryOp):
        operand = _walk(node.operand, variables)
        if isinstance(node.op, ast.UAdd):
            return +operand
        if isinstance(node.op, ast.USub):
            return -operand
        raise FormulaError(f"Unsupported unary operator: {type(node.op).__name__}")

    if isinstance(node, ast.BinOp):
        left = _walk(node.left, variables)
        right = _walk(node.right, variables)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                raise FormulaError("Division by zero in formula")
            return left / right
        if isinstance(node.op, ast.FloorDiv):
            if right == 0:
                raise FormulaError("Division by zero in formula")
            return left // right
        if isinstance(node.op, ast.Mod):
            if right == 0:
                raise FormulaError("Modulo by zero in formula")
            return left % right
        if isinstance(node.op, ast.Pow):
            # Limit the exponent so a hostile formula cannot DoS via 10**1e9
            if right > Decimal(100) or right < Decimal(-100):
                raise FormulaError("Exponent out of range in formula")
            return Decimal(left) ** Decimal(right)
        raise FormulaError(f"Unsupported binary operator: {type(node.op).__name__}")

    raise FormulaError(f"Unsupported AST node: {type(node).__name__}")


def evaluate(formula: str, variables: dict[str, object] | None = None) -> Decimal:
    """Evaluate ``formula`` with the given ``variables`` map. Returns Decimal.

    Raises ``FormulaError`` for empty strings, syntax errors, disallowed nodes
    or unknown variables.
    """
    if formula is None or not str(formula).strip():
        raise FormulaError("Empty formula")
    # Strip an optional leading "=" so callers can pass the spreadsheet-style
    # formula as-is.
    text = str(formula).strip().lstrip("=").strip()
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise FormulaError(f"Syntax error in formula: {exc.msg}") from exc

    bound: dict[str, Decimal] = {
        k: _to_decimal(v) for k, v in (variables or {}).items()
    }
    return _walk(tree, bound)

"""Pure margin-cascade computer for assemblies.

Self-contained (standard library only) so it can be unit-tested standalone
and never blocks the module import graph. It layers an ordered set of
margins on top of an assembly's typed component cost.

The design intent (see the Protti estimating model): an estimator defines a
set of margins ONCE at the offer/project level (the "global default"), every
assembly inherits them, and any single assembly can disable or re-rate a
margin for that line ("per-line override"). Margins are NOT cost - the cost
stays in the components; these sit on top of it.

Money is :class:`decimal.Decimal` throughout, never ``float``. Each step is
quantized to ``decimals`` places with ``ROUND_HALF_UP`` immediately, and a
margin whose base is the running subtotal consumes the already-rounded
amount (round-per-step, feed-forward) - same contract as the methodology
cascade engine.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

__all__ = [
    "SUBTOTAL_TOKEN",
    "component_totals_by_type",
    "extract_margin_defaults",
    "resolve_effective_margins",
    "compute_margin_cascade",
]

# A margin whose ``base`` lists this token applies to the running subtotal:
# direct cost plus every active margin computed before it. This is how a
# Risque & Bénéfice (R&B) markup sits on top of everything else.
SUBTOTAL_TOKEN = "__subtotal__"

_VALID_KINDS = frozenset({"percentage", "fixed"})


def _dec(value: Any, default: str = "0") -> Decimal:
    """Coerce any value to a finite ``Decimal``, falling back to ``default``.

    Accepts Decimal / int / numeric str. A non-finite or unparseable value
    yields ``Decimal(default)`` so the cascade can never produce ``NaN`` /
    ``Infinity`` that would later serialise as ``null``.
    """
    if isinstance(value, Decimal):
        return value if value.is_finite() else Decimal(default)
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(default)
    return d if d.is_finite() else Decimal(default)


def _round(value: Decimal, decimals: int) -> Decimal:
    """Quantize ``value`` with ROUND_HALF_UP to ``decimals`` places."""
    quant = Decimal(1) if decimals <= 0 else Decimal(1).scaleb(-decimals)
    return value.quantize(quant, rounding=ROUND_HALF_UP)


def component_totals_by_type(components: Sequence[Any]) -> dict[str, Decimal]:
    """Sum component ``total`` money grouped by ``resource_type``.

    ``components`` is any sequence of objects exposing ``.resource_type`` and
    ``.total`` (the assembly ORM ``Component``). Untyped components fall into
    an ``"untyped"`` bucket so their money still counts toward the direct
    total even though no margin can target them by type.
    """
    out: dict[str, Decimal] = {}
    for comp in components:
        rtype = getattr(comp, "resource_type", None) or "untyped"
        rtype = str(rtype)
        out[rtype] = out.get(rtype, Decimal("0")) + _dec(getattr(comp, "total", "0"))
    return out


def extract_margin_defaults(raw: Any) -> list[dict[str, Any]]:
    """Normalise a stored margin-defaults blob to a list of margin dicts.

    Accepts either a bare list of margin dicts, or a ``{"margins": [...]}``
    wrapper (so the project metadata can carry sibling keys like currency or
    decimals later without breaking the contract). Anything else yields
    ``[]``. The returned dicts are shallow copies, never the stored objects.
    """
    if isinstance(raw, Mapping):
        raw = raw.get("margins")
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        return [dict(m) for m in raw if isinstance(m, Mapping)]
    return []


def resolve_effective_margins(
    defaults: Any,
    overrides: Any,
) -> list[dict[str, Any]]:
    """Apply per-assembly ``overrides`` on top of the global ``defaults``.

    Args:
        defaults: The project-level margin list. Each entry is a dict with
            ``key`` and the margin definition. A non-list yields ``[]``.
        overrides: A dict ``{key: {"active"?: bool, "rate"?: number,
            "amount"?: number}}``. Only the listed fields are overridden; the
            rest of the margin definition is inherited unchanged.

    Returns:
        A new ordered list of margin dicts with overrides merged in. The
        input dicts are never mutated.
    """
    if not isinstance(defaults, Sequence) or isinstance(defaults, (str, bytes)):
        return []
    ov: Mapping[str, Any] = overrides if isinstance(overrides, Mapping) else {}
    out: list[dict[str, Any]] = []
    for margin in defaults:
        if not isinstance(margin, Mapping):
            continue
        merged = dict(margin)
        key = str(merged.get("key", ""))
        patch = ov.get(key)
        if isinstance(patch, Mapping):
            if "active" in patch:
                merged["active"] = bool(patch["active"])
            if "rate" in patch:
                merged["rate"] = patch["rate"]
            if "amount" in patch:
                merged["amount"] = patch["amount"]
        out.append(merged)
    return out


def compute_margin_cascade(
    component_totals: Mapping[str, Any],
    margins: Sequence[Any],
    *,
    decimals: int = 2,
    currency: str = "",
) -> dict[str, Any]:
    """Layer ordered ``margins`` on top of per-type component totals.

    Args:
        component_totals: Money summed per ``resource_type`` (the assembly's
            direct cost split by type), e.g. ``{"labor": Decimal("22.21"),
            "material": Decimal("6.00")}``.
        margins: Ordered margin dicts. Each: ``key``, ``label``, ``kind``
            (``"percentage"`` | ``"fixed"``), ``rate`` (percent, for
            percentage), ``amount`` (for fixed), ``base`` (a resource-type
            token, a list of them, or :data:`SUBTOTAL_TOKEN`), ``active``.
        decimals: Rounding precision for every monetary value.
        currency: Informational ISO code echoed back in the result.

    Returns:
        A dict with ``currency``, ``direct_total``, ``steps`` (one per
        margin, each carrying ``base_amount``, ``amount``, ``active``),
        ``margin_total`` and ``grand_total`` - all money as exact decimal
        strings so the wire payload stays locale-neutral and lossless.
    """
    totals: dict[str, Decimal] = {
        str(k): _dec(v) for k, v in (component_totals or {}).items()
    }
    direct_total = _round(sum(totals.values(), Decimal("0")), decimals)

    steps: list[dict[str, Any]] = []
    margin_total = Decimal("0")
    # running = direct cost + every active margin computed so far. A margin
    # targeting SUBTOTAL_TOKEN applies to this value.
    running = direct_total
    step_amounts: dict[str, Decimal] = {}

    for margin in margins or []:
        if not isinstance(margin, Mapping):
            continue
        key = str(margin.get("key", ""))
        label = str(margin.get("label", key))
        kind = str(margin.get("kind", "percentage"))
        if kind not in _VALID_KINDS:
            kind = "percentage"
        active = bool(margin.get("active", True))
        rate = _dec(margin.get("rate", "0"))

        base_tokens = margin.get("base", [])
        if isinstance(base_tokens, str):
            base_tokens = [base_tokens]
        elif not isinstance(base_tokens, Sequence):
            base_tokens = []

        # Resolve the base this margin applies to: leaf resource types, an
        # earlier margin's amount (by key), or the running subtotal.
        base_amount = Decimal("0")
        for raw_token in base_tokens:
            token = str(raw_token)
            if token == SUBTOTAL_TOKEN:
                base_amount += running
            elif token in totals:
                base_amount += totals[token]
            elif token in step_amounts:
                base_amount += step_amounts[token]
            # An unknown token contributes 0 (it just shows as a 0 base).
        base_amount = _round(base_amount, decimals)

        if not active:
            amount = _round(Decimal("0"), decimals)
        elif kind == "fixed":
            amount = _round(_dec(margin.get("amount", "0")), decimals)
        else:  # percentage
            amount = _round(base_amount * rate / Decimal("100"), decimals)

        step_amounts[key] = amount
        if active:
            margin_total += amount
            running = _round(running + amount, decimals)

        steps.append(
            {
                "key": key,
                "label": label,
                "kind": kind,
                "rate": str(rate),
                "base": [str(t) for t in base_tokens],
                "base_amount": str(base_amount),
                "amount": str(amount),
                "active": active,
            }
        )

    margin_total = _round(margin_total, decimals)
    grand_total = _round(direct_total + margin_total, decimals)

    return {
        "currency": currency,
        "direct_total": str(direct_total),
        "steps": steps,
        "margin_total": str(margin_total),
        "grand_total": str(grand_total),
    }

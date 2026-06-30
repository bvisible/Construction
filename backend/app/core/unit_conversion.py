"""Server-side metric -> imperial unit conversion for human-facing reports.

This is the backend twin of the frontend ``unitConversion.ts``
(``frontend/src/shared/lib/unitConversion.ts``); the conversion factors and
display labels are kept byte-identical so a PDF rendered server-side and a
quantity rendered in the browser agree to the last decimal.

Scope (GitHub #270): the whole platform stores quantities metric-canonical
(``m`` / ``m2`` / ``m3`` / ``kg`` ...). Only *human-facing* output (a printed
PDF, a rendered cell) is ever converted into the user's measurement system.
Data-interchange exports (CSV, Excel, GAEB) stay canonical metric and must
never call this module.

What is and is not converted:

* Physical quantities and their unit labels ARE converted when the caller
  asks for ``system="imperial"`` (see :func:`convert`).
* Line / project totals, markups and VAT are NEVER recomputed - a total is an
  amount in the project currency, invariant to the unit a quantity is shown in.
* A per-unit RATE is the one nuance: it is money per one metric unit, so when
  the paired quantity is displayed converted (2.31 m -> 7.58 ft) the rate must
  be restated against the same displayed unit (50 / m -> 15.24 / ft) or the
  printed line no longer reconciles. :func:`display_rate` does exactly that
  reciprocal restatement; it changes only the per-unit basis, and the total it
  pairs with is unchanged. Callers that print a rate next to a converted
  quantity MUST use it.

Units with no imperial mapping (``pcs``, ``%``, ``lump``, ``hr`` ...) pass
through unchanged in both systems, which is the correct behaviour for
countable / lump / dimensionless items. ``system="metric"`` (the default)
returns the value unchanged and only tidies the unit label
("m2" -> "m²").

Precision note: even though a quantity is a measurement (float-typed in the
API) and not money, the multiply here is done with :class:`decimal.Decimal`
so a value that arrives as a ``Decimal`` (the BOQ position quantity is a
4-dp Decimal) keeps its precision instead of being round-tripped through a
binary float.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Final, NamedTuple

__all__ = [
    "ConversionResult",
    "convert",
    "conversion_factor",
    "display_rate",
    "display_unit_for",
]


class _Entry(NamedTuple):
    """A metric -> imperial mapping: scale factor, canonical + display label."""

    factor: str  # kept as a string so Decimal(factor) is exact
    unit: str  # canonical imperial unit code ("ft2")
    display: str  # human-facing label ("sq ft" / "ft²")


# Metric -> imperial factors, mirroring METRIC_TO_IMPERIAL in
# unitConversion.ts. Factors are stored as strings so they convert to an
# exact Decimal (Decimal(0.3048) would carry binary-float noise).
_METRIC_TO_IMPERIAL: Final[dict[str, _Entry]] = {
    "m": _Entry("3.2808399", "ft", "ft"),
    "m2": _Entry("10.7639", "ft2", "sq ft"),
    "m3": _Entry("35.3147", "ft3", "cu ft"),
    # Superscript variants of the area / volume codes used on the takeoff
    # canvas + ledger ("m²" / "m³"). Mapped to superscript imperial
    # labels so the converted display stays in the same visual style as the
    # metric source rather than switching to the "sq ft" / "cu ft" spelling.
    "m²": _Entry("10.7639", "ft2", "ft²"),
    "m³": _Entry("35.3147", "ft3", "ft³"),
    "kg": _Entry("2.20462", "lb", "lb"),
    "km": _Entry("0.621371", "mi", "mi"),
    "cm": _Entry("0.393701", "in", "in"),
    "mm": _Entry("0.0393701", "in", "in"),
    "t": _Entry("1.10231", "ton", "ton"),
    "lm": _Entry("3.28084", "lft", "l.ft"),
    # Extended BoQ area / land / liquid coverage, mirroring the additions in
    # unitConversion.ts. Small areas relabel to square inches, dm2 to square
    # feet, hectares to acres, litres to US gallons. Superscript variants are
    # mapped like the m2/m3 pair above.
    "mm2": _Entry("0.0015500031", "in2", "sq in"),
    "cm2": _Entry("0.15500031", "in2", "sq in"),
    "dm2": _Entry("0.107639104", "ft2", "sq ft"),
    "mm²": _Entry("0.0015500031", "in2", "in²"),
    "cm²": _Entry("0.15500031", "in2", "in²"),
    "dm²": _Entry("0.107639104", "ft2", "ft²"),
    "ha": _Entry("2.4710538", "ac", "ac"),
    "l": _Entry("0.264172052", "gal", "gal"),
}


# Display-friendly labels for common metric units, mirroring METRIC_DISPLAY
# in unitConversion.ts. Used in metric mode so "m2" renders as "m²"
# without changing the value.
_METRIC_DISPLAY: Final[dict[str, str]] = {
    "m": "m",
    "m2": "m²",
    "m3": "m³",
    # Already-superscript inputs map to themselves so they are recognised as
    # metric (the takeoff layer stores units as "m²" / "m³").
    "m²": "m²",
    "m³": "m³",
    "kg": "kg",
    "km": "km",
    "cm": "cm",
    "mm": "mm",
    "t": "t",
    "lm": "l.m",
    "mm2": "mm²",
    "cm2": "cm²",
    "dm2": "dm²",
    "mm²": "mm²",
    "cm²": "cm²",
    "dm²": "dm²",
    "ha": "ha",
    "l": "l",
}


class ConversionResult(NamedTuple):
    """A converted quantity: numeric value + the unit label to show beside it."""

    value: Decimal
    display_unit: str


def _to_decimal(value: Decimal | float | int | str) -> Decimal:
    """Coerce a quantity to a finite Decimal (non-finite / junk -> 0)."""
    if isinstance(value, Decimal):
        return value if value.is_finite() else Decimal(0)
    try:
        d = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return Decimal(0)
    return d if d.is_finite() else Decimal(0)


def _normalise_key(metric_unit: str | None) -> str:
    """Return the lookup key for a metric unit (trimmed, original case)."""
    return (metric_unit or "").strip()


def display_unit_for(metric_unit: str | None, system: str = "metric") -> str:
    """Return the unit label a metric unit resolves to in ``system``.

    No value is needed - used where only a unit column / header / suffix is
    rendered. ``metric`` tidies the label ("m2" -> "m²"); ``imperial``
    relabels ("m2" -> "sq ft"). Unknown / unmapped units (``pcs``, ``%`` ...)
    return the trimmed input unchanged.
    """
    key = _normalise_key(metric_unit)
    if system == "imperial":
        entry = _METRIC_TO_IMPERIAL.get(key) or _METRIC_TO_IMPERIAL.get(key.lower())
        if entry is not None:
            return entry.display
        # Fall through to the metric label so an already-imperial or unmapped
        # unit still renders tidily rather than empty.
    return _METRIC_DISPLAY.get(key) or _METRIC_DISPLAY.get(key.lower()) or key


def convert(
    value: Decimal | float | int | str,
    metric_unit: str | None,
    system: str = "metric",
) -> ConversionResult:
    """Convert a metric-canonical quantity into the target measurement system.

    Args:
        value: The metric-canonical quantity (Decimal preferred; float / int /
            str accepted and coerced).
        metric_unit: The canonical metric unit the value is expressed in
            (``m`` / ``m2`` / ``kg`` ...). ``None`` / empty is treated as an
            unmapped, dimensionless unit.
        system: ``"metric"`` (default) returns the value unchanged with a tidy
            label; ``"imperial"`` scales the value and relabels the unit.

    Returns:
        A :class:`ConversionResult` (``value`` as Decimal, ``display_unit`` as
        the label to render). Units with no imperial mapping pass through with
        their value unchanged in both systems.

    Money must never be passed to this function - it converts measurements,
    not prices.
    """
    amount = _to_decimal(value)
    key = _normalise_key(metric_unit)

    if system == "imperial":
        entry = _METRIC_TO_IMPERIAL.get(key) or _METRIC_TO_IMPERIAL.get(key.lower())
        if entry is not None:
            return ConversionResult(amount * Decimal(entry.factor), entry.display)

    # Metric (or unmapped under imperial): value passes through unchanged,
    # only the label is tidied.
    return ConversionResult(amount, display_unit_for(key, system))


def conversion_factor(metric_unit: str | None, system: str = "metric") -> Decimal:
    """Return the scalar a metric unit scales by in ``system``.

    The Decimal ``f`` such that ``display_value = metric_value * f``. Returns
    ``Decimal(1)`` for metric and for any unit with no imperial mapping, so
    callers can multiply / divide unconditionally. This is the single source of
    the reciprocal used to restate a per-unit rate against a converted quantity.
    """
    if system == "imperial":
        key = _normalise_key(metric_unit)
        entry = _METRIC_TO_IMPERIAL.get(key) or _METRIC_TO_IMPERIAL.get(key.lower())
        if entry is not None:
            return Decimal(entry.factor)
    return Decimal(1)


def display_rate(
    rate: Decimal | float | int | str,
    metric_unit: str | None,
    system: str = "metric",
) -> Decimal:
    """Restate a per-unit rate so it pairs with a quantity shown in ``system``.

    A rate is money per ONE metric unit (50 / m). When the paired quantity is
    displayed converted (2.31 m -> 7.58 ft) the rate must be shown against the
    SAME displayed unit or the printed line stops reconciling: 7.58 ft is
    priced at ``50 / 3.2808399 = 15.24 / ft`` so ``qty * rate`` still equals the
    (invariant) line total. The line total is never recomputed from this value -
    it stays canonical; only the displayed per-unit basis is restated. Units
    with no imperial mapping return the rate unchanged.

    This is the one place the module deliberately touches a money figure, and
    it changes only the per-unit *basis*, never a total.
    """
    factor = conversion_factor(metric_unit, system)
    amount = _to_decimal(rate)
    if factor == 0:
        return amount
    return amount / factor

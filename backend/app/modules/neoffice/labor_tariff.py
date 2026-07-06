"""Composed labour hourly tariff for Protti — the estimating "moteur".

Turns a CN base wage into the real hourly cost by composing:

    coût horaire = salaire de base
                 + charges sociales (× charges_pct)
                 + repas + indemnité de chantier (par jour ÷ heures productives)
                 + déplacement dépôt → chantier (distance-based, par jour ÷ heures)

The déplacement is distance-dependent (Sottens → chantier) and follows the CN/CCT
split, so two tariffs come out: one for the driver (conducteur, paid all travel)
and one for the passengers (paid the excess beyond the offered time). Feed it the
`distance.depot_to_site()` result to include travel; omit it for the depot-only rate.

Every parameter is explicit so Protti can calibrate (their real charges %, meal
policy, site allowance, productive hours).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


# Documented defaults (strings) — the starting point before Protti calibrates.
DEFAULTS: dict[str, str] = {
    "charges_pct": "0.42",
    "repas_jour": "23.00",
    "indemnite_jour": "0.00",
    "heures_jour": "8.4",
}

# Keys stored under user.metadata_ for the per-instance calibration.
PARAMS_META_KEY = "neoffice_labor_tariff_params"


class TariffParams:
    """Composition parameters — defaults are documented, calibratable starting points."""

    def __init__(
        self,
        charges_pct: str = "0.42",       # charges sociales employeur + suppléments (13e, vacances, fériés)
        repas_jour: str = "23.00",       # dîner 17 + petit-déjeuner 6 (CHF/jour)
        indemnite_jour: str = "0.00",    # indemnité de chantier OFAS (CHF/jour) — à renseigner
        heures_jour: str = "8.4",        # heures productives / jour
    ) -> None:
        self.charges_pct = Decimal(charges_pct)
        self.repas_jour = Decimal(repas_jour)
        self.indemnite_jour = Decimal(indemnite_jour)
        self.heures_jour = Decimal(heures_jour)


def _q(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), ROUND_HALF_UP)


def compose(base_hourly: str | float, params: TariffParams | None = None, travel: dict | None = None) -> dict:
    """Compose the hourly tariff. Returns the breakdown + driver/passenger totals.

    Args:
        base_hourly: CN base hourly wage (CHF).
        params: composition parameters (defaults if None).
        travel: result of ``distance.depot_to_site()`` (or None for depot-only).
    """
    p = params or TariffParams()
    base = Decimal(str(base_hourly))

    charges = _q(base * p.charges_pct)
    repas_indemnite_h = _q((p.repas_jour + p.indemnite_jour) / p.heures_jour)
    fixed = base + charges + repas_indemnite_h  # sans déplacement

    def travel_per_hour(billable_min: float) -> Decimal:
        cost_day = Decimal(str(billable_min)) / Decimal("60") * base
        return _q(cost_day / p.heures_jour)

    result = {
        "salaire_base_horaire_chf": str(base),
        "charges_pct": str(p.charges_pct),
        "charges_chf": str(charges),
        "repas_indemnite_horaire_chf": str(repas_indemnite_h),
        "cout_horaire_sans_deplacement_chf": str(_q(fixed)),
    }
    if travel and "error" not in travel:
        dep_driver = travel_per_hour(travel["driver_billable_min"])
        dep_passenger = travel_per_hour(travel["passenger_billable_min"])
        result.update({
            # The déplacement is billed on TIME (minutes), not distance — the km
            # is shown for context only. The CN/CCT rule works on minutes.
            "distance_km": travel["distance_km"],
            "one_way_min": travel["one_way_min"],
            "round_trip_min": travel["round_trip_min"],
            "offered_min": travel["offered_min"],
            "driver_billable_min": travel["driver_billable_min"],
            "passenger_billable_min": travel["passenger_billable_min"],
            "deplacement_horaire_conducteur_chf": str(dep_driver),
            "deplacement_horaire_passager_chf": str(dep_passenger),
            "cout_horaire_conducteur_chf": str(_q(fixed + dep_driver)),
            "cout_horaire_passager_chf": str(_q(fixed + dep_passenger)),
        })
    else:
        result["cout_horaire_conducteur_chf"] = str(_q(fixed))
        result["cout_horaire_passager_chf"] = str(_q(fixed))
    return result

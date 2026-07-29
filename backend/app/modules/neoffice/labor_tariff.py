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
#
# Everything the estimator asked to be able to change lives here (client
# feedback 2026-07-20): the average gross wage itself, the depot and office
# overhead carried per productive hour, and the risk & profit margins applied
# per resource family. Money defaults that we cannot know are 0 rather than a
# plausible-looking number — a wrong figure that reads like a real one is worse
# than an obvious blank.
DEFAULTS: dict[str, str] = {
    # Labour build-up
    "salaire_base_horaire": "34.00",  # CN class Q Vaud gros œuvre — overridable
    "charges_pct": "0.42",
    "repas_jour": "23.00",
    "indemnite_jour": "0.00",
    "heures_jour": "8.4",
    # Company overhead recovered on every productive hour (CHF/h)
    "charges_depot_h": "0.00",
    "charges_bureau_h": "0.00",
    # Risk & profit, per resource family (fraction, 0.10 = 10 %)
    "marge_mo_pct": "0.00",
    "marge_materiaux_pct": "0.00",
    "marge_machines_pct": "0.00",
    "marge_outillage_pct": "0.00",
    "marge_tiers_pct": "0.00",
    # Selling-price rounding step (CHF). 0 disables rounding.
    "arrondi_chf": "0.50",
}

# Keys stored under user.metadata_ for the per-instance calibration.
PARAMS_META_KEY = "neoffice_labor_tariff_params"

#: Resource families the margin cascade knows about, mapped to their parameter.
#: Keys match the resource ``type`` used across the BOQ / assemblies.
MARGIN_KEY_BY_FAMILY: dict[str, str] = {
    "labor": "marge_mo_pct",
    "material": "marge_materiaux_pct",
    "equipment": "marge_machines_pct",
    "tooling": "marge_outillage_pct",
    "subcontractor": "marge_tiers_pct",
}


class TariffParams:
    """Composition parameters — defaults are documented, calibratable starting points."""

    def __init__(
        self,
        charges_pct: str = "0.42",       # charges sociales employeur + suppléments (13e, vacances, fériés)
        repas_jour: str = "23.00",       # dîner 17 + petit-déjeuner 6 (CHF/jour)
        indemnite_jour: str = "0.00",    # indemnité de chantier OFAS (CHF/jour) — à renseigner
        heures_jour: str = "8.4",        # heures productives / jour
        salaire_base_horaire: str = "34.00",  # salaire moyen brut (CHF/h)
        charges_depot_h: str = "0.00",   # charges dépôt réparties (CHF par heure productive)
        charges_bureau_h: str = "0.00",  # charges bureau réparties (CHF par heure productive)
        marge_mo_pct: str = "0.00",
        marge_materiaux_pct: str = "0.00",
        marge_machines_pct: str = "0.00",
        marge_outillage_pct: str = "0.00",
        marge_tiers_pct: str = "0.00",
        arrondi_chf: str = "0.50",
    ) -> None:
        self.charges_pct = Decimal(charges_pct)
        self.repas_jour = Decimal(repas_jour)
        self.indemnite_jour = Decimal(indemnite_jour)
        self.heures_jour = Decimal(heures_jour)
        self.salaire_base_horaire = Decimal(salaire_base_horaire)
        self.charges_depot_h = Decimal(charges_depot_h)
        self.charges_bureau_h = Decimal(charges_bureau_h)
        self.marge_mo_pct = Decimal(marge_mo_pct)
        self.marge_materiaux_pct = Decimal(marge_materiaux_pct)
        self.marge_machines_pct = Decimal(marge_machines_pct)
        self.marge_outillage_pct = Decimal(marge_outillage_pct)
        self.marge_tiers_pct = Decimal(marge_tiers_pct)
        self.arrondi_chf = Decimal(arrondi_chf)

    @classmethod
    def from_mapping(cls, raw: dict | None) -> "TariffParams":
        """Build from a stored blob, falling back to the documented defaults.

        Unknown keys are ignored and a malformed value falls back rather than
        raising: a half-filled calibration must still produce a usable tariff.
        """
        data = dict(DEFAULTS)
        for key, value in (raw or {}).items():
            if key in DEFAULTS and str(value).strip() != "":
                data[key] = str(value)
        try:
            return cls(**data)  # type: ignore[arg-type]
        except Exception:
            return cls()

    def margin_for(self, family: str) -> Decimal:
        """Risk & profit fraction for a resource family (0 when unknown)."""
        key = MARGIN_KEY_BY_FAMILY.get((family or "").lower())
        return getattr(self, key) if key else Decimal("0")


def _q(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), ROUND_HALF_UP)


def round_to_step(value: Decimal | str | float, step: Decimal | str | float = "0.50") -> Decimal:
    """Round a selling price to the nearest step (Swiss habit: CHF 0.50).

    A step of 0 (or less) means "do not round" and returns the value at two
    decimals, so the caller can always pipe through this without branching.
    """
    v = Decimal(str(value))
    s = Decimal(str(step))
    if s <= 0:
        return _q(v)
    return _q((v / s).quantize(Decimal("1"), ROUND_HALF_UP) * s)


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
    # Depot and office overhead are already expressed per productive hour, so
    # they add straight onto the hourly cost (client feedback: both had to be
    # visible and editable, not buried inside the social-charges percentage).
    structure_h = _q(p.charges_depot_h + p.charges_bureau_h)
    fixed = base + charges + repas_indemnite_h + structure_h  # sans déplacement

    def travel_per_hour(billable_min: float) -> Decimal:
        cost_day = Decimal(str(billable_min)) / Decimal("60") * base
        return _q(cost_day / p.heures_jour)

    result = {
        "salaire_base_horaire_chf": str(base),
        "charges_pct": str(p.charges_pct),
        "charges_chf": str(charges),
        "repas_indemnite_horaire_chf": str(repas_indemnite_h),
        "charges_depot_horaire_chf": str(_q(p.charges_depot_h)),
        "charges_bureau_horaire_chf": str(_q(p.charges_bureau_h)),
        "charges_structure_horaire_chf": str(structure_h),
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

    # Selling price = cost + risk & profit on labour, rounded the way the
    # estimator quotes (CHF 0.50 by default). The cost figures above stay
    # untouched so the two are always readable side by side — the client wants
    # to see the margin, not have it folded silently into the cost.
    for role in ("conducteur", "passager"):
        cost = Decimal(result[f"cout_horaire_{role}_chf"])
        sell = cost * (Decimal("1") + p.marge_mo_pct)
        result[f"prix_horaire_{role}_chf"] = str(round_to_step(sell, p.arrondi_chf))
    result["marge_mo_pct"] = str(p.marge_mo_pct)
    result["arrondi_chf"] = str(p.arrondi_chf)
    return result

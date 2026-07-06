"""Depot -> site driving distance for the Protti travel-cost component.

Protti's labour tariff carries a *déplacement* (travel) component that depends on
the driving distance between the depot (Sottens, VD) and the construction site.
This module resolves that distance with **OpenStreetMap only** — no Google, no API
key:

* geocoding  -> Nominatim (address -> lat/lon)
* routing    -> OSRM       (two points -> driving distance + duration)

The public OSM/OSRM endpoints are rate-limited and meant for light use; for
production volume they should be self-hosted (documented in Obsidian). A polite
User-Agent is mandatory per the Nominatim usage policy.

The travel component follows the CN/CCT rule Protti described: 15 min each way is
offered (30 min/day), the driver (conducteur) is paid for all travel time, the
passengers only for the excess beyond the offered time.
"""

from __future__ import annotations

import httpx

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_URL = "https://router.project-osrm.org/route/v1/driving"
USER_AGENT = "Neoconstruction/1.0 (+https://neoffice.ch; Protti)"

# Protti SA depot. Default address geocoded on first use; overridable per instance.
DEPOT_ADDRESS = "Sottens, Vaud, Suisse"

# CN/CCT travel rule (minutes offered per one-way trip, both ways offered).
OFFERED_MIN_ONE_WAY = 15


async def geocode(address: str) -> tuple[float, float] | None:
    """Address -> (lat, lon) via Nominatim, or None if not found."""
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": USER_AGENT}) as client:
        resp = await client.get(
            NOMINATIM_URL,
            params={"q": address, "format": "json", "limit": 1, "countrycodes": "ch"},
        )
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return None
        return float(data[0]["lat"]), float(data[0]["lon"])


async def route(lat1: float, lon1: float, lat2: float, lon2: float) -> dict | None:
    """Driving distance/duration between two points via OSRM."""
    url = f"{OSRM_URL}/{lon1},{lat1};{lon2},{lat2}"
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": USER_AGENT}) as client:
        resp = await client.get(url, params={"overview": "false", "alternatives": "false"})
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "Ok" or not data.get("routes"):
            return None
        r = data["routes"][0]
        return {
            "distance_km": round(r["distance"] / 1000, 1),
            "duration_min": round(r["duration"] / 60, 1),
        }


async def depot_to_site(site_address: str, depot_address: str | None = None) -> dict:
    """Full computation: geocode depot + site, route, apply the CCT travel rule.

    Returns a dict with the raw distance/duration and the billable travel minutes
    per day (driver vs passengers), ready to feed the composed labour tariff.
    """
    depot = await geocode(depot_address or DEPOT_ADDRESS)
    site = await geocode(site_address)
    if depot is None or site is None:
        return {"error": "geocode_failed", "depot_found": depot is not None, "site_found": site is not None}
    leg = await route(depot[0], depot[1], site[0], site[1])
    if leg is None:
        return {"error": "route_failed"}

    one_way_min = leg["duration_min"]
    round_trip_min = round(one_way_min * 2, 1)
    offered_min = OFFERED_MIN_ONE_WAY * 2  # both ways offered
    passenger_billable_min = max(0.0, round(round_trip_min - offered_min, 1))
    return {
        "depot_address": depot_address or DEPOT_ADDRESS,
        "site_address": site_address,
        "distance_km": leg["distance_km"],
        "one_way_min": one_way_min,
        "round_trip_min": round_trip_min,
        "offered_min": offered_min,
        "driver_billable_min": round_trip_min,        # conducteur payé tout
        "passenger_billable_min": passenger_billable_min,  # passagers l'excédent
    }

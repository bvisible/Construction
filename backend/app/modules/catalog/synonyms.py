# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
"""Construction-vocabulary synonym expansion for resource and work search.

Estimators type the word they know; a price book stores the word its author
chose. "rebar" must still find "Reinforcement steel bar", "formwork" must find
"Shuttering", and a US "labor" must find a UK "labour" row. This maps a search
term to the set of interchangeable trade terms so a search can OR across all of
them, turning a dead-end "no matches" into a hit.

Kept deliberately conservative: only genuinely interchangeable words share a
group. Related-but-distinct materials (a brick is not a block, a door is not a
window) are never merged, so expansion never pulls in the wrong resource.
"""

from __future__ import annotations

# Each inner set is a group of interchangeable terms: typing any member searches
# for every member. Trade-jargon equivalents and US/UK spelling pairs only, so
# the expansion widens recall without dragging in a different material.
_SYNONYM_GROUPS: tuple[frozenset[str], ...] = (
    frozenset(
        {
            "rebar",
            "reinforcement",
            "reinforcing",
            "reinforcing bar",
            "reinforcing steel",
            "reinforcement steel",
        }
    ),
    frozenset({"formwork", "shuttering"}),
    frozenset({"plant", "equipment", "machinery"}),
    frozenset({"labour", "labor", "manpower", "workman"}),
    frozenset({"cement", "opc", "portland cement"}),
    frozenset({"plaster", "plastering", "render", "rendering"}),
    frozenset({"paint", "painting", "emulsion"}),
    frozenset({"excavation", "excavate", "earthwork", "earthworks"}),
    frozenset({"insulation", "insulating"}),
    frozenset({"timber", "lumber"}),
    frozenset({"scaffold", "scaffolding"}),
    frozenset({"waterproofing", "waterproof", "tanking"}),
    frozenset({"aggregate", "gravel", "ballast"}),
    frozenset({"tarmac", "asphalt", "blacktop"}),
    # US / UK spelling pairs that appear in resource names.
    frozenset({"fibre", "fiber"}),
    frozenset({"aluminium", "aluminum"}),
    frozenset({"colour", "color"}),
    frozenset({"mould", "mold"}),
    frozenset({"galvanised", "galvanized"}),
)

# term -> the full group it belongs to (built once at import).
_INDEX: dict[str, frozenset[str]] = {}
for _group in _SYNONYM_GROUPS:
    for _term in _group:
        _INDEX[_term] = _group


def expand_query(q: str, limit: int = 8) -> list[str]:
    """Return the search term plus any interchangeable trade synonyms.

    The original query is always first (so an exact / substring hit ranks
    itself); synonyms follow. Matching is whole-query and case-insensitive: a
    group is pulled in when the trimmed query equals one of its terms, so a short
    precise word like "plant" expands while a long descriptive phrase does not
    accidentally match a short synonym. Deduped and capped so the OR-expansion
    stays bounded.
    """
    original = q.strip()
    if not original:
        return []
    terms: list[str] = [original]
    group = _INDEX.get(original.lower())
    if group:
        terms.extend(term for term in sorted(group) if term.lower() != original.lower())
    seen: set[str] = set()
    out: list[str] = []
    for term in terms:
        key = term.lower()
        if key not in seen:
            seen.add(key)
            out.append(term)
        if len(out) >= limit:
            break
    return out

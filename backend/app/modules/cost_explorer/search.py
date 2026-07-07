# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
"""International, forgiving text-matching helpers for the Cost Explorer search.

An estimator anywhere in the world types the word they know, in the language
they think in, with or without accents, singular or plural. A price book stores
the word its author chose, in the language of its region. This module bridges
the two so a search still lands on the right priced work:

* :func:`fold` - normalise a string for comparison: strip accents/diacritics,
  collapse whitespace and lowercase, while leaving non-Latin scripts (Cyrillic)
  intact so a Russian term still matches a Russian row.
* :func:`match_terms` - expand a search word into the set of interchangeable
  construction terms across English, German, French, Spanish, Italian and
  Russian, plus simple singular/plural variants. Each variant is tagged as a
  *partial* match (the user's own word, matched as a substring so partial typing
  still finds a row) or a *whole word* match (a machine-injected cross-language
  synonym, matched on word boundaries so a short foreign word cannot poison the
  result by hiding inside an unrelated English word).
* :func:`variant_matches` - apply one variant against an already-folded haystack
  with the right partial / whole-word rule.
* :func:`text_search_hint` / :func:`by_resources_hint` - a short, plain-language,
  translation-ready hint telling a user what to try when a search returns
  nothing or only weak matches.

Pure and stdlib-only (``re`` + ``unicodedata``), so it imports and unit-tests on
any interpreter, independent of the FastAPI dependency graph.

The vocabulary is kept deliberately conservative: only genuinely interchangeable
words share a group. Related-but-distinct materials (a brick is not a block, a
door is not a window) are never merged, so expansion widens recall without ever
dragging in the wrong resource.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Cap the number of variants a single search word expands into, so the OR-search
# it drives stays bounded even for a word that sits in a large multilingual group.
_MAX_VARIANTS = 18

# Regex metacharacters that must be escaped before a folded variant is spliced
# into a word-boundary pattern (PostgreSQL ``~*`` regex or Python :mod:`re`).
_RX_SPECIAL = set(r".^$*+?()[]{}|\\")


def fold(text: str) -> str:
    """Normalise a string for accent-insensitive, case-insensitive comparison.

    Decomposes accented Latin letters and drops the combining marks (so ``Béton``
    folds to ``beton`` and ``hormigón`` to ``hormigon``), collapses runs of
    whitespace to single spaces, trims, and lowercases. Non-Latin scripts such as
    Cyrillic carry no combining marks here and survive unchanged, so a Russian
    query still matches a Russian row.
    """
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", stripped).strip().casefold()


def _rx_escape(term: str) -> str:
    """Escape only true regex metacharacters, leaving everything else literal.

    :func:`re.escape` over-escapes characters that PostgreSQL's regex engine does
    not treat as special, which can raise on ``~*``; this touches only the shared
    metacharacter set so the pattern is valid for both PostgreSQL and Python.
    """
    return "".join("\\" + ch if ch in _RX_SPECIAL else ch for ch in term)


def boundary_pattern(term: str) -> str:
    r"""Escape a term literally for splicing into a word-boundary regex.

    Returns the term with only regex metacharacters escaped, ready to sit
    between two word-boundary anchors (``\y`` in PostgreSQL's regex engine,
    ``\b`` in Python's :mod:`re`). The term is NOT accent-folded here: a database
    stores its text as authored, and PostgreSQL's regex cannot fold accents, so
    the accented spelling must reach it verbatim to match an accented row.
    :func:`match_terms` already emits both the accented and the folded spelling,
    so the unaccented rows are covered by the folded variant.
    """
    return _rx_escape(term)


# Groups of interchangeable construction terms. Typing any member searches for
# every member. Each group spans the trades and materials estimators search for
# most, across English, German, French, Spanish, Italian and Russian, plus the
# common US/UK spelling pairs. Accented spellings are listed as authored; the
# folded (accent-stripped) form is added automatically by :func:`match_terms`,
# so a base that stored either spelling is still reached.
_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"concrete", "beton", "béton", "hormigón", "calcestruzzo", "бетон"}),
    frozenset({"cement", "opc", "portland cement", "zement", "ciment", "cemento", "цемент"}),
    frozenset(
        {
            "rebar",
            "reinforcement",
            "reinforcing",
            "reinforcing bar",
            "reinforcing steel",
            "reinforcement steel",
            "bewehrung",
            "betonstahl",
            "armature",
            "armadura",
            "armatura",
            "арматура",
        }
    ),
    frozenset({"steel", "stahl", "acier", "acero", "acciaio", "сталь"}),
    frozenset({"formwork", "shuttering", "schalung", "coffrage", "encofrado", "cassaforma", "опалубка"}),
    frozenset({"brick", "brickwork", "ziegel", "brique", "ladrillo", "mattone", "кирпич"}),
    frozenset({"block", "blockwork", "hohlblock", "bloc", "bloque", "blocco", "блок"}),
    frozenset(
        {
            "plaster",
            "plastering",
            "render",
            "rendering",
            "putz",
            "enduit",
            "enlucido",
            "revoco",
            "intonaco",
            "штукатурка",
        }
    ),
    frozenset(
        {
            "paint",
            "painting",
            "emulsion",
            "anstrich",
            "peinture",
            "pintura",
            "pittura",
            "vernice",
            "краска",
        }
    ),
    frozenset(
        {
            "insulation",
            "insulating",
            "dämmung",
            "dammung",
            "isolation",
            "aislamiento",
            "isolamento",
            "изоляция",
            "утеплитель",
        }
    ),
    frozenset(
        {
            "excavation",
            "excavate",
            "earthwork",
            "earthworks",
            "aushub",
            "erdarbeiten",
            "terrassement",
            "excavación",
            "excavacion",
            "scavo",
            "земляные",
            "выемка",
        }
    ),
    frozenset(
        {
            "waterproofing",
            "waterproof",
            "tanking",
            "abdichtung",
            "étanchéité",
            "etancheite",
            "impermeabilización",
            "impermeabilizacion",
            "impermeabilizzazione",
            "гидроизоляция",
        }
    ),
    frozenset(
        {"scaffold", "scaffolding", "gerüst", "geruest", "échafaudage", "echafaudage", "andamio", "ponteggio", "леса"}
    ),
    frozenset({"timber", "lumber", "wood", "holz", "bois", "madera", "legno", "древесина", "дерево"}),
    frozenset(
        {
            "tile",
            "tiles",
            "tiling",
            "fliese",
            "carrelage",
            "baldosa",
            "azulejo",
            "piastrella",
            "плитка",
        }
    ),
    frozenset({"door", "doors", "tür", "tuer", "porte", "puerta", "porta", "дверь"}),
    frozenset({"window", "windows", "fenster", "fenêtre", "fenetre", "ventana", "finestra", "окно"}),
    frozenset(
        {
            "roof",
            "roofing",
            "dach",
            "toiture",
            "tejado",
            "cubierta",
            "tetto",
            "copertura",
            "крыша",
            "кровля",
        }
    ),
    frozenset(
        {
            "labour",
            "labor",
            "manpower",
            "workman",
            "arbeit",
            "lohn",
            "main d oeuvre",
            "mano de obra",
            "manodopera",
            "труд",
        }
    ),
    frozenset(
        {
            "plant",
            "equipment",
            "machinery",
            "geräte",
            "geraete",
            "maschinen",
            "maquinaria",
            "attrezzatura",
            "оборудование",
        }
    ),
    frozenset({"pipe", "piping", "rohr", "tuyau", "tube", "tubo", "труба"}),
    frozenset({"sand", "sable", "arena", "sabbia", "песок"}),
    frozenset(
        {
            "aggregate",
            "gravel",
            "ballast",
            "kies",
            "schotter",
            "gravier",
            "grava",
            "árido",
            "arido",
            "ghiaia",
            "щебень",
            "гравий",
        }
    ),
    frozenset({"glass", "glazing", "glas", "verre", "vidrio", "vetro", "стекло"}),
    frozenset({"mortar", "mörtel", "moertel", "mortier", "mortero", "malta", "раствор"}),
    frozenset({"asphalt", "tarmac", "blacktop", "asphalte", "asfalto", "асфальт"}),
    frozenset({"waterstop", "waterbar"}),
    # US / UK spelling pairs that appear verbatim in resource and work names.
    frozenset({"fibre", "fiber"}),
    frozenset({"aluminium", "aluminum"}),
    frozenset({"colour", "color"}),
    frozenset({"mould", "mold"}),
    frozenset({"galvanised", "galvanized"}),
)

# Folded term -> the full group it belongs to (built once at import). Folding the
# key means an accented ("béton") and an unaccented ("beton") spelling of the
# same word resolve to the same group.
_INDEX: dict[str, frozenset[str]] = {}
for _group in _GROUPS:
    for _term in _group:
        _INDEX.setdefault(fold(_term), _group)


def _number_variants(word: str) -> list[str]:
    """Simple singular/plural variants of a folded, single Latin word.

    Substring matching already finds a plural from a singular (``wall`` matches
    ``walls``); this adds the reverse (``walls`` also finds ``wall``) and a plural
    for a singular, so recall does not hinge on the exact form the base stored.
    Applied only to plain ASCII single words, so it never mangles a code, a
    phrase or a non-Latin term.
    """
    if len(word) < 4 or " " in word or not (word.isascii() and word.isalpha()):
        return []
    out: list[str] = []
    if word.endswith("es") and len(word) > 5:
        out.append(word[:-2])
    if word.endswith("s"):
        out.append(word[:-1])
    else:
        out.append(word + "s")
    return out


def match_terms(term: str, limit: int = _MAX_VARIANTS) -> list[tuple[str, bool]]:
    """Expand a search word into ``(variant, whole_word)`` match instructions.

    The first entries are *partial* matches (``whole_word`` False): the word as
    the user typed it, its folded form and its singular/plural variants, all
    matched as substrings so partial typing still lands. Cross-language synonyms
    from the same group follow as *whole word* matches (``whole_word`` True), so a
    short foreign word (for example French ``porte`` for a door) matches a real
    word in a description and never hides inside an unrelated English word (such
    as "supported"). Deduped by folded spelling and capped by ``limit``.
    """
    original = term.strip()
    if not original:
        return []
    out: list[tuple[str, bool]] = []
    seen: set[str] = set()

    def push(candidate: str, whole_word: bool) -> None:
        key = candidate.casefold()
        if candidate and key not in seen:
            seen.add(key)
            out.append((candidate, whole_word))

    push(original, False)
    key = fold(original)
    push(key, False)
    for variant in _number_variants(key):
        push(variant, False)

    group = _INDEX.get(key)
    if group:
        for member in sorted(group):
            push(member, True)
            push(fold(member), True)

    return out[:limit]


def expand_query(term: str, limit: int = _MAX_VARIANTS) -> list[str]:
    """The plain list of search variants for ``term`` (partial and synonym).

    A convenience over :func:`match_terms` for callers that only need the words,
    not how each should be matched. The original term is always first.
    """
    return [variant for variant, _ in match_terms(term, limit)]


def variant_matches(variant: str, hay_folded: str, *, whole_word: bool) -> bool:
    """True when ``variant`` occurs in an already-folded haystack.

    A whole-word variant must sit on word boundaries; a partial variant matches
    anywhere as a substring. ``hay_folded`` is expected to be the output of
    :func:`fold` already, so this only folds the variant.
    """
    needle = fold(variant)
    if not needle:
        return False
    if whole_word:
        return re.search(rf"\b{re.escape(needle)}\b", hay_folded) is not None
    return needle in hay_folded


# ── User guidance ────────────────────────────────────────────────────────────
#
# Short, plain-language hints returned alongside a result so a non-expert user
# knows what to try next. ``code`` is a stable machine key a localized UI can map
# to a translated string; ``message`` is a ready English fallback. No hint is
# returned when a search already has strong results, so the UI stays quiet when
# nothing needs saying.

# Below this top score a text result is treated as only an approximate match.
LOW_CONFIDENCE_SCORE = 0.5


@dataclass(frozen=True)
class SearchHint:
    """A translation-ready hint: a stable ``code`` and an English ``message``."""

    code: str
    message: str


def _filter_clause(has_region: bool, has_sources: bool) -> str:
    """Name the active filters so a hint can suggest removing the right one."""
    if has_region and has_sources:
        return "the region and source filters"
    if has_region:
        return "the region filter"
    if has_sources:
        return "the source filter"
    return ""


def text_search_hint(
    *,
    query: str,
    result_count: int,
    top_score: float = 0.0,
    has_region: bool = False,
    has_sources: bool = False,
) -> SearchHint | None:
    """Guidance for a free-text work search, or ``None`` when none is needed."""
    if not query or not query.strip():
        return SearchHint(
            "cost_explorer.hint.empty_query",
            "Type a word to search, for example a material, a trade, or a rate code.",
        )
    if result_count == 0:
        message = (
            "No priced works matched your search. Try a shorter or more general "
            "word, check the spelling, or search by the rate code."
        )
        filters = _filter_clause(has_region, has_sources)
        if filters:
            message += f" You can also remove {filters} to widen the search."
        return SearchHint("cost_explorer.hint.no_results", message)
    if top_score < LOW_CONFIDENCE_SCORE:
        return SearchHint(
            "cost_explorer.hint.low_confidence",
            "These are approximate matches. Try a more specific word, or check "
            "that the region matches the price base you expect.",
        )
    return None


def by_resources_hint(
    *,
    requested_count: int,
    result_count: int,
    has_region: bool = False,
    has_sources: bool = False,
) -> SearchHint | None:
    """Guidance for a by-resources search, or ``None`` when none is needed."""
    if requested_count == 0:
        return SearchHint(
            "cost_explorer.hint.no_resources",
            "Add at least one resource code to find the works that use it.",
        )
    if result_count == 0:
        message = "No priced works use these resources together. Try fewer resources, or check the resource codes."
        filters = _filter_clause(has_region, has_sources)
        if filters:
            message += f" You can also remove {filters} to widen the search."
        return SearchHint("cost_explorer.hint.no_results", message)
    return None

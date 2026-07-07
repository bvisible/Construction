"""Unit tests for the Cost Explorer international text-matching helpers.

``app.modules.cost_explorer.search`` is pure (``re`` + ``unicodedata`` only), so
it is loaded here directly from its file path, independent of the FastAPI
dependency graph, and runs identically here and in CI.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_PATH = Path(__file__).resolve().parents[2] / "app" / "modules" / "cost_explorer" / "search.py"
_spec = importlib.util.spec_from_file_location("cost_explorer_search", _PATH)
assert _spec and _spec.loader
search = importlib.util.module_from_spec(_spec)
sys.modules["cost_explorer_search"] = search
_spec.loader.exec_module(search)

fold = search.fold
expand_query = search.expand_query
match_terms = search.match_terms
variant_matches = search.variant_matches


def _variants(term: str) -> list[str]:
    return [fold(v) for v in expand_query(term)]


# ── fold: accent / case / whitespace normalisation ──────────────────────────


def test_fold_strips_accents_and_lowercases() -> None:
    assert fold("Béton Armé") == "beton arme"
    assert fold("HORMIGÓN") == "hormigon"
    assert fold("  spaced   out  ") == "spaced out"


def test_fold_keeps_cyrillic_intact() -> None:
    # Cyrillic carries no combining marks here, so it survives (only lowercased).
    assert fold("Бетон") == "бетон"


def test_fold_empty_is_empty() -> None:
    assert fold("") == ""
    assert fold("   ") == ""


# ── multilingual expansion for frequent trades / materials ──────────────────


def test_english_concrete_expands_across_languages() -> None:
    out = _variants("concrete")
    for word in ("beton", "hormigon", "calcestruzzo", "бетон"):
        assert word in out


def test_german_beton_finds_english_concrete() -> None:
    assert "concrete" in _variants("Beton")


def test_french_acier_finds_english_steel() -> None:
    assert "steel" in _variants("acier")


def test_spanish_hormigon_without_accent_finds_concrete() -> None:
    # A user who cannot type the accent still reaches the group.
    assert "concrete" in _variants("hormigon")


def test_italian_calcestruzzo_finds_concrete() -> None:
    assert "concrete" in _variants("calcestruzzo")


def test_russian_cyrillic_finds_english() -> None:
    assert "concrete" in _variants("бетон")
    assert "steel" in _variants("сталь")


def test_rebar_still_expands_to_reinforcement() -> None:
    # The original English behaviour is preserved (superset).
    out = _variants("rebar")
    assert "reinforcement" in out


def test_us_uk_spelling_pairs_expand_both_ways() -> None:
    assert "labour" in _variants("labor")
    assert "labor" in _variants("labour")
    assert "fiber" in _variants("fibre")


# ── singular / plural ───────────────────────────────────────────────────────


def test_plural_query_also_matches_singular() -> None:
    # "walls" is not a substring of "wall", so a singular variant is needed.
    assert "wall" in _variants("walls")


def test_singular_query_also_offers_plural() -> None:
    assert "walls" in _variants("wall")


# ── distinct materials never merged (poisoning guard) ───────────────────────


def test_distinct_materials_are_never_merged() -> None:
    assert "block" not in _variants("brick")
    assert "brick" not in _variants("block")
    assert "window" not in _variants("door")
    assert "door" not in _variants("window")


# ── partial vs whole-word tagging ───────────────────────────────────────────


def test_user_word_is_partial_synonym_is_whole_word() -> None:
    terms = match_terms("door")
    by_word = {fold(word): whole for word, whole in terms}
    # The word the user typed matches as a substring (partial).
    assert by_word["door"] is False
    # An injected short cross-language synonym matches on word boundaries.
    assert by_word["porte"] is True


def test_whole_word_synonym_does_not_poison_substring() -> None:
    # French "porte" (door) must not match inside the English word "supported".
    hay = fold("Supported precast beam")
    assert variant_matches("porte", hay, whole_word=True) is False
    # But it does match a real standalone word.
    assert variant_matches("porte", fold("Porte en bois"), whole_word=True) is True


def test_partial_variant_matches_substring() -> None:
    hay = fold("Reinforced concrete wall")
    assert variant_matches("concret", hay, whole_word=False) is True


def test_accent_insensitive_variant_match() -> None:
    hay = fold("Béton armé pour dalle")
    assert variant_matches("beton", hay, whole_word=True) is True


# ── edge cases / robustness ─────────────────────────────────────────────────


def test_blank_and_whitespace_expand_to_nothing() -> None:
    assert match_terms("") == []
    assert match_terms("   ") == []
    assert expand_query("") == []


def test_unknown_term_returns_itself_only() -> None:
    # A word in no group still returns itself plus its own morphology, but no
    # foreign synonyms.
    out = _variants("gizmo")
    assert "gizmo" in out
    assert all(v.isascii() for v in out)


def test_original_term_is_first() -> None:
    terms = match_terms("Beton")
    assert terms[0][0] == "Beton"  # verbatim, so an exact hit ranks itself


def test_expansion_is_capped_and_deduped() -> None:
    out = expand_query("concrete", limit=5)
    assert len(out) <= 5
    assert len(out) == len({v.casefold() for v in out})


def test_very_long_query_does_not_crash() -> None:
    long_word = "a" * 500
    out = match_terms(long_word)
    assert out  # returns at least the word itself
    assert len(out) <= search._MAX_VARIANTS


def test_regex_special_query_is_escaped_not_crashing() -> None:
    # A query full of regex metacharacters must be matched literally, never raise
    # (metacharacters are escaped before they reach the regex engine).
    hay = fold("pipe (dn 100) c++ grade")
    assert variant_matches("(dn 100)", hay, whole_word=False) is True
    # A term is escaped literally on both paths; the call returns a bool cleanly.
    assert isinstance(variant_matches("c++", hay, whole_word=True), bool)
    assert variant_matches("c++", hay, whole_word=False) is True


# ── user guidance hints ─────────────────────────────────────────────────────


def test_text_hint_empty_query() -> None:
    hint = search.text_search_hint(query="   ", result_count=0)
    assert hint is not None
    assert hint.code == "cost_explorer.hint.empty_query"


def test_text_hint_no_results_mentions_active_filter() -> None:
    hint = search.text_search_hint(query="unobtanium", result_count=0, has_region=True)
    assert hint is not None
    assert hint.code == "cost_explorer.hint.no_results"
    assert "region" in hint.message.lower()


def test_text_hint_no_results_without_filter_omits_filter_sentence() -> None:
    hint = search.text_search_hint(query="unobtanium", result_count=0)
    assert hint is not None
    assert "remove" not in hint.message.lower()


def test_text_hint_low_confidence() -> None:
    hint = search.text_search_hint(query="wall", result_count=3, top_score=0.2)
    assert hint is not None
    assert hint.code == "cost_explorer.hint.low_confidence"


def test_text_hint_strong_result_is_silent() -> None:
    assert search.text_search_hint(query="wall", result_count=3, top_score=0.9) is None


def test_by_resources_hint_no_resources() -> None:
    hint = search.by_resources_hint(requested_count=0, result_count=0)
    assert hint is not None
    assert hint.code == "cost_explorer.hint.no_resources"


def test_by_resources_hint_no_results_mentions_filter() -> None:
    hint = search.by_resources_hint(requested_count=2, result_count=0, has_region=True, has_sources=True)
    assert hint is not None
    assert hint.code == "cost_explorer.hint.no_results"
    assert "region and source" in hint.message.lower()


def test_by_resources_hint_strong_result_is_silent() -> None:
    assert search.by_resources_hint(requested_count=2, result_count=5) is None


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("ok", fn.__name__)
    print(f"\n{len(fns)} search tests passed")

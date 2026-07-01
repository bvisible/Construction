"""Deterministic reader for the *tables* an architect prints on a plan.

The geometric take-off (:mod:`element_metre`) measures walls, slabs and rooms
from the vector layers, but it is blind to the tabular data the architect types
next to the drawing:

* **Schedules / nomenclatures** — door lists, window lists, finish schedules
  (FR *nomenclature des portes / fenêtres*, DE *Türliste / Fensterliste*). These
  carry counts, dimensions and specs the geometry cannot recover.
* **Title block (cartouche)** — scale, format, project, owner, date, revision
  index. Useful metadata printed as ``label:\\nvalue`` cells.

This is 100 % deterministic (``pdfplumber`` table extraction + keyword
classification) — no AI, no network. Inspired by the text/table extraction leg
of open material-estimation pipelines, but kept LLM-free: we only *read* the
architect's own tables, we never *interpret* free text.

NEOFFICE — Neoffice-only module, no core OCE patch.
"""

from __future__ import annotations

import io
import re
from typing import Any

# ── Classification of a real (non-empty) table by what its text mentions ──────
# FR / DE / EN so it generalises across the plans Neoffice clients send.
_SCHEDULE_KEYWORDS: list[tuple[str, re.Pattern[str]]] = [
    ("doors", re.compile(r"\b(portes?|t[uü]r(?:en|liste)?|door)\b", re.I)),
    ("windows", re.compile(r"\b(fen[eê]tres?|fenster(?:liste)?|window)\b", re.I)),
    ("finishes", re.compile(r"\b(finitions?|rev[eê]tements?|bel[aä]ge?|finish(?:es)?)\b", re.I)),
    ("rooms", re.compile(r"\b(locaux|local|pi[eè]ces?|r[aä]ume?|surfaces?)\b", re.I)),
]

# A cartouche cell looks like "échelle:\n1:50" or "projet:\nSavièse". We split on
# the first colon and keep the label only when it is one of these known keys, so
# a stray "1:50" dimension inside the drawing is never mistaken for a label.
_TITLE_KEYS: list[tuple[str, re.Pattern[str]]] = [
    ("scale", re.compile(r"^(échelle|echelle|scale|ma[ßss]stab)$", re.I)),
    ("format", re.compile(r"^(format|papier|blatt)$", re.I)),
    ("project", re.compile(r"^(projet|project|objet|bauvorhaben|bauprojekt)$", re.I)),
    ("title", re.compile(r"^(titre(?: du plan)?|title|plan|planinhalt)$", re.I)),
    ("owner", re.compile(r"^(ma[îi]tre d.?ouvrage|owner|client|bauherr(?:schaft)?)$", re.I)),
    ("architect", re.compile(r"^(architecte?|architect|planer|bureau)$", re.I)),
    ("signed_by", re.compile(r"^(sign[ée] par|signed|gezeichnet|dessin[ée] par|vu par)$", re.I)),
    ("date", re.compile(r"^(date(?: de révision)?|datum)$", re.I)),
    ("revision", re.compile(r"^(indice|index(?: de révision)?|revision|révision)$", re.I)),
    ("plan_no", re.compile(r"^(no\.?|n[°o]|num[ée]ro|plan.?nr|nr\.?)$", re.I)),
]

_MAX_SCHEDULE_ROWS = 200  # a runaway "table" is a mis-detected grid; cap it.
# pdfplumber's extract_tables() cost scales super-linearly with edge count and
# HANGS on dense drawing sheets (a section/facade with 400k vectors took >60 s on
# the osiris VM, vs ~6 s for a 12k-vector floor plan). Those dense sheets never
# carry a door/finish schedule anyway, so above this vector count we skip the
# whole table scan — this is what kept the "Métré" button from hanging on
# multi-sheet PDFs (sections + facades). Clean floor plans stay well under it.
_MAX_VECTORS = 25000


def _clean(cell: Any) -> str:
    """Collapse a raw pdfplumber cell to a single trimmed line."""
    if cell is None:
        return ""
    return re.sub(r"\s+", " ", str(cell)).strip()


def _cells(table: list[list[Any]]) -> list[Any]:
    return [c for row in table for c in row]


def _nonempty_ratio(table: list[list[Any]]) -> float:
    cells = _cells(table)
    if not cells:
        return 0.0
    return sum(1 for c in cells if _clean(c)) / len(cells)


def _classify(table: list[list[Any]]) -> str:
    text = " ".join(_clean(c) for c in _cells(table)).lower()
    for kind, rx in _SCHEDULE_KEYWORDS:
        if rx.search(text):
            return kind
    return "generic"


def _title_key_hits(table: list[list[Any]]) -> int:
    """Count cells whose ``label:`` matches a title-block key.

    Used to tell the cartouche apart from a real schedule: the cartouche is a
    handful of ``label: value`` cells, so two or more hits means "this is the
    title block, not a door/finish list" and it must not be reported twice.
    """
    hits = 0
    for raw in _cells(table):
        if raw is None or ":" not in str(raw):
            continue
        label = _clean(str(raw).partition(":")[0]).lower()
        if any(rx.match(label) for _, rx in _TITLE_KEYS):
            hits += 1
    return hits


def _harvest_title_block(tables: list[list[list[Any]]]) -> dict[str, str]:
    """Pull ``label: value`` pairs out of cartouche-style cells.

    Cartouche cells are printed as ``"label:\\nvalue"`` (e.g. ``"échelle:\\n1:50"``).
    We split on the FIRST colon, normalise the label, and keep the value only
    when the label matches a known title-block key — so a dimension like
    ``"1:50"`` sitting loose in the drawing never becomes a spurious field.
    """
    out: dict[str, str] = {}
    for table in tables:
        for raw in _cells(table):
            if raw is None:
                continue
            cell = str(raw)
            if ":" not in cell:
                continue
            label_part, _, value_part = cell.partition(":")
            label = _clean(label_part).lower()
            value = _clean(value_part)
            if not label or not value:
                continue
            for key, rx in _TITLE_KEYS:
                if key in out:  # first non-empty wins (top-most cartouche cell)
                    continue
                if rx.match(label):
                    out[key] = value[:120]
                    break
    return out


def read_plan_schedules(
    pdf_bytes: bytes, page_index: int = 0, *, vector_count: int | None = None
) -> dict[str, Any]:
    """Read the schedules and the title block off one PDF page.

    Args:
        pdf_bytes: Raw PDF bytes.
        page_index: 0-based page index.
        vector_count: Number of vector drawings on the page, if the caller
            already knows it (``compute_element_metre`` does). Passed to skip the
            table scan on dense sheets without re-parsing the page; when ``None``
            it is counted here.

    Returns:
        ``{"title_block": {...}, "schedules": [...], "raw_table_count": int,
        "dropped_empty": int}``. ``schedules`` holds only real tables (each
        ``{"type", "headers", "rows", "row_count"}``); a plan that carries no
        schedule returns an empty list (honest, never an error). A dense sheet
        skipped by the density guard returns ``skipped_dense: True``.
    """
    result: dict[str, Any] = {
        "title_block": {},
        "schedules": [],
        "raw_table_count": 0,
        "dropped_empty": 0,
    }
    # Density guard — a dense section/facade sheet would hang pdfplumber; skip it.
    if vector_count is None:
        try:
            import pymupdf

            with pymupdf.open(stream=pdf_bytes, filetype="pdf") as _doc:
                if 0 <= page_index < _doc.page_count:
                    vector_count = len(_doc[page_index].get_drawings())
        except Exception:  # noqa: BLE001 - counting must never sink the read
            vector_count = None
    if vector_count is not None and vector_count > _MAX_VECTORS:
        result["skipped_dense"] = True
        return result

    try:
        import pdfplumber
    except ImportError:
        result["error"] = "pdfplumber_missing"
        return result

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        if page_index < 0 or page_index >= len(pdf.pages):
            return result
        page = pdf.pages[page_index]
        try:
            tables = page.extract_tables() or []
        except Exception:  # noqa: BLE001 - a malformed grid must not sink the read
            tables = []

    result["raw_table_count"] = len(tables)
    # The cartouche is often one of the "sparse" tables, so harvest it from ALL
    # detected tables (before the schedule filter drops the sparse ones).
    result["title_block"] = _harvest_title_block(tables)

    for table in tables:
        # A real schedule has several filled rows; the drawing's ruled lines
        # produce mostly-empty grids that we drop (but title_block already
        # mined them above).
        filled_rows = [r for r in table if any(_clean(c) for c in r)]
        if len(filled_rows) < 3 or _nonempty_ratio(table) < 0.30:
            result["dropped_empty"] += 1
            continue
        # The cartouche also survives the density filter; it is already captured
        # in title_block, so drop it here instead of reporting it as a schedule.
        if _title_key_hits(table) >= 2:
            result["dropped_empty"] += 1
            continue
        headers = [_clean(c) for c in filled_rows[0]]
        body = [[_clean(c) for c in r] for r in filled_rows[1 : 1 + _MAX_SCHEDULE_ROWS]]
        result["schedules"].append(
            {
                "type": _classify(table),
                "headers": headers,
                "rows": body,
                "row_count": len(body),
            }
        )
    return result

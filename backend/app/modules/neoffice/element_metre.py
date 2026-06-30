"""Deterministic element take-off (métré) from a vector PDF's OCG layers.

NEOFFICE module — 100% ours (no upstream coupling). Companion to
``room_detection.py`` (which detects *rooms*); this module measures *structural
& finish elements* (concrete walls/slabs by type, partitions + linear metres)
by reading the architect's CAD **layers** preserved in a vector PDF.

Why this works without any ML: ArchiCAD/Allplan/Revit PDF exports keep their
Optional Content Groups (OCG = layers) with semantic names. PyMuPDF exposes
the layer of every stroke via ``page.get_drawings()[i]["layer"]`` (v1.22+). We
classify each layer to an element taxonomy by **regex on the layer name** (so
it generalises across architects / FR-DE conventions), pair the two parallel
faces of each wall into a centre-line, and sum lengths/areas at the plan scale.

Honest scope: deterministic for Case A (vector + named layers). Wall surface
m² needs a storey height that is NOT on the floor plan (read it on the section
sheet, or pass ``storey_height``; default flagged as an assumption). Door
counts, salient/reentrant angles and window reveals are separate deterministic
passes (see TODO at the bottom) — not yet implemented here.
"""

from __future__ import annotations

import math
import re
from typing import Any

try:  # pragma: no cover - import guard mirrors room_detection
    import pymupdf  # type: ignore
except ImportError:  # pragma: no cover
    import fitz as pymupdf  # type: ignore

from shapely.geometry import LineString
from shapely.ops import polygonize, unary_union
from shapely.strtree import STRtree

# ── Element taxonomy: layer-name regex → (element key, eBKP-H code) ───────────
# Order matters: first match wins. Patterns are case-insensitive and cover the
# common ArchiCAD/Allplan FR + DE layer naming seen on Swiss plans.
_LAYER_RULES: list[tuple[str, str, str]] = [
    (r"escalier|treppe|stair", "escalier", "C02"),
    # Structural-engineer overlay: often REDRAWS the architectural walls, so it
    # is kept in its own bucket (cross-check) and excluded from the wall totals
    # to avoid double-counting with the architectural "porteur" layer.
    (r"tragstruktur|tragwerk", "structure_overlay", ""),
    (r"non[- ]?porteur|leichtbau|cloison|innenwand|innenwaende", "cloison", "G01"),
    (r"porteur|tragende?\s*wand|tragmauer", "beton_porteur", "C02.02"),
    (r"ext[ée]rieur|aussen|au[ßs]senwand", "beton_exterieur", "C02.01"),
    (r"sols?\b.*dalle|dalle|decke|bodenplatte", "dalle", "C04"),
    (r"\bmur\b|\bwand\b|\bwall\b", "mur_autre", "C02"),
]

# Element keys excluded from the headline wall total (reported separately).
_NON_BILLABLE = {"structure_overlay"}

# Wall double-line pairing thresholds (PDF points). Defaults sized for 1:50.
_OFFSET_MIN_PT = 2.5
_OFFSET_MAX_PT = 22.0
_PARALLEL_DEG = 8.0
_MIN_OVERLAP_PT = 8.0
_MIN_SEG_PT = 3.0

_PT_PER_INCH = 72.0
_M_PER_INCH = 0.0254


def classify_layer(name: str | None) -> tuple[str, str] | None:
    """Map a raw OCG layer name to (element_key, ebkp_code) or None."""
    if not name:
        return None
    low = name.lower()
    for pattern, key, ebkp in _LAYER_RULES:
        if re.search(pattern, low):
            return key, ebkp
    return None


def _seg_dir(s):
    (x1, y1), (x2, y2) = s
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    return ((dx / length, dy / length) if length else (0.0, 0.0)), length


def _angle_deg(d1, d2) -> float:
    c = max(-1.0, min(1.0, abs(d1[0] * d2[0] + d1[1] * d2[1])))
    return math.degrees(math.acos(c))


def _perp_offset(s1, s2) -> float:
    (ax, ay), _ = s1
    bx, by = s2[0]
    d1, _ = _seg_dir(s1)
    n = (-d1[1], d1[0])
    return abs((bx - ax) * n[0] + (by - ay) * n[1])


def _element_segments(page) -> dict[str, list]:
    """Group wall/line items by element key from their layer."""
    out: dict[str, list] = {}
    for d in page.get_drawings():
        cls = classify_layer(d.get("layer"))
        if not cls:
            continue
        key = cls[0]
        bucket = out.setdefault(key, [])
        for it in d.get("items", []):
            if it[0] == "l":
                a, b = it[1], it[2]
                bucket.append(((a.x, a.y), (b.x, b.y)))
    return out


def _centerlines(segs) -> list[LineString]:
    """Pair the two parallel faces of each wall → midline LineStrings."""
    if not segs:
        return []
    geoms = [LineString(s) for s in segs]
    dirs = [_seg_dir(s) for s in segs]
    tree = STRtree(geoms)
    mids: list[LineString] = []
    used: set[tuple[int, int]] = set()
    for i, s1 in enumerate(segs):
        d1, length1 = dirs[i]
        if length1 < _MIN_SEG_PT:
            continue
        import numpy as np

        p0 = np.array(s1[0], dtype=float)
        u = np.array(d1, dtype=float)
        for j in tree.query(geoms[i].buffer(_OFFSET_MAX_PT + 2)):
            j = int(j)
            if j <= i or (i, j) in used:
                continue
            d2, length2 = dirs[j]
            if length2 < _MIN_SEG_PT or _angle_deg(d1, d2) > _PARALLEL_DEG:
                continue
            s2 = segs[j]
            off = _perp_offset(s1, s2)
            if not (_OFFSET_MIN_PT <= off <= _OFFSET_MAX_PT):
                continue
            t = [(np.array(p, dtype=float) - p0) @ u for p in (s1[0], s1[1], s2[0], s2[1])]
            lo = max(min(t[0], t[1]), min(t[2], t[3]))
            hi = min(max(t[0], t[1]), max(t[2], t[3]))
            if hi - lo < _MIN_OVERLAP_PT:
                continue
            n = np.array((-u[1], u[0]))
            if (np.array(s2[0], dtype=float) - p0) @ n < 0:
                n = -n
            a = p0 + lo * u + (off / 2.0) * n
            b = p0 + hi * u + (off / 2.0) * n
            mids.append(LineString([tuple(a), tuple(b)]))
            used.add((i, j))
            break
    return mids


def _ml(mids: list[LineString], mpp: float) -> float:
    if not mids:
        return 0.0
    return float(unary_union(mids).length * mpp)


# Snap grid (PDF points) to close hairline gaps before polygonising slab edges.
_SLAB_SNAP_PT = 1.0
# Discard polygonised faces smaller than this (m²): hatch artefacts, dimension
# boxes, text outlines that leak into the slab layer.
_SLAB_MIN_FACE_M2 = 1.0


def _slab_metrics(segs, mpp: float) -> tuple[float, float, int]:
    """Slab take-off from outline strokes: (area_m², edge_perimeter_m, n_faces).

    The slab layer is drawn as an outline (no fill), so we node the strokes and
    polygonise the planar graph. Summing the faces gives the poured-concrete
    footprint (sub-division lines per zone don't double-count — polygonise
    yields a planar partition). The perimeter of the dissolved footprint is the
    edge formwork (coffrage de rive). Tiny faces are dropped as artefacts.
    """
    if not segs:
        return 0.0, 0.0, 0

    def _snap(p):
        return (round(p[0] / _SLAB_SNAP_PT) * _SLAB_SNAP_PT,
                round(p[1] / _SLAB_SNAP_PT) * _SLAB_SNAP_PT)

    lines = [LineString([_snap(a), _snap(b)]) for a, b in segs if _snap(a) != _snap(b)]
    if not lines:
        return 0.0, 0.0, 0
    min_face_pt2 = _SLAB_MIN_FACE_M2 / (mpp * mpp)
    faces = [p for p in polygonize(unary_union(lines)) if p.area >= min_face_pt2]
    if not faces:
        return 0.0, 0.0, 0
    footprint = unary_union(faces)
    area_m2 = sum(p.area for p in faces) * mpp * mpp
    perimeter_m = footprint.length * mpp
    return float(area_m2), float(perimeter_m), len(faces)


def compute_element_metre(
    pdf_bytes: bytes,
    page_index: int,
    scale_ratio: float | None = None,
    storey_height_m: float = 2.70,
) -> dict[str, Any]:
    """Return per-element quantities (ml + m²) for one floor-plan page.

    ``scale_ratio`` is the plan denominator (e.g. 50 for 1:50). If None we try
    the dimension-based scale from room_detection; else fall back to 50.
    """
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    page = doc[page_index]

    if scale_ratio is None:
        try:
            from app.modules.neoffice.room_detection import _dimension_scale_m_per_pt

            mpp = _dimension_scale_m_per_pt(page)
            if mpp:
                scale_ratio = round(mpp / (_M_PER_INCH / _PT_PER_INCH))
        except Exception:
            scale_ratio = None
    if not scale_ratio:
        scale_ratio = 50.0
    mpp = _M_PER_INCH / _PT_PER_INCH * scale_ratio  # metres per PDF point

    # eBKP code per element key (first matching rule wins).
    ebkp_by_key: dict[str, str] = {}
    for _pat, k, e in _LAYER_RULES:
        ebkp_by_key.setdefault(k, e)

    buckets = _element_segments(page)
    elements: dict[str, Any] = {}
    for key, segs in buckets.items():
        if key == "dalle":
            # Slab: area from polygonised outline; "linear" = edge formwork.
            area_m2, perimeter_m, n_faces = _slab_metrics(segs, mpp)
            elements[key] = {
                "ebkp": ebkp_by_key.get(key, ""),
                "linear_m": round(perimeter_m, 1),
                "surface_m2": round(area_m2, 1),
                "faces": len(segs),
                "measure": "slab_footprint",
            }
            continue
        # Wall-type element: pair the two faces into a centre-line.
        mids = _centerlines(segs)
        ml = _ml(mids, mpp)
        elements[key] = {
            "ebkp": ebkp_by_key.get(key, ""),
            "linear_m": round(ml, 1),
            "surface_m2": round(ml * storey_height_m, 1),
            "faces": len(segs),
            "measure": "wall_centerline",
        }

    return {
        "page": page_index,
        "scale_ratio": scale_ratio,
        "metres_per_point": round(mpp, 6),
        "storey_height_m": storey_height_m,
        "storey_height_is_assumption": True,
        "elements": elements,
        "todo": [
            "door counts (gap detection in partition layer)",
            "salient/reentrant angles (shapely cross-product on outlines)",
            "window reveals (opening perimeter from wall thickness)",
            "crawl-space lining + junction linear metres",
            "slab classification (bathroom/stairwell) via room labels",
        ],
    }

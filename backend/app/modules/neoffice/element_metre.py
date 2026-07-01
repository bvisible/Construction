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

# Material sub-classification by drawing colour. Architects tag special walls
# with a coloured outline (béton apparent) or a coloured fill (fire compartment,
# bathroom) on top of the black hatch — see the plan's "hachures" legend. We
# read the stroke/fill colour and, by proximity, tag each concrete wall's
# material so the béton total splits by type (huge for pricing: each material is
# a different unit price).
#
# GENERALISATION: colours are NOT standardised across architects, so we do NOT
# hard-code them. The primary source is the plan's OWN legend, read at runtime
# (``_learn_materials_from_legend``) → {colour: label} for that specific PDF.
# This map below is only a last-resort fallback when a plan has no readable
# legend (it happens to be the ARTTESA/Savièse convention).
_MATERIAL_COLORS_FALLBACK: dict[str, str] = {
    "#e22817": "Béton type 4 (apparent)",
    "#e7c62f": "Béton type 2 (apparent)",
    "#5081f3": "EI30 RF1 (coupe-feu)",
    "#e86a1f": "EI30 (coupe-feu)",
    "#ff8000": "Swisspor (isolation)",
    "#4eb525": "SDB (carreaux plâtre)",
}
# Buffer (PDF points) grown around a colour marker to catch the wall it tags.
_MATERIAL_BUFFER_PT = 18.0
# Words that mark the start of a hatch/material legend block (FR/DE/EN, since
# offices title it differently: hachures, légende, Legende, Schraffur, materials).
_LEGEND_ANCHOR = re.compile(r"hachure|l[ée]gende|legend|mat[ée]ria|schraffur", re.I)

# Hatch-MOTIF classification (poured vs precast concrete). Unlike colour, the
# hatch pattern is a stable drawing convention (ISO/SIA): cross-hatch (±45°) =
# poured/apparent concrete, orthogonal grid (0/90°) = precast. We isolate the
# concrete hatch, render it, and compare spectral energy per tile via FFT — the
# FFT needs periodic regularity, so it ignores the stray orthogonal lines that
# fooled the raw vector angle histogram.
_HATCH_MAX_PT = 40.0        # a stroke shorter than this is a hatch fill stroke
# 2 px/pt keeps the FFT discrimination identical to higher scales but the raster
# stays small (A0 @ scale 6 = 144 MP → OOM/swap on the constrained osiris VM;
# @ scale 2 = 16 MP, ~0.4 s). The periodic hatch signal survives the downscale.
_PATTERN_SCALE = 2          # raster px per PDF point for the hatch FFT
_PATTERN_TILE_PT = 50.0     # FFT tile size (PDF points)
_PATTERN_INK_MIN = 0.02     # min ink fraction for a tile to be analysed
_PATTERN_LABELS = {
    "coule": "Béton coulé (croisillon)",
    "prefab": "Béton préfabriqué (grille)",
    "mix": "Béton — motif à vérifier",
}

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


def _hex_color(c) -> str | None:
    """PyMuPDF colour tuple (0..1 floats) → '#rrggbb', or None."""
    if not c:
        return None
    try:
        return "#%02x%02x%02x" % tuple(int(round(x * 255)) for x in c)
    except Exception:
        return None


def _learn_materials_from_legend(page) -> dict[str, str]:
    """Read the plan's OWN hatch/colour legend → ``{colour_hex: material_label}``.

    This is what makes the material split generalise across architects: rather
    than hard-coding one office's palette, we find the legend block (title
    ``hachures`` / ``légende``), take each coloured swatch, and pair it with the
    text on its row. Returns ``{}`` when no legend is found.
    """
    words = page.get_text("words")  # (x0, y0, x1, y1, text, block, line, wno)
    anchor = next((w for w in words if _LEGEND_ANCHOR.search(w[4])), None)
    if anchor is None:
        return {}
    ax0, ay = anchor[0], anchor[3]
    # Coloured swatches in the legend column, at or below the title.
    swatches: list[tuple[str, float, float]] = []  # (colour, y_center, x_right)
    for d in page.get_drawings():
        col = _hex_color(d.get("fill")) or _hex_color(d.get("color"))
        if not col or col in ("#000000", "#ffffff"):
            continue
        r = d.get("rect")
        if r is None:
            continue
        cy = (r.y0 + r.y1) / 2.0
        if ay - 12 <= cy <= ay + 240 and ax0 - 60 <= r.x0 <= ax0 + 100:
            swatches.append((col, cy, max(r.x0, r.x1)))
    # Topmost swatch per colour → the legend row that defines it.
    seen: dict[str, tuple[float, float]] = {}
    for col, cy, xr in sorted(swatches, key=lambda s: s[1]):
        seen.setdefault(col, (cy, xr))
    out: dict[str, str] = {}
    for col, (cy, xr) in seen.items():
        row = [w for w in words if abs((w[1] + w[3]) / 2.0 - cy) < 7 and xr < w[0] < xr + 360]
        row.sort(key=lambda w: w[0])
        label = " ".join(w[4] for w in row).strip()
        if label:
            out[col] = label
    return out


def _material_regions(page):
    """Buffered shapely region per material, from the coloured stroke/fill markers.

    Returns ``(regions, colour_map)`` where ``regions`` is
    ``{material_label: geometry}`` and ``colour_map`` is the ``{hex: label}``
    actually used (learned from the plan's legend, else the built-in fallback).
    A concrete wall whose centre-line falls inside a region is tagged with it.
    """
    colour_map = _learn_materials_from_legend(page) or _MATERIAL_COLORS_FALLBACK
    by_mat: dict[str, list] = {}
    for d in page.get_drawings():
        mat = (colour_map.get(_hex_color(d.get("color")))
               or colour_map.get(_hex_color(d.get("fill"))))
        if not mat:
            continue
        for it in d.get("items", []):
            if it[0] == "l":
                a, b = it[1], it[2]
                if (a.x, a.y) != (b.x, b.y):
                    by_mat.setdefault(mat, []).append(LineString([(a.x, a.y), (b.x, b.y)]))
            elif it[0] == "re":
                r = it[1]
                by_mat.setdefault(mat, []).append(LineString([
                    (r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1), (r.x0, r.y0),
                ]))
    regions = {m: unary_union(ls).buffer(_MATERIAL_BUFFER_PT) for m, ls in by_mat.items() if ls}
    return regions, colour_map


def _tag_material(mid: LineString, regions: dict[str, Any]) -> str | None:
    """Material label of the region the wall centre-line overlaps most, or None."""
    best, best_len = None, 0.0
    for mat, reg in regions.items():
        try:
            inter = mid.intersection(reg).length
        except Exception:
            inter = 0.0
        if inter > best_len:
            best_len, best = inter, mat
    return best if best_len > 0 else None


def _beton_hatch_pattern(page):
    """FFT of the isolated concrete hatch → tile map ``{(row,col): 'coule'|'prefab'|'mix'}``.

    Returns ``(tiles, scale, tile_px)``. We render ONLY the short strokes of the
    concrete layers (drops the long wall faces + every other layer), tile it,
    and per tile compare diagonal (±45°, cross-hatch → poured) vs orthogonal
    (0/90°, grid → precast) spectral energy. Isolating the hatch is what makes
    it reliable; the FFT's periodicity requirement rejects stray orthogonal
    lines that the raw vector angle histogram mistook for a grid.
    """
    import numpy as np

    scale = _PATTERN_SCALE
    doc = pymupdf.open()
    blank = doc.new_page(width=page.rect.width, height=page.rect.height)
    shape = blank.new_shape()
    drew = 0
    for d in page.get_drawings():
        cls = classify_layer(d.get("layer"))
        if not cls or cls[0] not in ("beton_porteur", "beton_exterieur"):
            continue
        for it in d.get("items", []):
            if it[0] == "l":
                a, b = it[1], it[2]
                if 1.0 < math.hypot(b.x - a.x, b.y - a.y) < _HATCH_MAX_PT:
                    shape.draw_line(pymupdf.Point(a.x, a.y), pymupdf.Point(b.x, b.y))
                    drew += 1
    tpx = int(_PATTERN_TILE_PT * scale)
    if drew < 20:
        return {}, scale, tpx
    shape.finish(color=(0, 0, 0), width=0.5)
    shape.commit()
    pm = blank.get_pixmap(matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csGRAY)
    img = 255.0 - np.frombuffer(pm.samples, dtype=np.uint8).reshape(pm.height, pm.width).astype(float)

    h, w = img.shape
    yy, xx = np.mgrid[0:tpx, 0:tpx]
    r = np.hypot(xx - tpx // 2, yy - tpx // 2)
    ang = np.degrees(np.arctan2(yy - tpx // 2, xx - tpx // 2)) % 180
    ring = (r > 4) & (r < tpx * 0.45)
    diag_m = ring & ((np.abs(ang - 45) < 18) | (np.abs(ang - 135) < 18))
    ortho_m = ring & ((ang < 18) | (ang > 162) | (np.abs(ang - 90) < 18))
    win = np.hanning(tpx)[:, None] * np.hanning(tpx)[None, :]
    ink_min = tpx * tpx * _PATTERN_INK_MIN

    tiles: dict[tuple[int, int], str] = {}
    for ti in range(0, h - tpx, tpx):
        for tj in range(0, w - tpx, tpx):
            q = img[ti:ti + tpx, tj:tj + tpx]
            if q.sum() < ink_min:
                continue
            fm = np.abs(np.fft.fftshift(np.fft.fft2((q - q.mean()) * win)))
            diag = float(fm[diag_m].sum())
            ortho = float(fm[ortho_m].sum())
            tiles[(ti // tpx, tj // tpx)] = (
                "coule" if diag > ortho * 1.15
                else "prefab" if ortho > diag * 1.25
                else "mix"
            )
    return tiles, scale, tpx


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
# Envelope-corner detection: simplify tolerance (pt) removes drawing noise, and
# a vertex turning less than this is treated as "straight", not a real corner.
_ENVELOPE_SIMPLIFY_PT = 3.0
_CORNER_MIN_DEG = 20.0


def _slab_metrics(segs, mpp: float):
    """Slab take-off from outline strokes.

    Returns ``(area_m², edge_perimeter_m, n_faces, footprint)`` where
    ``footprint`` is the dissolved shapely geometry (or None).

    The slab layer is drawn as an outline (no fill), so we node the strokes and
    polygonise the planar graph. Summing the faces gives the poured-concrete
    footprint (sub-division lines per zone don't double-count — polygonise
    yields a planar partition). The perimeter of the dissolved footprint is the
    edge formwork (coffrage de rive). Tiny faces are dropped as artefacts.
    """
    if not segs:
        return 0.0, 0.0, 0, None

    def _snap(p):
        return (round(p[0] / _SLAB_SNAP_PT) * _SLAB_SNAP_PT,
                round(p[1] / _SLAB_SNAP_PT) * _SLAB_SNAP_PT)

    lines = [LineString([_snap(a), _snap(b)]) for a, b in segs if _snap(a) != _snap(b)]
    if not lines:
        return 0.0, 0.0, 0, None
    min_face_pt2 = _SLAB_MIN_FACE_M2 / (mpp * mpp)
    faces = [p for p in polygonize(unary_union(lines)) if p.area >= min_face_pt2]
    if not faces:
        return 0.0, 0.0, 0, None
    footprint = unary_union(faces)
    area_m2 = sum(p.area for p in faces) * mpp * mpp
    perimeter_m = footprint.length * mpp
    return float(area_m2), float(perimeter_m), len(faces), footprint


# Room-label categories (regex on the room name word). Used to split slab/floor
# quantities the way the architect asks (e.g. slab under bathrooms, stairwell).
_ROOM_CATEGORIES: list[tuple[str, str]] = [
    ("sdb", r"bain|douche|\bwc\b|sanitaire"),
    ("escalier", r"escalier|treppe|cage"),
    ("reduit", r"r[ée]duit|local|buand|technique|cave"),
    ("sejour", r"salon|s[ée]jour|cuisine|manger"),
    ("chambre", r"chambre|dressing"),
]
# Max distance (PDF points) from a printed area value to its room-name word.
_LABEL_LINK_PT = 70.0


def _room_label_areas(page, mpp: float) -> dict[str, dict[str, float]]:
    """Split the architect's *printed* room areas by category.

    Vector PDFs carry the room labels as text ("Salle de bain" + "4.75 m2").
    We pair every "<number> m²" token with the nearest room-name word and bucket
    it. This yields the per-use slab/floor split (slab under bathrooms, under the
    stairwell, …) straight from the architect's own figures — more reliable than
    polygonising open-plan rooms. ``mpp`` is unused for the values (they are
    already in m²) but kept for signature symmetry / future polygon fallbacks.
    """
    words = page.get_text("words")  # (x0, y0, x1, y1, word, block, line, wno)
    area_tokens: list[tuple[float, float, float]] = []
    for i, w in enumerate(words):
        if re.fullmatch(r"\d{1,3}[.,]\d{2}", w[4]):
            nxt = words[i + 1][4] if i + 1 < len(words) else ""
            if re.fullmatch(r"m[²2]", nxt):
                area_tokens.append(((w[0] + w[2]) / 2, (w[1] + w[3]) / 2,
                                    float(w[4].replace(",", "."))))
    name_pts: list[tuple[float, float, str]] = []
    for w in words:
        low = w[4].lower()
        for cat, pat in _ROOM_CATEGORIES:
            if re.search(pat, low):
                name_pts.append(((w[0] + w[2]) / 2, (w[1] + w[3]) / 2, cat))
                break
    out: dict[str, dict[str, float]] = {}
    for ax, ay, val in area_tokens:
        best, best_d = None, _LABEL_LINK_PT
        for nx, ny, cat in name_pts:
            d = math.hypot(ax - nx, ay - ny)
            if d < best_d:
                best_d, best = d, cat
        if best is None:
            continue
        b = out.setdefault(best, {"count": 0, "net_area_m2": 0.0})
        b["count"] += 1
        b["net_area_m2"] = round(b["net_area_m2"] + val, 2)
    return out


def _envelope_angles(footprint) -> dict[str, Any] | None:
    """Count salient (convex) vs reentrant (concave) corners of the building
    envelope — the outer ring of the slab footprint. These drive corner formwork
    pricing (coffrage d'angle): a salient corner is an outside angle, a reentrant
    one is an inside notch. We walk the simplified ring and classify each vertex
    by the sign of the turn (cross product) relative to the ring orientation.

    Also returns ``points`` (PDF-point coords + kind) so the front-end can draw
    the corner markers on the plan, and ``ring`` (the simplified outline).
    """
    if footprint is None or footprint.is_empty:
        return None
    poly = footprint
    if poly.geom_type == "MultiPolygon":
        poly = max(poly.geoms, key=lambda g: g.area)
    ring = list(poly.simplify(_ENVELOPE_SIMPLIFY_PT).exterior.coords)[:-1]
    n = len(ring)
    if n < 4:
        return None
    signed = sum(ring[i][0] * ring[(i + 1) % n][1] - ring[(i + 1) % n][0] * ring[i][1]
                 for i in range(n))
    ccw = signed > 0
    salient = reentrant = 0
    points: list[dict[str, Any]] = []
    for i in range(n):
        p0, p1, p2 = ring[(i - 1) % n], ring[i], ring[(i + 1) % n]
        e1 = (p1[0] - p0[0], p1[1] - p0[1])
        e2 = (p2[0] - p1[0], p2[1] - p1[1])
        cross = e1[0] * e2[1] - e1[1] * e2[0]
        dot = e1[0] * e2[0] + e1[1] * e2[1]
        if abs(math.degrees(math.atan2(cross, dot))) < _CORNER_MIN_DEG:
            continue  # near-straight: not a real corner
        kind = "salient" if (cross > 0) == ccw else "reentrant"
        if kind == "salient":
            salient += 1
        else:
            reentrant += 1
        points.append({"x": round(p1[0], 2), "y": round(p1[1], 2), "kind": kind})
    return {
        "salient": salient,
        "reentrant": reentrant,
        "total": salient + reentrant,
        "points": points,
        "ring": [[round(x, 2), round(y, 2)] for x, y in ring],
    }


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
    envelope: dict[str, Any] | None = None
    # Geometry for the front-end overlay (all coords in PDF points, same space
    # as room_detection proposals): slab outline, wall centre-lines, corners.
    geo_walls: dict[str, list] = {}
    geo_slab: list[list[float]] = []
    geo_angles: list[dict[str, Any]] = []
    # Material sub-classification of concrete walls, keyed by the architect's
    # colour markers (béton apparent type 4/2, fire compartments EI30, …). The
    # colour→material map is learned from the plan's own legend (generalises).
    material_regions, material_map = _material_regions(page)
    beton_by_material: dict[str, list] = {}
    geo_materials: dict[str, list] = {}
    # Hatch-motif split (poured vs precast) via FFT — the colour-agnostic signal.
    pattern_tiles, p_scale, p_tpx = _beton_hatch_pattern(page)
    beton_by_pattern: dict[str, list] = {}
    geo_patterns: dict[str, list] = {}
    for key, segs in buckets.items():
        if key == "dalle":
            # Slab: area from polygonised outline; "linear" = edge formwork.
            area_m2, perimeter_m, n_faces, footprint = _slab_metrics(segs, mpp)
            elements[key] = {
                "ebkp": ebkp_by_key.get(key, ""),
                "linear_m": round(perimeter_m, 1),
                "surface_m2": round(area_m2, 1),
                "faces": len(segs),
                "measure": "slab_footprint",
            }
            # Building-envelope corner count (formwork) derives from the slab.
            angles = _envelope_angles(footprint)
            if angles:
                envelope = {
                    "area_m2": round(area_m2, 1),
                    "perimeter_m": round(perimeter_m, 1),
                    "salient_angles": angles["salient"],
                    "reentrant_angles": angles["reentrant"],
                }
                geo_slab = angles["ring"]
                geo_angles = angles["points"]
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
        geo_walls[key] = [
            [round(c[0], 2), round(c[1], 2)]
            for m in mids
            for c in (m.coords[0], m.coords[-1])
        ]
        # Sub-classify concrete walls two ways: by material (colour markers /
        # legend) and by hatch motif (FFT — poured vs precast).
        if key in ("beton_porteur", "beton_exterieur"):
            for m in mids:
                seg = [
                    [round(m.coords[0][0], 2), round(m.coords[0][1], 2)],
                    [round(m.coords[-1][0], 2), round(m.coords[-1][1], 2)],
                ]
                if material_regions:
                    mat = _tag_material(m, material_regions) or "Standard (non marqué)"
                    beton_by_material.setdefault(mat, []).append(m)
                    geo_materials.setdefault(mat, []).extend(seg)
                if pattern_tiles:
                    cx, cy = m.interpolate(0.5, normalized=True).coords[0]
                    tile = pattern_tiles.get(
                        (int(cy * p_scale) // p_tpx, int(cx * p_scale) // p_tpx)
                    )
                    plabel = _PATTERN_LABELS.get(tile, "Béton — motif indéterminé")
                    beton_by_pattern.setdefault(plabel, []).append(m)
                    geo_patterns.setdefault(plabel, []).extend(seg)

    # Union per material / per motif so overlapping face-pairs aren't double-counted.
    beton_material_ml = {
        label: round(_ml(mids, mpp), 1) for label, mids in beton_by_material.items()
    }
    beton_pattern_ml = {
        label: round(_ml(mids, mpp), 1) for label, mids in beton_by_pattern.items()
    }

    # Deterministic tabular read (schedules + cartouche): complements the geometry
    # with the architect's own printed tables (door/window/finish lists the vector
    # layers can't see, plus the title block). Non-fatal — a plan with no table
    # returns empty, and a pdfplumber hiccup must not sink the métré.
    try:
        from app.modules.neoffice.plan_schedules import read_plan_schedules

        _tables = read_plan_schedules(pdf_bytes, page_index)
    except Exception:  # noqa: BLE001
        _tables = {"title_block": {}, "schedules": []}

    return {
        "page": page_index,
        "scale_ratio": scale_ratio,
        "metres_per_point": round(mpp, 6),
        "storey_height_m": storey_height_m,
        "storey_height_is_assumption": True,
        "elements": elements,
        "envelope": envelope,
        "beton_by_material": beton_material_ml,
        "beton_by_pattern": beton_pattern_ml,
        "title_block": _tables.get("title_block", {}),
        "schedules": _tables.get("schedules", []),
        "material_legend": {
            "learned": material_map is not _MATERIAL_COLORS_FALLBACK,
            "map": material_map,
        },
        "geometry": {
            "page_width_pt": round(page.rect.width, 2),
            "page_height_pt": round(page.rect.height, 2),
            "slab_outline": geo_slab,
            "walls": geo_walls,
            "materials": geo_materials,
            "patterns": geo_patterns,
            "angles": geo_angles,
        },
        "rooms_by_category": _room_label_areas(page, mpp),
        "todo": [
            "door counts (gap detection — no door/window layer in ArchiCAD export)",
            "window reveals (depends on door/window detection)",
            "crawl-space lining + junction linear metres (needs basement sheet)",
            "slab classification (bathroom/stairwell) via room labels",
            "interior glazing (no glazing layer — needs architect input)",
        ],
    }

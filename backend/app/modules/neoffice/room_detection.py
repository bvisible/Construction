"""NEOFFICE FILE — Owned 100% by Neoservice. Not from upstream OpenConstructionERP.

Vector-geometry room detection for the Takeoff module (Piste B).

Unlike the vision pipeline (plan_vision.py, multimodal LLM → approximate boxes),
this reads the PDF's VECTOR layer and reconstructs room polygons that follow the
real walls — far more precise on CAD plans.

Pipeline (rebuilt 2026-06-09 after a measured spike on a real Protti plan — see
Obsidian note 64 + the metre_pdf spike):
  1. §1b  Isolate real walls by their DOUBLE-LINE signature: keep only dark
          strokes that have a parallel partner at wall-thickness offset. This
          drops furniture, fixtures, hatching and dimension lines cleanly
          (7690 → ~870 segments on Protti), far better than a length/connected-
          component filter (which dropped real walls fragmented by doors).
  2. §1d  TRUE scale from dimension lines (a number like "5.03" m centred on a
          line of known pt length). Independent of room detection — no circular
          calibration. On Protti: exactly 1:50. Falls back to the passed
          scale_ratio when too few dimensions are found.
  3. Rasterise the clean walls → morphological close (seal corner gaps, merge the
     double lines into solid bands) → connected components of the free space =
     wall-aligned room regions → contour each into a simplified polygon.
  4. §1c  Open-plan split: a region holding ≥2 room labels (open kitchen/séjour,
          no dividing wall) is Voronoi-split by its labels into separate
          approximate rooms.
  5. Label by point-in-polygon against the PDF text; m² from the §1d scale.

STATUS: contours follow the walls; rooms with no physical separation (open plan)
or no enclosure (balconies) stay approximate — the user adjusts them with the
in-canvas measurement editor. This is a clear precision jump over the vision boxes.
Measured ceiling of pure geometry is low ONLY because some rooms have no wall to
detect (cf. note 64) — not a code defect.

Kept in oe_neoffice (Neoservice custom) — no core patch. Uses cv2/shapely/pymupdf.
"""

from __future__ import annotations

import math
import re
from typing import Any

import cv2
import numpy as np
import pymupdf
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import split as shp_split
from shapely.strtree import STRtree

# ── Wall layer ───────────────────────────────────────────────────────────
WALL_COLOR_HEX = "#000000"       # dominant wall stroke on Protti plans

# ── Double-line wall detection (§1b) ─────────────────────────────────────
WALL_OFFSET_MIN_PT = 2.5         # min gap between the two wall lines (~0.04 m)
WALL_OFFSET_MAX_PT = 16.0        # max wall thickness (~0.28 m @1:50)
WALL_PARALLEL_DEG = 8.0          # max angle between paired wall lines
WALL_MIN_SEG_PT = 3.0            # ignore micro-segments
WALL_MIN_OVERLAP_PT = 8.0        # paired lines must run alongside this far

# ── Dimension-line scale (§1d) ───────────────────────────────────────────
DIM_RE = re.compile(r"^(\d{1,2})[.,](\d{2})$")
SCALE_MIN_MPP, SCALE_MAX_MPP = 0.010, 0.030   # plausible m/pt window
DIM_PERP_TOL_PT = 18.0
DIM_PROJ_MIN, DIM_PROJ_MAX = 0.15, 0.85
DIM_MIN_VOTES = 8
M_PER_PT_AT_72 = 0.0254 / 72.0                # paper metres per point

# ── Raster room extraction ───────────────────────────────────────────────
RENDER_DPI = 150
WALL_CLOSE_PT = 8.0              # seal corner gaps + merge double lines
MIN_ROOM_M2 = 2.5               # drop noise fragments / wall pockets
MAX_ROOM_M2 = 90.0              # drop the building envelope / frame

ROOM_KEYWORDS = re.compile(
    r"chambre|cuisine|s[ée]jour|sdb|salle|bain|hall|d[ée]gag|wc|balcon|entr[ée]e|"
    r"bureau|local|cave|terrasse|buand|r[ée]duit|dressing|garage|atelier|gaine|"
    r"couloir|palier|office|cellier|loggia|douche",
    re.I,
)


def _hex(color: Any) -> str | None:
    if not color:
        return None
    try:
        return "#%02x%02x%02x" % tuple(int(round(x * 255)) for x in color)
    except (TypeError, ValueError):
        return None


def _black_segments(page: "pymupdf.Page") -> list[tuple[tuple[float, float], tuple[float, float]]]:
    out = []
    for d in page.get_drawings():
        if _hex(d.get("color")) != WALL_COLOR_HEX:
            continue
        for it in d.get("items", []):
            if it[0] == "l":
                a, b = it[1], it[2]
                out.append(((a.x, a.y), (b.x, b.y)))
    return out


# ── §1b — double-line wall filter ────────────────────────────────────────

def _dir(s):
    (ax, ay), (bx, by) = s
    dx, dy = bx - ax, by - ay
    n = math.hypot(dx, dy)
    return (dx / n, dy / n) if n else (0.0, 0.0), n


def _parallel(d1, d2, tol_deg):
    dot = min(1.0, abs(d1[0] * d2[0] + d1[1] * d2[1]))
    return math.degrees(math.acos(dot)) <= tol_deg


def _perp_offset(s1, s2):
    (ax, ay), (bx, by) = s1
    mx, my = (s2[0][0] + s2[1][0]) / 2, (s2[0][1] + s2[1][1]) / 2
    dx, dy = bx - ax, by - ay
    n = math.hypot(dx, dy)
    return 1e9 if n == 0 else abs((mx - ax) * dy - (my - ay) * dx) / n


def _overlap(s1, s2, d1):
    ax, ay = s1[0]

    def proj(p):
        return (p[0] - ax) * d1[0] + (p[1] - ay) * d1[1]

    a0, a1 = sorted([proj(s1[0]), proj(s1[1])])
    b0, b1 = sorted([proj(s2[0]), proj(s2[1])])
    return max(0.0, min(a1, b1) - max(a0, b0))


def _double_line_walls(segments):
    """Keep segments that have a parallel partner at wall-thickness offset."""
    if not segments:
        return []
    geoms = [LineString(s) for s in segments]
    dirs = [_dir(s) for s in segments]
    tree = STRtree(geoms)
    keep = [False] * len(segments)
    for i, s1 in enumerate(segments):
        if dirs[i][1] < WALL_MIN_SEG_PT:
            continue
        d1 = dirs[i][0]
        for j in tree.query(geoms[i].buffer(WALL_OFFSET_MAX_PT + 2)):
            j = int(j)
            if j == i or dirs[j][1] < WALL_MIN_SEG_PT:
                continue
            if not _parallel(d1, dirs[j][0], WALL_PARALLEL_DEG):
                continue
            if not (WALL_OFFSET_MIN_PT <= _perp_offset(s1, segments[j]) <= WALL_OFFSET_MAX_PT):
                continue
            if _overlap(s1, segments[j], d1) < WALL_MIN_OVERLAP_PT:
                continue
            keep[i] = True
            break
    return [s for s, k in zip(segments, keep) if k]


# ── §1d — scale from dimension lines ─────────────────────────────────────

def _dimension_scale_m_per_pt(page: "pymupdf.Page") -> float | None:
    segs = [
        ((it[1].x, it[1].y), (it[2].x, it[2].y))
        for d in page.get_drawings() for it in d.get("items", []) if it[0] == "l"
    ]
    if not segs:
        return None
    # Spatial index so each dimension number only tests the few lines passing
    # near it (the O(N²) scan over ~30k segments was the latency bottleneck).
    geoms = [LineString(s) for s in segs]
    tree = STRtree(geoms)
    pad = DIM_PERP_TOL_PT + 4.0
    votes = []
    for x0, y0, x1, y1, w, *_ in page.get_text("words"):
        m = DIM_RE.match(w.strip())
        if not m:
            continue
        v = float(w.strip().replace(",", "."))
        if not (0.30 <= v <= 30.0):
            continue
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        best_len = 0.0
        for j in tree.query(box(cx - pad, cy - pad, cx + pad, cy + pad)):
            (ax, ay), (bx, by) = segs[int(j)]
            dx, dy = bx - ax, by - ay
            l2 = dx * dx + dy * dy
            if l2 == 0:
                continue
            length = math.sqrt(l2)
            if not (v / SCALE_MAX_MPP <= length <= v / SCALE_MIN_MPP):
                continue
            t = ((cx - ax) * dx + (cy - ay) * dy) / l2
            perp = abs((cx - ax) * dy - (cy - ay) * dx) / length
            if perp < DIM_PERP_TOL_PT and DIM_PROJ_MIN < t < DIM_PROJ_MAX and length > best_len:
                best_len = length
        if best_len:
            votes.append(v / best_len)
    if len(votes) < DIM_MIN_VOTES:
        return None
    return float(np.median(votes))


# ── Raster room regions ──────────────────────────────────────────────────

def _wall_regions(page, walls, conv) -> list[Polygon]:
    pw, ph = page.rect.width, page.rect.height
    s = RENDER_DPI / 72.0
    W, H = int(round(pw * s)), int(round(ph * s))
    img = np.zeros((H, W), np.uint8)
    for (a, b) in walls:
        cv2.line(img, (int(a[0] * s), int(a[1] * s)), (int(b[0] * s), int(b[1] * s)), 255, 2)
    k = max(3, int(round(WALL_CLOSE_PT * s)))
    closed = cv2.morphologyEx(img, cv2.MORPH_CLOSE,
                              cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    free = cv2.bitwise_not(closed)
    n, lab = cv2.connectedComponents(free, connectivity=4)
    border = set(lab[0, :]) | set(lab[-1, :]) | set(lab[:, 0]) | set(lab[:, -1])
    min_px = (MIN_ROOM_M2 / conv) * (s * s)
    polys = []
    for lid in range(1, n):
        if lid in border:
            continue
        mask = (lab == lid).astype(np.uint8)
        if int(mask.sum()) < min_px:
            continue
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cnts:
            continue
        c = max(cnts, key=cv2.contourArea)
        c = cv2.approxPolyDP(c, 0.008 * cv2.arcLength(c, True), True)
        pts = [(float(p[0][0]) / s, float(p[0][1]) / s) for p in c]
        if len(pts) >= 3:
            poly = Polygon(pts)
            if poly.is_valid and not poly.is_empty and poly.area * conv <= MAX_ROOM_M2:
                polys.append(poly)
    return polys


_SURFACE_RE = re.compile(r"Surface[:\s]*(\d+[.,]\d+|\d+)\s*m", re.I)


def _room_labels(page: "pymupdf.Page") -> list[tuple[str, float, float, float | None]]:
    """Room labels with their declared surface (m²) when printed nearby.

    ArchiCAD prints the room name and 'Surface: X m²' as separate text blocks in
    the same column; pair each name with the nearest surface block just below it.
    The declared surface is used as weak supervision to place open-plan cuts so
    the split areas match the architect's figures (area correct by construction).
    """
    names: list[tuple[str, float, float]] = []
    surfs: list[tuple[float, float, float]] = []
    for x0, y0, x1, y1, text, *_ in page.get_text("blocks"):
        t = (text or "").strip()
        if not t:
            continue
        first = t.split("\n")[0].strip()
        low = first.lower()
        if "surface" not in low and not low.startswith("sol") and ROOM_KEYWORDS.search(first):
            names.append((first, (x0 + x1) / 2, (y0 + y1) / 2))
        m = _SURFACE_RE.search(t)
        if m:
            surfs.append(((x0 + x1) / 2, (y0 + y1) / 2, float(m.group(1).replace(",", "."))))
    out: list[tuple[str, float, float, float | None]] = []
    for name, cx, cy in names:
        best, best_dy = None, 1e9
        for sx, sy, val in surfs:
            dy = sy - cy
            if abs(sx - cx) < 45 and 0 < dy < 45 and dy < best_dy:
                best, best_dy = val, dy
        out.append((name, cx, cy, best))
    return out


# ── Open-plan straight cut (hybrid deterministic half, area-weighted) ─────

def _area_left(poly: Polygon, axis: str, c: float) -> float:
    minx, miny, maxx, maxy = poly.bounds
    clip = box(minx - 1, miny - 1, c, maxy + 1) if axis == "x" \
        else box(minx - 1, miny - 1, maxx + 1, c)
    return poly.intersection(clip).area


def _weighted_pos(poly: Polygon, axis: str, frac_left: float, iters: int = 34) -> float:
    minx, miny, maxx, maxy = poly.bounds
    lo, hi = (minx, maxx) if axis == "x" else (miny, maxy)
    target = frac_left * poly.area
    for _ in range(iters):
        mid = (lo + hi) / 2
        if _area_left(poly, axis, mid) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _split_region(poly, idxs, pts, declared, min_part):
    """Split an open-plan region among its room anchors with STRAIGHT axis-aligned
    cuts, positioned by the declared surfaces when known. Recurses for 3+ rooms."""
    if len(idxs) <= 1:
        return [(poly, idxs[0])] if idxs else []
    xs = [pts[i].x for i in idxs]
    ys = [pts[i].y for i in idxs]
    axis = "x" if (max(xs) - min(xs)) >= (max(ys) - min(ys)) else "y"
    key = (lambda i: pts[i].x) if axis == "x" else (lambda i: pts[i].y)
    order = sorted(idxs, key=key)
    _, kbest = max((key(order[k + 1]) - key(order[k]), k) for k in range(len(order) - 1))
    left, right = order[: kbest + 1], order[kbest + 1:]
    da = sum(declared[i] or 0 for i in left)
    db = sum(declared[i] or 0 for i in right)
    if da > 0 and db > 0:
        c = _weighted_pos(poly, axis, da / (da + db))
        c = min(max(c, key(order[kbest])), key(order[kbest + 1]))
    else:
        c = (key(order[kbest]) + key(order[kbest + 1])) / 2
    minx, miny, maxx, maxy = poly.bounds
    cutter = LineString([(c, miny - 1), (c, maxy + 1)]) if axis == "x" \
        else LineString([(minx - 1, c), (maxx + 1, c)])
    try:
        pieces = [pg for pg in shp_split(poly, cutter).geoms
                  if pg.geom_type == "Polygon" and not pg.is_empty]
    except Exception:
        return [(poly, idxs[0])]
    if len(pieces) < 2:
        return [(poly, min(idxs, key=lambda i: pts[i].distance(poly.representative_point())))]
    out = []
    for pg in pieces:
        if pg.area < min_part:
            continue
        contained = [i for i in idxs if pg.contains(pts[i])]
        if len(contained) >= 2:
            out += _split_region(pg, contained, pts, declared, min_part)
        elif len(contained) == 1:
            out.append((pg, contained[0]))
        else:
            out.append((pg, min(idxs, key=lambda i: pts[i].distance(pg.representative_point()))))
    return out


def _iter_polys(geom):
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom]
    if geom.geom_type in ("MultiPolygon", "GeometryCollection"):
        return [g for g in geom.geoms if g.geom_type == "Polygon" and not g.is_empty]
    return []


def page_has_vectors(pdf_bytes: bytes, page_index: int, min_drawings: int = 20) -> bool:
    """True if the page carries a usable vector layer (CAD export), False for a
    raster/scan PDF (image only).

    Lets the detect-rooms endpoint route a vector plan to the geometry pathway
    and an image/scan plan to the vision pathway. The threshold avoids treating
    a few incidental vector marks (logo, frame) as a real CAD drawing.
    """
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    with doc:
        if page_index < 0 or page_index >= doc.page_count:
            return False
        return len(doc[page_index].get_drawings()) >= min_drawings


def detect_rooms(
    pdf_bytes: bytes,
    page_index: int,
    scale_ratio: float | None,
) -> dict[str, Any]:
    """Detect room polygons from the PDF vector layer.

    Returns a dict with page dims (PDF points), the rooms (polygon normalised to
    [0,1] of the page so the frontend can place them in any render frame), and
    coverage stats. Raises ``IndexError`` if the page is out of range.
    """
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    with doc:
        if page_index < 0 or page_index >= doc.page_count:
            raise IndexError(f"Page {page_index} out of range")
        page = doc[page_index]
        pw, ph = page.rect.width, page.rect.height

        # §1d — true scale (dimension lines), else the frontend's scale_ratio.
        mpp = _dimension_scale_m_per_pt(page)
        scale_src = "dimensions"
        if mpp is None:
            scale_src = "fallback"
            mpp = (M_PER_PT_AT_72 * scale_ratio) if scale_ratio else M_PER_PT_AT_72 * 50.0
        conv = mpp * mpp                                   # m² per pt²
        implied_ratio = round(mpp / M_PER_PT_AT_72, 1)

        segments = _black_segments(page)
        walls = _double_line_walls(segments)
        regions = _wall_regions(page, walls, conv) if walls else []
        labels = _room_labels(page)
        pts = [Point(cx, cy) for _n, cx, cy, _d in labels]
        declared = [d for _n, _cx, _cy, d in labels]
        min_part_pt2 = MIN_ROOM_M2 / conv if conv else 0.0

        rooms_out: list[dict[str, Any]] = []

        def emit(poly: Polygon, name: str | None) -> None:
            rooms_out.append({
                "name": name,
                "polygon": [[round(x / pw, 5), round(y / ph, 5)] for x, y in poly.exterior.coords],
                "area_m2": round(poly.area * conv, 2),
            })

        for poly in regions:
            inside = [i for i, p in enumerate(pts) if poly.contains(p)]
            if len(inside) <= 1:
                emit(poly, labels[inside[0]][0] if inside else None)
                continue
            # §1c — split an open-plan region by STRAIGHT virtual walls, positioned
            # by the declared surfaces when known (area correct by construction).
            # Each cut edge is editable; later the ML places this line (note 65).
            for pg, owner in _split_region(poly, inside, pts, declared, min_part_pt2):
                emit(pg, labels[owner][0])

        return {
            "page_width_pt": round(pw, 2),
            "page_height_pt": round(ph, 2),
            "scale_ratio": implied_ratio,
            "scale_pixels_per_unit": round(1.0 / mpp, 4) if mpp else None,  # pt per metre
            "rooms": rooms_out,
            "stats": {
                "wall_segments": len(walls),
                "regions": len(regions),
                "rooms": len(rooms_out),
                "scale_source": scale_src,
            },
        }

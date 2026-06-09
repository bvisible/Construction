"""NEOFFICE FILE — Owned 100% by Neoservice. Not from upstream OpenConstructionERP.

Vector-geometry room detection for the Takeoff module (Piste B).

Unlike the vision pipeline (plan_vision.py, multimodal LLM → approximate boxes),
this reads the PDF's VECTOR layer and reconstructs room polygons that follow the
real walls — far more precise on CAD plans.

Pipeline (validated 2026-06-08 on a real Protti plan, see Obsidian note 61):
  1. Extract long wall segments from the dark stroke layer (#000000).
  2. Keep only segments inside the building envelope (drops dimension axes that
     shoot out of the plan).
  3. Node the network (shapely unary_union) — inserts intersections + dedups.
  4. Close doorways: join dangling (degree-1) wall endpoints that are colinear
     and separated by a door-width gap.
  5. Polygonize → room polygons; filter by area to drop micro-polygons + frame.
  6. Label each room by point-in-polygon against the PDF text labels.
  7. Compute m² from the drawing scale.

STATUS: geometric PRE-DETECTION — contours follow the walls, but some rooms may
merge (un-closed door) or be missing (wall on another layer). The user adjusts.
The door-arc sealing + hatch-mass refinements are tracked for the next sprint.

Kept in oe_neoffice (Neoservice custom) — no core patch. Reuses shapely/pymupdf.
"""

from __future__ import annotations

import collections
import math
import re
from typing import Any

import pymupdf
from shapely.geometry import LineString, MultiLineString, Point
from shapely.ops import polygonize, unary_union

# Wall stroke colour. #000000 (black) on the Protti plans; auto-calibration across
# conventions is a later sprint item — for now this is the dominant wall layer.
WALL_COLOR_HEX = "#000000"
MIN_WALL_SEG_PT = 25.0          # keep long strokes (walls), drop short (furniture/text/dims)
SNAP_PT = 1.5                   # snap-rounding grid to repair connectivity
ENVELOPE_PCT = (2, 98)          # percentile bbox → drops axes shooting out of the plan
DOOR_GAP_MIN_PT, DOOR_GAP_MAX_PT = 36.0, 62.0  # door width @1:50 ≈ 0.6–1.1 m
DOOR_COLINEAR_MAX_DEG = 18.0    # closure only between colinear dangling ends (real doors)
MIN_ROOM_M2, MAX_ROOM_M2 = 2.0, 70.0

ROOM_KEYWORDS = re.compile(
    r"chambre|cuisine|s[ée]jour|sdb|salle|bain|hall|d[ée]gag|wc|balcon|entr[ée]e|"
    r"bureau|local|cave|terrasse|buand|r[ée]duit|dressing|garage|atelier",
    re.I,
)


def _hex(color: Any) -> str | None:
    if not color:
        return None
    try:
        return "#%02x%02x%02x" % tuple(int(round(x * 255)) for x in color)
    except (TypeError, ValueError):
        return None


def _snap(v: float) -> float:
    return round(v / SNAP_PT) * SNAP_PT


def _angle(u: tuple[float, float], v: tuple[float, float]) -> float:
    du, dv = math.hypot(*u), math.hypot(*v)
    if du == 0 or dv == 0:
        return 180.0
    cs = max(-1.0, min(1.0, (u[0] * v[0] + u[1] * v[1]) / (du * dv)))
    return math.degrees(math.acos(cs))


def _wall_lines(page: "pymupdf.Page") -> list[LineString]:
    """Long dark strokes, snapped, kept within the building envelope."""
    import numpy as np

    raw: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for d in page.get_drawings():
        if _hex(d.get("color")) != WALL_COLOR_HEX:
            continue
        for it in d.get("items", []):
            if it[0] == "l":
                a, b = it[1], it[2]
                if math.hypot(b.x - a.x, b.y - a.y) >= MIN_WALL_SEG_PT:
                    pa, pb = (_snap(a.x), _snap(a.y)), (_snap(b.x), _snap(b.y))
                    if pa != pb:
                        raw.append((pa, pb))
    if not raw:
        return []
    xs = [c[0] for s in raw for c in s]
    ys = [c[1] for s in raw for c in s]
    x1, x2 = np.percentile(xs, ENVELOPE_PCT)
    y1, y2 = np.percentile(ys, ENVELOPE_PCT)

    def inside(pt: tuple[float, float]) -> bool:
        return x1 - 8 <= pt[0] <= x2 + 8 and y1 - 8 <= pt[1] <= y2 + 8

    return [LineString([a, b]) for a, b in raw if inside(a) and inside(b)]


def _door_closures(lines: list[LineString]) -> list[LineString]:
    """Join colinear dangling (degree-1) endpoints separated by a door-width gap."""
    deg: collections.Counter = collections.Counter()
    incoming: dict[tuple[float, float], list[tuple[float, float]]] = {}
    for ln in lines:
        c = list(ln.coords)
        for end, nb in ((c[0], c[1]), (c[-1], c[-2])):
            deg[end] += 1
            incoming.setdefault(end, []).append((end[0] - nb[0], end[1] - nb[1]))
    ends = [pt for pt, d in deg.items() if d == 1]
    closures: list[LineString] = []
    used: set[int] = set()
    for i in range(len(ends)):
        if i in used:
            continue
        pi, di = ends[i], incoming[ends[i]][0]
        best, best_d = -1, 1e9
        for j in range(len(ends)):
            if j == i or j in used:
                continue
            pj = ends[j]
            dist = math.hypot(pi[0] - pj[0], pi[1] - pj[1])
            if not (DOOR_GAP_MIN_PT <= dist <= DOOR_GAP_MAX_PT):
                continue
            sd = (pj[0] - pi[0], pj[1] - pi[1])
            a1, a2 = _angle(di, sd), _angle(incoming[pj][0], sd)
            if min(a1, 180 - a1) > DOOR_COLINEAR_MAX_DEG or min(a2, 180 - a2) > DOOR_COLINEAR_MAX_DEG:
                continue
            if dist < best_d:
                best_d, best = dist, j
        if best >= 0:
            closures.append(LineString([pi, ends[best]]))
            used.add(i)
            used.add(best)
    return closures


def _room_label_points(page: "pymupdf.Page") -> list[tuple[str, float, float]]:
    out: list[tuple[str, float, float]] = []
    for w in page.get_text("words"):
        text = w[4].strip()
        if text and ROOM_KEYWORDS.search(text):
            out.append((text, (w[0] + w[2]) / 2, (w[1] + w[3]) / 2))
    return out


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

        lines = _wall_lines(page)
        rooms_out: list[dict[str, Any]] = []
        total = 0
        if lines:
            closures = _door_closures(lines)
            merged = unary_union(lines + closures)
            polys = list(polygonize(merged))
            ppu = 72.0 / (0.0254 * scale_ratio) if scale_ratio else None  # PDF pt per metre
            labels = _room_label_points(page)
            for poly in polys:
                total += 1
                area_m2 = poly.area / (ppu * ppu) if ppu else None
                if area_m2 is None or not (MIN_ROOM_M2 <= area_m2 <= MAX_ROOM_M2):
                    continue
                name = next(
                    (t for t, cx, cy in labels if poly.contains(Point(cx, cy))), None
                )
                # exterior ring → normalised [0,1] polygon
                poly_norm = [
                    [round(x / pw, 4), round(y / ph, 4)] for x, y in poly.exterior.coords
                ]
                rooms_out.append(
                    {
                        "name": name,
                        "polygon": poly_norm,
                        "area_m2": round(area_m2, 2),
                    }
                )

        return {
            "page_width_pt": round(pw, 2),
            "page_height_pt": round(ph, 2),
            "scale_ratio": scale_ratio,
            "scale_pixels_per_unit": (72.0 / (0.0254 * scale_ratio)) if scale_ratio else None,
            "rooms": rooms_out,
            "stats": {"raw_polygons": total, "rooms": len(rooms_out)},
        }

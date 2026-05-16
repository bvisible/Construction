"""NEOFFICE FILE — Owned 100% by Neoservice. Not from upstream OpenConstructionERP.

Pure-function importer that maps an Apple RoomPlan CapturedRoom JSON to a
list of BIMElement payloads ready for bulk insert into oe_bim_element.

RoomPlan coordinate system
--------------------------
Right-handed, +Y up, units in metres. Each Surface/Object carries:
- ``dimensions`` (SIMD3<Float>) — width (x), height (y), depth (z), all in m.
- ``transform`` (simd_float4x4) — column-major 4x4 matrix. Translation lives
  in the 4th column rows 0..2 (transform[12], [13], [14] in flat list form).
  RoomPlan exports the matrix as a 16-element flat list.
- ``confidence`` — "high" | "medium" | "low".
- ``category`` (object/wall) — string enum from Apple (e.g. "wall", "door",
  "sofa", "table", "bed").

Output BIMElement shape
-----------------------
Aligns with ``BIMElement`` ORM (bim_hub.models). Each element has:
- ``stable_id``: ``"<type>:<uuid>"`` (deterministic, idempotent on re-import)
- ``element_type``: IFC class string (``IfcWall``, ``IfcDoor``, ``IfcWindow``,
  ``IfcOpeningElement``, ``IfcFurnishingElement``)
- ``quantities``: canonical keys (Length, Width, Height, Area, Volume) so the
  existing frontend element panel renders them with no changes.
- ``properties``: full RoomPlan-specific data preserved under
  ``roomplan_*`` keys (confidence, parent_identifier, surface attributes).
- ``bounding_box``: world-space AABB computed from transform × ±dim/2.
"""

from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)


# ── Apple RoomPlan category → IFC class mapping ────────────────────────────

_SURFACE_IFC_MAP: dict[str, str] = {
    "wall": "IfcWall",
    "door": "IfcDoor",
    "window": "IfcWindow",
    "opening": "IfcOpeningElement",
    "floor": "IfcSlab",
    "ceiling": "IfcCovering",
}

# Apple objects categories — extend as RoomPlan evolves.
# All map to IfcFurnishingElement; the original category is preserved in
# properties["roomplan_category"] for downstream filtering.
_OBJECT_CATEGORIES: set[str] = {
    "storage", "refrigerator", "stove", "bed", "sink", "washerDryer",
    "toilet", "bathtub", "oven", "dishwasher", "table", "sofa", "chair",
    "fireplace", "television", "stairs",
}


# ── Public API ─────────────────────────────────────────────────────────────


def parse_roomplan_scan(scan: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Parse a CapturedRoom JSON into BIMElement payloads + global metadata.

    Returns ``(elements, meta)`` where:
        elements: list of dicts ready to be passed to ``BIMElement(**d)``
                  (model_id is added by the caller).
        meta: ``{"bounding_box": {...}, "storey_count": int, "element_count": int}``

    The function is pure (no DB access) and idempotent — re-running it on the
    same JSON yields the same stable_ids.
    """
    elements: list[dict[str, Any]] = []

    # RoomPlan exports the room as either a single CapturedRoom object or a
    # CapturedStructure containing multiple rooms. Normalize to a list of rooms.
    rooms = _extract_rooms(scan)

    for room_idx, room in enumerate(rooms):
        storey_label = _storey_label_for_room(room, room_idx)
        for surface_kind in ("walls", "doors", "windows", "openings", "floors"):
            for surface in room.get(surface_kind, []) or []:
                el = _surface_to_element(surface, surface_kind, storey_label)
                if el is not None:
                    elements.append(el)

        for obj in room.get("objects", []) or []:
            el = _object_to_element(obj, storey_label)
            if el is not None:
                elements.append(el)

    bbox = _global_bounding_box(elements)
    meta = {
        "bounding_box": bbox,
        "storey_count": max(len(rooms), 1),
        "element_count": len(elements),
    }
    return elements, meta


# ── Internal helpers ───────────────────────────────────────────────────────


def _extract_rooms(scan: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a list of room-like dicts to iterate over.

    Handles three known top-level shapes:
    1. Bare CapturedRoom — has top-level "walls"/"doors"/...
    2. CapturedStructure — has "rooms": [...]
    3. Wrapper exported by the iOS app — has "capturedRoom": {...}
    """
    if isinstance(scan.get("rooms"), list):
        return [r for r in scan["rooms"] if isinstance(r, dict)]
    if isinstance(scan.get("capturedRoom"), dict):
        return [scan["capturedRoom"]]
    if any(k in scan for k in ("walls", "doors", "windows", "openings", "objects")):
        return [scan]
    logger.warning("RoomPlan scan has unrecognized shape (top-level keys: %s)", list(scan.keys()))
    return []


def _storey_label_for_room(room: dict[str, Any], idx: int) -> str:
    story = room.get("story") or room.get("storyName") or room.get("name")
    if isinstance(story, str) and story.strip():
        return story.strip()[:255]
    return f"Level {idx}"


def _surface_to_element(
    surface: dict[str, Any],
    surface_kind: str,
    storey: str,
) -> dict[str, Any] | None:
    """Map a RoomPlan Surface (wall/door/window/opening/floor) to a BIMElement payload."""
    category = surface.get("category") or surface_kind.rstrip("s")  # "walls" → "wall"
    ifc_type = _SURFACE_IFC_MAP.get(category) or _SURFACE_IFC_MAP.get(surface_kind.rstrip("s"))
    if ifc_type is None:
        logger.debug("Skipping unknown surface category: %s", category)
        return None

    identifier = surface.get("identifier") or surface.get("uuid")
    if not identifier:
        logger.debug("Skipping surface with no identifier (category=%s)", category)
        return None

    dims = _read_dimensions(surface)
    transform = _read_transform(surface)
    bbox = _bounding_box_from(transform, dims)

    quantities = _quantities_for_surface(dims, ifc_type)
    properties = {
        "roomplan_category": category,
        "roomplan_confidence": surface.get("confidence"),
        "roomplan_surface_kind": surface_kind,
    }
    parent_id = surface.get("parentIdentifier") or surface.get("parent_identifier")
    if parent_id:
        properties["roomplan_parent_id"] = parent_id
    attrs = surface.get("attributes")
    if isinstance(attrs, dict) and attrs:
        properties["roomplan_attributes"] = attrs
    polygon = surface.get("polygonCorners") or surface.get("polygon_corners")
    if isinstance(polygon, list) and polygon:
        properties["roomplan_polygon_corners"] = polygon

    return {
        "stable_id": f"{ifc_type.lower()}:{identifier}",
        "element_type": ifc_type,
        "name": _humanize(category),
        "storey": storey,
        "discipline": "architecture",
        "properties": properties,
        "quantities": quantities,
        "bounding_box": bbox,
    }


def _object_to_element(obj: dict[str, Any], storey: str) -> dict[str, Any] | None:
    """Map a RoomPlan Object (furniture, appliance) to a BIMElement payload."""
    category = obj.get("category")
    identifier = obj.get("identifier") or obj.get("uuid")
    if not identifier:
        return None

    dims = _read_dimensions(obj)
    transform = _read_transform(obj)
    bbox = _bounding_box_from(transform, dims)
    quantities = {
        "Width": _round(dims[0]),
        "Height": _round(dims[1]),
        "Depth": _round(dims[2]),
        "Volume": _round(dims[0] * dims[1] * dims[2]),
    }
    properties = {
        "roomplan_category": category,
        "roomplan_confidence": obj.get("confidence"),
        "roomplan_surface_kind": "object",
    }
    return {
        "stable_id": f"ifcfurnishingelement:{identifier}",
        "element_type": "IfcFurnishingElement",
        "name": _humanize(category) if category else "Object",
        "storey": storey,
        "discipline": "architecture",
        "properties": properties,
        "quantities": quantities,
        "bounding_box": bbox,
    }


def _read_dimensions(item: dict[str, Any]) -> tuple[float, float, float]:
    """Read a SIMD3<Float> dimensions field. Returns (x, y, z) in metres."""
    dims = item.get("dimensions")
    if isinstance(dims, list) and len(dims) >= 3:
        return _f(dims[0]), _f(dims[1]), _f(dims[2])
    if isinstance(dims, dict):
        return _f(dims.get("x", 0)), _f(dims.get("y", 0)), _f(dims.get("z", 0))
    return 0.0, 0.0, 0.0


def _read_transform(item: dict[str, Any]) -> list[float]:
    """Read a simd_float4x4 transform. Returns 16-float flat list (column-major).

    Falls back to identity matrix when missing/malformed so the downstream
    bounding-box math still produces a sane (origin-anchored) AABB.
    """
    raw = item.get("transform")
    if isinstance(raw, list):
        flat = _flatten(raw)
        if len(flat) >= 16:
            return [_f(v) for v in flat[:16]]
    if isinstance(raw, dict):
        # Sometimes serialized as {columns: [[…], [...], [...], [...]]}
        cols = raw.get("columns")
        if isinstance(cols, list):
            flat = _flatten(cols)
            if len(flat) >= 16:
                return [_f(v) for v in flat[:16]]
    return [
        1.0, 0.0, 0.0, 0.0,
        0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, 1.0, 0.0,
        0.0, 0.0, 0.0, 1.0,
    ]


def _bounding_box_from(transform: list[float], dims: tuple[float, float, float]) -> dict[str, list[float]]:
    """Compute world-space AABB by transforming the 8 corners of the local box.

    transform is column-major:
        | m0  m4  m8  m12 |
        | m1  m5  m9  m13 |
        | m2  m6  m10 m14 |
        | m3  m7  m11 m15 |
    """
    hx, hy, hz = dims[0] / 2, dims[1] / 2, dims[2] / 2
    corners = [
        (-hx, -hy, -hz), (+hx, -hy, -hz),
        (-hx, +hy, -hz), (+hx, +hy, -hz),
        (-hx, -hy, +hz), (+hx, -hy, +hz),
        (-hx, +hy, +hz), (+hx, +hy, +hz),
    ]
    m = transform
    xs, ys, zs = [], [], []
    for (lx, ly, lz) in corners:
        wx = m[0] * lx + m[4] * ly + m[8] * lz + m[12]
        wy = m[1] * lx + m[5] * ly + m[9] * lz + m[13]
        wz = m[2] * lx + m[6] * ly + m[10] * lz + m[14]
        xs.append(wx); ys.append(wy); zs.append(wz)
    return {
        "min": [_round(min(xs)), _round(min(ys)), _round(min(zs))],
        "max": [_round(max(xs)), _round(max(ys)), _round(max(zs))],
    }


def _quantities_for_surface(dims: tuple[float, float, float], ifc_type: str) -> dict[str, float]:
    """Canonical quantity keys per IFC type (aligns with what ifc_processor emits)."""
    w, h, d = dims
    qty: dict[str, float] = {
        "Width": _round(w),
        "Height": _round(h),
        "Length": _round(w),
        "Thickness": _round(d),
    }
    if ifc_type in {"IfcWall", "IfcSlab", "IfcCovering"}:
        qty["Area"] = _round(w * h)
        qty["Volume"] = _round(w * h * d)
    if ifc_type in {"IfcDoor", "IfcWindow", "IfcOpeningElement"}:
        qty["Area"] = _round(w * h)
    return qty


def _global_bounding_box(elements: list[dict[str, Any]]) -> dict[str, list[float]] | None:
    xs, ys, zs = [], [], []
    for el in elements:
        bb = el.get("bounding_box")
        if not isinstance(bb, dict):
            continue
        mn, mx = bb.get("min"), bb.get("max")
        if isinstance(mn, list) and len(mn) >= 3:
            xs.append(mn[0]); ys.append(mn[1]); zs.append(mn[2])
        if isinstance(mx, list) and len(mx) >= 3:
            xs.append(mx[0]); ys.append(mx[1]); zs.append(mx[2])
    if not xs:
        return None
    return {
        "min": [_round(min(xs)), _round(min(ys)), _round(min(zs))],
        "max": [_round(max(xs)), _round(max(ys)), _round(max(zs))],
    }


# ── Tiny utils ─────────────────────────────────────────────────────────────


def _f(v: Any) -> float:
    try:
        f = float(v)
        return f if math.isfinite(f) else 0.0
    except (TypeError, ValueError):
        return 0.0


def _round(v: float) -> float:
    return round(_f(v), 4)


def _flatten(seq: Any) -> list[Any]:
    out: list[Any] = []
    if isinstance(seq, list):
        for item in seq:
            if isinstance(item, list):
                out.extend(_flatten(item))
            else:
                out.append(item)
    return out


def _humanize(s: str | None) -> str:
    if not s:
        return ""
    return s[:1].upper() + s[1:]

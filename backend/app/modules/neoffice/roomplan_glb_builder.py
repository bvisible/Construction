"""NEOFFICE FILE — Owned 100% by Neoservice. Not from upstream OpenConstructionERP.

Build a binary glTF 2.0 (GLB) mesh scene from an Apple RoomPlan
CapturedRoom JSON. The GLB is meant to be served as the
``canonical_file_path`` of the BIMModel so the Three.js viewer renders
the room in 3D (walls as boxes, floor as extruded polygon, openings
as semi-transparent panes, furniture as bbox boxes).

Coordinate system
-----------------
RoomPlan: right-handed, +Y up, metres. glTF: same → no remap needed.

Mesh sementics in the scene
---------------------------
Each mesh's ``metadata["name"]`` is set to the BIMElement ``stable_id``
(e.g. ``ifcwall:WALL-UUID``). The Three.js viewer in the OCE BIM page
matches mesh names against ``BIMElement.mesh_ref`` to link a picked
mesh to its element row in the side panel.

Materials are differentiated per IFC type so the user can visually
tell walls (concrete grey) from floors (warm sand), openings
(translucent blue) and furniture (light wood).
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import trimesh
from shapely.geometry import Polygon

from app.modules.neoffice.roomplan_importer import _coerce_enum, _extract_rooms, _read_dimensions

logger = logging.getLogger(__name__)


# Reasonable PBR-ish colours for the Three.js viewer.
# Format: RGBA in 0-255 range — trimesh accepts both per-vertex and
# per-mesh `visual.face_colors`.
_COLOR_BY_KIND: dict[str, tuple[int, int, int, int]] = {
    "wall":    (210, 205, 195, 255),   # warm grey
    "door":    (140, 100,  70, 200),   # walnut, slightly transparent
    "window":  (130, 180, 230, 150),   # sky blue, translucent
    "opening": (255, 240, 180,  90),   # pale yellow, mostly transparent
    "floor":   (215, 195, 165, 255),   # warm sand
    "object":  (175, 145, 110, 240),   # light wood
}


def build_glb_bytes(scan: dict[str, Any]) -> bytes:
    """Render a RoomPlan CapturedRoom scan to a binary glTF (GLB) blob.

    Returns the GLB bytes ready to write to storage. Raises if the scan
    is so malformed that not a single mesh can be produced — callers
    should fall back to ``has_geometry=False`` in that case.
    """
    rooms = _extract_rooms(scan)
    if not rooms:
        raise ValueError("No room data in scan")

    meshes: list[trimesh.Trimesh] = []
    counters = {k: 0 for k in _COLOR_BY_KIND}

    for room in rooms:
        for surface in room.get("walls", []) or []:
            m = _surface_to_box(surface, kind="wall")
            if m is not None:
                meshes.append(m); counters["wall"] += 1
        for surface in room.get("doors", []) or []:
            m = _surface_to_box(surface, kind="door")
            if m is not None:
                meshes.append(m); counters["door"] += 1
        for surface in room.get("windows", []) or []:
            m = _surface_to_box(surface, kind="window")
            if m is not None:
                meshes.append(m); counters["window"] += 1
        for surface in room.get("openings", []) or []:
            m = _surface_to_box(surface, kind="opening")
            if m is not None:
                meshes.append(m); counters["opening"] += 1
        for surface in room.get("floors", []) or []:
            m = _floor_to_extruded(surface)
            if m is not None:
                meshes.append(m); counters["floor"] += 1
        for obj in room.get("objects", []) or []:
            m = _surface_to_box(obj, kind="object")
            if m is not None:
                meshes.append(m); counters["object"] += 1

    if not meshes:
        raise ValueError("No meshes produced from scan")

    scene = trimesh.Scene(meshes)
    # The OCE BIM viewer applies ``scene.rotation.x = -π/2`` to every GLB on
    # load (ElementManager.ts:801) — this compensates for upstream DAE-based
    # GLBs that ship Z-up vertices (because trimesh's DAE→GLB export path
    # does NOT convert Z-up to Y-up). Our RoomPlan GLB is built Y-up natively
    # (RoomPlan is Y-up, trimesh box primitive is Y-up), so the viewer's
    # well-meaning rotation flips us 90° onto a wall. Pre-rotate +π/2 around
    # X here so the viewer's rotation lands us right-side-up.
    pre_rot = np.array([
        [1, 0,  0, 0],
        [0, 0, -1, 0],
        [0, 1,  0, 0],
        [0, 0,  0, 1],
    ], dtype=np.float64)
    scene.apply_transform(pre_rot)
    glb = scene.export(file_type="glb")
    logger.info(
        "RoomPlan GLB built: %d meshes (walls=%d doors=%d windows=%d "
        "openings=%d floors=%d objects=%d), %d bytes",
        len(meshes),
        counters["wall"], counters["door"], counters["window"],
        counters["opening"], counters["floor"], counters["object"],
        len(glb),
    )
    return glb


# ── Primitives ──────────────────────────────────────────────────────────────


def _surface_to_box(surface: dict[str, Any], *, kind: str) -> trimesh.Trimesh | None:
    """Return a unit box scaled to ``dimensions`` and placed by ``transform``.

    ``kind`` selects the material colour and stable_id prefix used as
    the mesh name (so the Three.js viewer can cross-reference the
    BIMElement row).
    """
    ident = surface.get("identifier") or surface.get("uuid")
    if not ident:
        return None

    dims = _read_dimensions(surface)
    if all(d <= 0 for d in dims):
        return None

    # Avoid zero-thickness boxes — trimesh chokes on degenerate AABBs.
    extents = tuple(max(d, 0.005) for d in dims)
    box = trimesh.creation.box(extents=extents)

    xform = _roomplan_transform(surface.get("transform"))
    if xform is not None:
        box.apply_transform(xform)

    box.visual.face_colors = _COLOR_BY_KIND.get(kind, (200, 200, 200, 255))
    # Use the raw Apple identifier as the mesh name so the Three.js
    # viewer (which walks ancestor `Object3D.name`) matches this against
    # BIMElement.mesh_ref. Prefixed names like "ifcwall:UUID" don't
    # survive the GLTFLoader → THREE.Group naming pipeline cleanly
    # (the ":" character is stripped, breaking the lookup).
    box.metadata["name"] = str(ident)
    return box


def _floor_to_extruded(floor: dict[str, Any]) -> trimesh.Trimesh | None:
    """Extrude the floor's ``polygonCorners`` into a thin slab.

    Falls back to a flat box of the floor's dimensions when the polygon
    is missing or degenerate.
    """
    ident = floor.get("identifier") or floor.get("uuid")
    if not ident:
        return None

    polygon = floor.get("polygonCorners") or floor.get("polygon_corners")
    xform = _roomplan_transform(floor.get("transform"))

    mesh: trimesh.Trimesh | None = None
    if isinstance(polygon, list) and len(polygon) >= 3:
        try:
            # Project the polygon onto its local plane. RoomPlan exports
            # polygonCorners in the *local* surface frame where the
            # polygon is flat on Z=0 (the surface's own normal); the
            # ``transform`` then rotates it into world space. So we
            # take (x, y) directly, ignoring z.
            poly2d = [(float(p[0]), float(p[1])) for p in polygon if len(p) >= 2]
            shape = Polygon(poly2d)
            if shape.is_valid and shape.area > 0:
                mesh = trimesh.creation.extrude_polygon(shape, height=0.02)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Floor polygon extrusion failed: %s", exc)
            mesh = None

    if mesh is None:
        # Fallback — a flat box of the declared dimensions.
        w, h, d = _read_dimensions(floor)
        # Floors usually have d≈0 (paper thin); enforce 2 cm.
        mesh = trimesh.creation.box(
            extents=(max(w, 0.01), max(h, 0.01), max(d, 0.02))
        )

    if xform is not None:
        mesh.apply_transform(xform)

    mesh.visual.face_colors = _COLOR_BY_KIND["floor"]
    mesh.metadata["name"] = str(ident)
    return mesh


def _roomplan_transform(raw: Any) -> np.ndarray | None:
    """Convert a simd_float4x4 (column-major flat 16-list) to a row-major
    numpy 4×4 ready to feed to ``mesh.apply_transform``.

    Returns None when the input is malformed — caller leaves the mesh
    at origin.
    """
    if not isinstance(raw, list) or len(raw) < 16:
        if isinstance(raw, dict):
            cols = raw.get("columns")
            if isinstance(cols, list):
                flat = [v for col in cols for v in col]
                if len(flat) >= 16:
                    raw = flat[:16]
                else:
                    return None
            else:
                return None
        else:
            return None
    try:
        # Column-major Swift → row-major numpy.
        arr = np.array(raw[:16], dtype=np.float64).reshape(4, 4, order="F")
        return arr
    except (TypeError, ValueError):
        return None


# Silence the noisy "category" enum coercion import in unit tests.
__all__ = ["build_glb_bytes"]
_ = _coerce_enum  # re-export marker (the importer is the canonical user)

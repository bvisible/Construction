"""NEOFFICE FILE — Owned 100% by Neoservice. Not from upstream OpenConstructionERP.

Vision-based plan analysis for the Takeoff module.

The core takeoff ``analyze`` pipeline is text-only: it extracts text (pdfplumber)
from a PDF and feeds it to the LLM. For an architectural drawing that text is
just sparse labels/dimensions, so the model hallucinates ("17 unreadable
elements"). This module instead renders the plan page to an image and sends it
to the multimodal model (Olares "nora", Gemma 4 12B vision), which reads rooms,
elements and the drawing scale directly off the drawing.

It also derives the takeoff calibration (pixels-per-metre) from the scale read
off the title block, so a freshly analysed plan is pre-calibrated and the
detected rooms can be pre-drawn as measurements.

Coordinate convention — IMPORTANT
----------------------------------
Bounding boxes are returned **normalised in [0, 1]** relative to the page
(origin top-left). The frontend multiplies them by the pdfjs page dimensions
(``getViewport({scale: 1})``, i.e. PDF points) to obtain measurement points in
the exact same reference frame it uses when the user draws by hand
(``x = (clientX - rect.left) / zoom`` → PDF points). This keeps the pre-drawn
rooms aligned with the drawing regardless of render resolution.

``scale_pixels_per_unit`` is given in **PDF points per metre**
(``72 / (0.0254 * ratio)``), matching the frontend ``presetScale()`` so it can
be applied directly as the takeoff calibration.

Kept in oe_neoffice (Neoservice custom) to avoid patching the upstream core.
"""

from __future__ import annotations

import base64
import logging
import re
from typing import Any

import pymupdf

from app.modules.ai.ai_client import call_ai, extract_json, resolve_provider_and_key

logger = logging.getLogger(__name__)

# Olares serves a single model aliased "nora" (verified via GET /v1/models).
# We pass it explicitly rather than relying on the site_config ``oce_olares_model``
# value, which is a stale alias (Qwen3.6…) that does not match what Olares routes.
NORA_VISION_MODEL = "nora"

# Render target: longest side in pixels. 1600px keeps the PNG ~280 KB and the
# vision round-trip a few seconds while staying legible for room/scale detection.
DEFAULT_TARGET_PX = 1600

# Gemma/PaliGemma emit bounding boxes in an integer 0..1000 reference frame
# (origin top-left). We normalise by this to a [0, 1] page fraction.
_BBOX_REFERENCE = 1000.0

# 1 inch = 0.0254 m; PDF user space is 72 points per inch.
_METRES_PER_INCH = 0.0254
_POINTS_PER_INCH = 72.0

SYSTEM_PROMPT = (
    "Tu es un expert en lecture de plans d'architecture et de metre (takeoff) "
    "pour la construction. Tu reponds UNIQUEMENT avec un objet JSON valide, "
    "sans aucun texte avant ou apres, sans bloc markdown."
)

USER_PROMPT = (
    "Analyse ce plan et renvoie un objet JSON STRICT avec EXACTEMENT cette structure:\n"
    "{\n"
    '  "plan_type": string,\n'
    '  "scale_label": string|null,\n'
    '  "scale_ratio": number|null,\n'
    '  "rooms": [ {"name": string, "zone": string|null, "usage": string|null, '
    '"bbox": [x0,y0,x1,y1], "approx_area_m2": number|null} ],\n'
    '  "elements": [ {"type": "door|window|wall|other", "label": string|null, '
    '"bbox": [x0,y0,x1,y1]} ]\n'
    "}\n"
    "Regles:\n"
    "- bbox: entiers entre 0 et 1000 dans le repere de l'image "
    "(origine haut-gauche, x vers la droite, y vers le bas), format [x0,y0,x1,y1].\n"
    "- Liste TOUTES les pieces visibles avec leur nom exact lu sur le plan.\n"
    "- zone = appartement ou secteur si visible (ex 'APT 4'), sinon null.\n"
    "- usage = chambre|cuisine|sdb|sejour|hall|balcon|degagement|autre.\n"
    "- scale_label = l'echelle lue dans le cartouche (ex '1:50'); "
    "scale_ratio = l'entier correspondant (ex 50). Sinon null. Ne devine pas.\n"
    "- elements: portes, fenetres et murs les plus evidents.\n"
    "- Valeurs textuelles en francais. Reponds en JSON uniquement."
)


def render_pdf_page_to_png(
    pdf_bytes: bytes,
    page_index: int = 0,
    target_px: int = DEFAULT_TARGET_PX,
) -> tuple[bytes, int, int, float, float]:
    """Render one PDF page to a PNG sized so its longest side is ``target_px``.

    Returns ``(png_bytes, width_px, height_px, page_width_pt, page_height_pt)``.
    The page dimensions are in PDF points (1/72 inch) and are echoed back so the
    frontend/clients know the reference frame the normalised bboxes map onto.
    Raises ``IndexError`` if the page does not exist, ``ValueError`` if the PDF
    cannot be opened.
    """
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:  # corrupt / non-PDF upload
        raise ValueError(f"Cannot open PDF: {exc}") from exc

    with doc:
        if page_index < 0 or page_index >= doc.page_count:
            raise IndexError(
                f"Page {page_index} out of range (document has {doc.page_count})"
            )
        page = doc[page_index]
        rect = page.rect
        longest = max(rect.width, rect.height) or 1.0
        zoom = float(target_px) / longest
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
        return pix.tobytes("png"), pix.width, pix.height, rect.width, rect.height


def derive_scale_pixels_per_unit(scale_ratio: float) -> float:
    """Derive the takeoff calibration (PDF points per metre) from a drawing scale.

    A drawing at 1:``scale_ratio`` means 1 unit on paper equals ``scale_ratio``
    units in reality. Measurement points are stored in PDF points (1/72 inch),
    so the calibration is ``72 / (0.0254 * scale_ratio)`` points-per-metre —
    identical to the frontend ``presetScale()``. Independent of render zoom.

    Assumes the PDF is at true paper size (standard for architectural exports).
    The user can still recalibrate manually with the 2-point tool.
    """
    return _POINTS_PER_INCH / (_METRES_PER_INCH * scale_ratio)


def _safe_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _coerce_scale_ratio(parsed: dict[str, Any]) -> float | None:
    """Pull a plausible scale ratio out of the model output.

    Prefers a numeric ``scale_ratio`` when it looks like a real architectural
    scale (5..2000); otherwise parses ``scale_label`` like "1:50".
    """
    raw = _safe_float(parsed.get("scale_ratio"))
    if raw is not None and 5.0 <= raw <= 2000.0:
        return raw
    label = parsed.get("scale_label")
    if isinstance(label, str):
        match = re.search(r"1\s*[:/]\s*(\d{1,4})", label)
        if match:
            val = float(match.group(1))
            if 5.0 <= val <= 2000.0:
                return val
    return None


def _normalize_bbox(bbox: Any) -> list[float] | None:
    """Normalise a model bbox to a ``[x0, y0, x1, y1]`` page fraction in [0, 1].

    The model emits a 0..1000 integer frame; we divide by 1000. Robust to the
    model occasionally returning already-normalised 0..1 floats (detected from
    the magnitude of the values). Coordinates are clamped to [0, 1].
    """
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return None
    try:
        vals = [float(v) for v in bbox]
    except (TypeError, ValueError):
        return None
    ref = 1.0 if max(abs(v) for v in vals) <= 1.0 else _BBOX_REFERENCE
    norm = [min(1.0, max(0.0, v / ref)) for v in vals]
    return [round(v, 4) for v in norm]


async def analyze_plan_vision(
    pdf_bytes: bytes,
    page_index: int,
    settings: Any,
    *,
    scale_override: float | None = None,
    target_px: int = DEFAULT_TARGET_PX,
) -> dict[str, Any]:
    """Run the vision analysis on one PDF page and return a structured result.

    Renders the page, sends the image to the multimodal model, parses the JSON,
    normalises bboxes to page fractions and derives the calibration from the
    scale. Raises ``RuntimeError`` if the output is not a JSON object,
    ``IndexError`` if the page is out of range.
    """
    png_bytes, width_px, height_px, page_w_pt, page_h_pt = render_pdf_page_to_png(
        pdf_bytes, page_index=page_index, target_px=target_px
    )
    image_b64 = base64.b64encode(png_bytes).decode("ascii")

    provider, api_key = resolve_provider_and_key(settings)

    raw_response, tokens = await call_ai(
        provider=provider,
        api_key=api_key,
        system=SYSTEM_PROMPT,
        prompt=USER_PROMPT,
        image_base64=image_b64,
        image_media_type="image/png",
        max_tokens=2048,
        model=NORA_VISION_MODEL,
    )

    parsed = extract_json(raw_response)
    if not isinstance(parsed, dict):
        raise RuntimeError("Vision model did not return a JSON object")

    scale_ratio = scale_override or _coerce_scale_ratio(parsed)
    scale_pixels_per_unit = (
        derive_scale_pixels_per_unit(scale_ratio) if scale_ratio else None
    )

    rooms: list[dict[str, Any]] = []
    for room in parsed.get("rooms", []) or []:
        if not isinstance(room, dict):
            continue
        rooms.append(
            {
                "name": str(room.get("name") or "").strip() or "Sans nom",
                "zone": str(room["zone"]).strip() if room.get("zone") else None,
                "usage": str(room["usage"]).strip() if room.get("usage") else None,
                "bbox": _normalize_bbox(room.get("bbox")),
                "approx_area_m2": _safe_float(room.get("approx_area_m2")),
            }
        )

    elements: list[dict[str, Any]] = []
    for element in parsed.get("elements", []) or []:
        if not isinstance(element, dict):
            continue
        elements.append(
            {
                "type": str(element.get("type") or "other").strip().lower(),
                "label": str(element["label"]).strip() if element.get("label") else None,
                "bbox": _normalize_bbox(element.get("bbox")),
            }
        )

    logger.info(
        "Vision plan analysis: rooms=%d elements=%d scale=%s ppu=%s tokens=%d",
        len(rooms), len(elements), scale_ratio, scale_pixels_per_unit, tokens,
    )

    return {
        "plan_type": str(parsed["plan_type"]).strip() if parsed.get("plan_type") else None,
        "scale_label": str(parsed["scale_label"]).strip() if parsed.get("scale_label") else None,
        "scale_ratio": scale_ratio,
        "scale_pixels_per_unit": scale_pixels_per_unit,
        "page_width_pt": round(page_w_pt, 2),
        "page_height_pt": round(page_h_pt, 2),
        "image_width": width_px,
        "image_height": height_px,
        "rooms": rooms,
        "elements": elements,
        "tokens_used": tokens,
    }

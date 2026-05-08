"""NEOFFICE FILE — Owned 100% by Neoservice. Not from upstream OCE.

Swiss regional pack API routes.

Endpoints:
    GET /config/           — Full Swiss regional configuration
    GET /standards/        — All standards (CFC, eBKP-H, eBKP-T, NPK, SIA)
    GET /standards/{code}  — Single standard (e.g. CFC, NPK)
    GET /classifications/  — Lightweight catalog list (codes + labels only)
    GET /tax-rules/        — TVA rates for invoicing
    GET /contract-types/   — Swiss contract type codes
    GET /sia-norms/        — SIA reference norms
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_current_user_id
from app.modules.swiss_pack.config import (
    PACK_CONFIG,
    get_classifications_summary,
    get_standard_by_code,
)

router = APIRouter(dependencies=[Depends(get_current_user_id)])
logger = logging.getLogger(__name__)


@router.get("/config/")
async def get_config() -> dict[str, Any]:
    """Return the full Swiss regional pack configuration."""
    return PACK_CONFIG


@router.get("/standards/")
async def list_standards() -> list[dict[str, Any]]:
    """Return the list of standards declared in this pack (without bulk data)."""
    return [
        {
            "code": s["code"],
            "name": s["name"],
            "description": s.get("description", ""),
            "size": _measure_standard_size(s),
        }
        for s in PACK_CONFIG["standards"]
    ]


@router.get("/standards/{code}/")
async def get_standard(code: str) -> dict[str, Any]:
    """Return a single standard by code (CFC, NPK, eBKP-H, eBKP-T, SIA_*)."""
    std = get_standard_by_code(code)
    if not std:
        raise HTTPException(status_code=404, detail=f"Unknown standard: {code}")
    return std


@router.get("/classifications/")
async def get_classifications() -> dict[str, Any]:
    """Compact summary of code+label pairs across CFC, eBKP-H/T and NPK."""
    return get_classifications_summary()


@router.get("/tax-rules/")
async def get_tax_rules() -> list[dict[str, Any]]:
    return PACK_CONFIG["tax_rules"]


@router.get("/contract-types/")
async def get_contract_types() -> list[dict[str, Any]]:
    return PACK_CONFIG["contract_types"]


@router.get("/sia-norms/")
async def get_sia_norms() -> list[dict[str, Any]]:
    return [s for s in PACK_CONFIG["standards"] if s["code"].startswith("SIA_")]


def _measure_standard_size(standard: dict[str, Any]) -> int:
    """Best-effort row-count for the human-readable summary."""
    for key in ("entries", "cost_groups", "service_phases", "parts", "chapters"):
        if key in standard:
            return len(standard[key])
    return 0

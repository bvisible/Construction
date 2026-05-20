"""NEOFFICE FILE — Owned 100% by Neoservice. Not from upstream OpenConstructionERP.

HTTP client for the Neoconstruction -> Activity bridge. Posts mirrored
Activity payloads to the Frappe `neoffice_activity` app.

Configuration is read from the environment (systemd `EnvironmentFile`):
``ACTIVITY_BRIDGE_URL`` and ``ACTIVITY_BRIDGE_TOKEN``. Reading it here rather
than in ``app/config.py`` keeps the bridge a fully additive, upstream-free
module.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_UPSERT_PATH = (
    "/api/method/neoffice_activity.neoffice_activity.api"
    ".upsert_activity_from_neoconstruction"
)
_TIMEOUT_SECONDS = 10.0


def _bridge_config() -> tuple[str, str]:
    """Return the (base_url, token) bridge configuration from the environment."""
    base_url = (os.environ.get("ACTIVITY_BRIDGE_URL", "") or "").rstrip("/")
    token = os.environ.get("ACTIVITY_BRIDGE_TOKEN", "") or ""
    return base_url, token


async def push_activity(payload: dict[str, Any]) -> bool:
    """Post a mirrored-Activity payload to the Frappe bridge endpoint.

    Returns True on success, False otherwise. Never raises: a bridge failure
    must not break the Neoconstruction flow that triggered it.
    """
    base_url, token = _bridge_config()
    source_id = payload.get("neoconstruction_source_id")

    if not base_url or not token:
        logger.warning(
            "Activity bridge not configured (ACTIVITY_BRIDGE_URL / "
            "ACTIVITY_BRIDGE_TOKEN) — skipping push for source_id=%s",
            source_id,
        )
        return False

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{base_url}{_UPSERT_PATH}",
                json={"payload": payload, "token": token},
            )
        response.raise_for_status()
    except Exception:
        logger.exception("Activity bridge push failed for source_id=%s", source_id)
        return False

    logger.info(
        "Activity bridge push OK source_id=%s status=%s",
        source_id,
        response.status_code,
    )
    return True

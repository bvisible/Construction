"""NEOFFICE FILE — Owned 100% by Neoservice. Not from upstream OpenConstructionERP.

HTTP client for the Neoconstruction -> Activity bridge. Posts mirrored
Activity payloads to the Frappe `neoffice_activity` app.

Frappe and the OCE backend are co-located on the same host, so the target
URL defaults to Frappe's local gunicorn. Only ACTIVITY_BRIDGE_TOKEN has to
be configured (in the systemd EnvironmentFile); ACTIVITY_BRIDGE_URL is
optional and only needed to target a non-standard / remote Frappe.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_FRAPPE_URL = "http://127.0.0.1:8000"
_FRAPPE_SITE = "prod.local"
_UPSERT_PATH = (
    "/api/method/neoffice_activity.neoffice_activity.api"
    ".upsert_activity_from_neoconstruction"
)
_TIMEOUT_SECONDS = 10.0


def _bridge_config() -> tuple[str, str, dict[str, str]]:
    """Return the (base_url, token, extra_headers) bridge configuration.

    Defaults to Frappe's local gunicorn (co-located host) with a `prod.local`
    Host header so Frappe resolves the site. Set ACTIVITY_BRIDGE_URL to target
    a remote Frappe; the Host header then follows that URL.
    """
    base_url = (
        os.environ.get("ACTIVITY_BRIDGE_URL", "") or _DEFAULT_FRAPPE_URL
    ).rstrip("/")
    token = os.environ.get("ACTIVITY_BRIDGE_TOKEN", "") or ""
    headers: dict[str, str] = {}
    if "127.0.0.1" in base_url or "localhost" in base_url:
        headers["Host"] = _FRAPPE_SITE
    return base_url, token, headers


async def push_activity(payload: dict[str, Any]) -> bool:
    """Post a mirrored-Activity payload to the Frappe bridge endpoint.

    Returns True on success, False otherwise. Never raises: a bridge failure
    must not break the Neoconstruction flow that triggered it.
    """
    base_url, token, headers = _bridge_config()
    source_id = payload.get("neoconstruction_source_id")

    if not token:
        logger.warning(
            "Activity bridge token not configured (ACTIVITY_BRIDGE_TOKEN) — "
            "skipping push for source_id=%s",
            source_id,
        )
        return False

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{base_url}{_UPSERT_PATH}",
                json={"payload": payload, "token": token},
                headers=headers,
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

# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Client-error sink API routes.

Endpoints:
    POST /                         — accept an anonymised client error report

The endpoint is intentionally write-only and unauthenticated so that
anonymous landing-page or marketing-site errors can still be captured.
A per-IP rate limit at 30 req/min (sliding window) keeps the surface
safe from abuse without introducing a Redis dependency.

Storage is a v4.3 follow-up — for now we forward the payload to the
standard ``logging`` pipeline at WARNING level so it shows up next to
backend errors in journald / log aggregators.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, status

from app.core.rate_limiter import RateLimiter, client_identifier
from app.modules.client_errors.schemas import ClientErrorReport

router = APIRouter(tags=["client_errors"])
logger = logging.getLogger(__name__)

# Per-IP cap. 30 req/min handles a tab that throws inside a tight render
# loop without dropping every report, while still rejecting a runaway
# client / abusive scanner. Sliding window; in-memory only — no Redis.
_client_error_limiter = RateLimiter(max_requests=30, window_seconds=60)


@router.post("/", status_code=status.HTTP_202_ACCEPTED)
async def submit_client_error(
    payload: ClientErrorReport,
    request: Request,
) -> dict[str, str]:
    """Accept an anonymised client-error report.

    Returns ``202 Accepted`` on success — the client is fire-and-forget
    and never reads the response body, but the explicit status code
    documents that the report is queued/observed rather than persisted.
    """
    client_ip = client_identifier(request)
    allowed, _ = _client_error_limiter.is_allowed(client_ip)
    if not allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Client-error reporter rate limit exceeded.",
        )

    # Cap individual stack lines so a single malformed report cannot
    # blow up the log line size budget. The Pydantic schema already
    # caps the list to 128 entries.
    capped_stack = [line[:512] for line in payload.stack_lines[:64]]

    logger.warning(
        "client_error",
        extra={
            "client_error_id": payload.error_id,
            "client_timestamp": payload.timestamp,
            "client_message": payload.message[:512],
            "client_stack": capped_stack,
            "client_user_agent": payload.user_agent[:256],
            "client_path": payload.path[:256],
            "client_ip": client_ip,
        },
    )
    return {"status": "accepted"}

"""NEOFFICE FILE — Owned 100% by Neoservice. Not from upstream OpenConstructionERP.

Maps Neoconstruction schedule objects to Frappe Activity bridge payloads.

The mirror is intentionally minimal: identity, title, description, date and
the planned assignee. Cost and effort mapping is deferred -- a Work Order's
`planned_cost` is free-text and its dates are not hour-denominated.
"""

from __future__ import annotations

from typing import Any

from app.modules.schedule.models import Activity, Schedule, WorkOrder

_TITLE_MAX_LEN = 140


def _emails_from_assigned_to(assigned_to: str | None) -> list[str]:
    """Extract resolvable employee emails from a WorkOrder.assigned_to value.

    `assigned_to` is free text that may hold an email or an opaque user id.
    Only email-shaped values are forwarded; anything else yields an empty
    list so Frappe leaves the Activity unassigned (the fallback-empty rule).
    """
    if assigned_to and "@" in assigned_to:
        return [assigned_to.strip()]
    return []


def work_order_to_activity_payload(
    work_order: WorkOrder,
    activity: Activity,
    schedule: Schedule,
) -> dict[str, Any]:
    """Build the Frappe bridge payload for a Neoconstruction Work Order."""
    title = work_order.description or work_order.code or f"Work Order {work_order.id}"
    return {
        "neoconstruction_source_type": "Work Order",
        "neoconstruction_source_id": str(work_order.id),
        "neoconstruction_project_id": str(schedule.project_id),
        "neoconstruction_wbs_code": activity.wbs_code or None,
        "title": title[:_TITLE_MAX_LEN],
        "description": work_order.description or None,
        "date": work_order.planned_start or None,
        "assigned_employee_emails": _emails_from_assigned_to(work_order.assigned_to),
    }


def schedule_activity_to_activity_payload(
    activity: Activity,
    schedule: Schedule,
) -> dict[str, Any]:
    """Build the Frappe bridge payload for a Neoconstruction Schedule Activity."""
    title = activity.name or f"Activity {activity.id}"
    return {
        "neoconstruction_source_type": "Schedule Activity",
        "neoconstruction_source_id": str(activity.id),
        "neoconstruction_project_id": str(schedule.project_id),
        "neoconstruction_wbs_code": activity.wbs_code or None,
        "title": title[:_TITLE_MAX_LEN],
        "description": activity.description or None,
        "date": activity.start_date or None,
        "assigned_employee_emails": [],
    }

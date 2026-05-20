"""NEOFFICE FILE — Owned 100% by Neoservice. Not from upstream OpenConstructionERP.

Unit tests for the Neoconstruction -> Activity bridge (mappers + HTTP
client). The EventBus handlers are thin glue over these units and are
validated end-to-end against osiris in bridge milestone J6.
"""

from __future__ import annotations

import uuid

import pytest

from app.modules.neoffice.bridge import frappe_client, mappers
from app.modules.schedule.models import Activity, Schedule, WorkOrder


# ── mappers ──────────────────────────────────────────────────────────────


def _schedule(project_id):
    return Schedule(id=uuid.uuid4(), project_id=project_id, name="Test Schedule")


def _activity(schedule_id, **kw):
    defaults = dict(
        id=uuid.uuid4(),
        schedule_id=schedule_id,
        name="Test Activity",
        description="",
        wbs_code="01.03.005",
        start_date="2026-05-21",
    )
    defaults.update(kw)
    return Activity(**defaults)


def _work_order(activity_id, **kw):
    defaults = dict(
        id=uuid.uuid4(),
        activity_id=activity_id,
        code="WO-1",
        description="Pose carrelage SDB",
        assigned_to="jean@example.com",
        planned_start="2026-05-21",
    )
    defaults.update(kw)
    return WorkOrder(**defaults)


class TestWorkOrderMapper:
    def test_payload_core_fields(self):
        project_id = uuid.uuid4()
        schedule = _schedule(project_id)
        activity = _activity(schedule.id)
        work_order = _work_order(activity.id)

        payload = mappers.work_order_to_activity_payload(work_order, activity, schedule)

        assert payload["neoconstruction_source_type"] == "Work Order"
        assert payload["neoconstruction_source_id"] == str(work_order.id)
        assert payload["neoconstruction_project_id"] == str(project_id)
        assert payload["neoconstruction_wbs_code"] == "01.03.005"
        assert payload["title"] == "Pose carrelage SDB"
        assert payload["date"] == "2026-05-21"

    def test_assigned_email_extracted(self):
        schedule = _schedule(uuid.uuid4())
        activity = _activity(schedule.id)
        work_order = _work_order(activity.id, assigned_to="marie@example.com")

        payload = mappers.work_order_to_activity_payload(work_order, activity, schedule)
        assert payload["assigned_employee_emails"] == ["marie@example.com"]

    def test_non_email_assignee_yields_empty(self):
        schedule = _schedule(uuid.uuid4())
        activity = _activity(schedule.id)
        # An opaque user id (not an email) must not be forwarded.
        work_order = _work_order(activity.id, assigned_to="user-42-uuid")

        payload = mappers.work_order_to_activity_payload(work_order, activity, schedule)
        assert payload["assigned_employee_emails"] == []

    def test_title_falls_back_to_code(self):
        schedule = _schedule(uuid.uuid4())
        activity = _activity(schedule.id)
        work_order = _work_order(activity.id, description="", code="WO-77")

        payload = mappers.work_order_to_activity_payload(work_order, activity, schedule)
        assert payload["title"] == "WO-77"


class TestScheduleActivityMapper:
    def test_payload_core_fields(self):
        project_id = uuid.uuid4()
        schedule = _schedule(project_id)
        activity = _activity(schedule.id, name="Lot 3 - Carrelage")

        payload = mappers.schedule_activity_to_activity_payload(activity, schedule)

        assert payload["neoconstruction_source_type"] == "Schedule Activity"
        assert payload["neoconstruction_source_id"] == str(activity.id)
        assert payload["neoconstruction_project_id"] == str(project_id)
        assert payload["title"] == "Lot 3 - Carrelage"
        assert payload["assigned_employee_emails"] == []


# ── frappe_client ────────────────────────────────────────────────────────


class _FakeResponse:
    status_code = 200

    def raise_for_status(self):
        return None


class _FakeAsyncClient:
    """Minimal httpx.AsyncClient stand-in that captures the POST."""

    captured: dict = {}

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None, headers=None):
        _FakeAsyncClient.captured = {"url": url, "json": json, "headers": headers}
        return _FakeResponse()


async def test_push_activity_posts_payload_and_token(monkeypatch):
    """A configured bridge posts the payload + token to the upsert endpoint."""
    _FakeAsyncClient.captured = {}
    monkeypatch.setattr(frappe_client.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setenv("ACTIVITY_BRIDGE_URL", "https://osiris.example/")
    monkeypatch.setenv("ACTIVITY_BRIDGE_TOKEN", "tok-abc")

    ok = await frappe_client.push_activity({"neoconstruction_source_id": "wo-1"})

    assert ok is True
    assert _FakeAsyncClient.captured["url"].endswith("upsert_activity_from_neoconstruction")
    assert _FakeAsyncClient.captured["json"]["token"] == "tok-abc"
    assert (
        _FakeAsyncClient.captured["json"]["payload"]["neoconstruction_source_id"] == "wo-1"
    )


async def test_push_activity_skips_when_unconfigured(monkeypatch):
    """An unconfigured bridge no-ops instead of raising."""
    monkeypatch.delenv("ACTIVITY_BRIDGE_URL", raising=False)
    monkeypatch.delenv("ACTIVITY_BRIDGE_TOKEN", raising=False)

    ok = await frappe_client.push_activity({"neoconstruction_source_id": "wo-x"})
    assert ok is False


# ── inbound progress endpoint auth ───────────────────────────────────────


class TestBridgeTokenAuth:
    """Tests for the shared-token guard of the inbound progress endpoint (J4a)."""

    def test_valid_token_accepted(self, monkeypatch):
        from app.modules.neoffice.router import _verify_activity_bridge_token

        monkeypatch.setenv("ACTIVITY_BRIDGE_TOKEN", "secret-xyz")
        # A matching token must not raise.
        _verify_activity_bridge_token(x_activity_bridge_token="secret-xyz")

    def test_invalid_token_rejected(self, monkeypatch):
        from fastapi import HTTPException

        from app.modules.neoffice.router import _verify_activity_bridge_token

        monkeypatch.setenv("ACTIVITY_BRIDGE_TOKEN", "secret-xyz")
        with pytest.raises(HTTPException) as exc_info:
            _verify_activity_bridge_token(x_activity_bridge_token="wrong-token")
        assert exc_info.value.status_code == 401

    def test_missing_token_config_rejected(self, monkeypatch):
        from fastapi import HTTPException

        from app.modules.neoffice.router import _verify_activity_bridge_token

        monkeypatch.delenv("ACTIVITY_BRIDGE_TOKEN", raising=False)
        with pytest.raises(HTTPException):
            _verify_activity_bridge_token(x_activity_bridge_token="anything")

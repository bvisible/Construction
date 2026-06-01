# DDC-CWICR-OE: DataDrivenConstruction / OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Smoke test for the Transmittals module (test-coverage audit 5).

Proves end-to-end wiring of the `oe_transmittals` module surface:

1. GET   /api/v1/transmittals/?project_id=...           (empty list)
2. POST  /api/v1/transmittals/                          (create draft)
3. GET   /api/v1/transmittals/{id}                      (happy path)
4. GET   /api/v1/transmittals/{missing-uuid}            (404)
5. PATCH /api/v1/transmittals/{id}                      (subject update)
6. POST  /api/v1/transmittals/{id}/issue/               (lock & 'issued')
7. PATCH /api/v1/transmittals/{id}                      (409 after lock)
8. DELETE on issued transmittal                         (409 audit guard)
9. RBAC: viewer role → 403 on the list endpoint
       (transmittals.* not registered in permission_registry,
        so non-admin roles must be denied)
10. DELETE a fresh DRAFT transmittal                    (204)
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

# ── Per-module SQLite isolation (MUST run BEFORE app imports) ─────────────
_TMP_DIR = Path(tempfile.mkdtemp(prefix="oe-transmittals-"))
_TMP_DB = _TMP_DIR / "transmittals.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP_DB.as_posix()}"
os.environ["DATABASE_SYNC_URL"] = f"sqlite:///{_TMP_DB.as_posix()}"

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402


@pytest_asyncio.fixture(scope="module")
async def app_instance():
    from app.config import get_settings

    get_settings.cache_clear()
    from app.main import create_app

    app = create_app()
    async with app.router.lifespan_context(app):
        from app.database import Base, engine

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield app


@pytest_asyncio.fixture(scope="module")
async def client(app_instance):
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _login_as(client: AsyncClient, role: str) -> tuple[str, dict[str, str]]:
    """Register a user, force the requested role + activate, log in.

    Returns (email, auth-header).
    """
    tag = uuid.uuid4().hex[:8]
    email = f"trn-{role}-{tag}@test.io"
    password = f"TrnTest{tag}9"
    reg = await client.post(
        "/api/v1/users/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": f"Trn {role} {tag}",
            "role": role,
        },
    )
    assert reg.status_code in (200, 201), reg.text

    # Force-activate + force the requested role (registration may demote).
    from sqlalchemy import update

    from app.database import async_session_factory
    from app.modules.users.models import User

    async with async_session_factory() as session:
        await session.execute(
            update(User).where(User.email == email.lower()).values(role=role, is_active=True),
        )
        await session.commit()

    login = await client.post(
        "/api/v1/users/auth/login",
        json={"email": email, "password": password},
    )
    token = login.json().get("access_token", "")
    assert token, login.text
    return email, {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_transmittals_smoke_full_lifecycle(client: AsyncClient):
    # Admin user for the happy-path CRUD lifecycle.
    _, header = await _login_as(client, "admin")

    # Create a project for the transmittal (FK target).
    proj = await client.post(
        "/api/v1/projects/",
        json={"name": "Transmittals Smoke", "description": "test-coverage audit 5"},
        headers=header,
    )
    assert proj.status_code in (200, 201), proj.text
    project_id = proj.json()["id"]

    # ── 1. GET list — empty ──────────────────────────────────────────────
    empty = await client.get(
        "/api/v1/transmittals/",
        params={"project_id": project_id},
        headers=header,
    )
    assert empty.status_code == 200, empty.text
    body = empty.json()
    assert body["total"] == 0
    assert body["items"] == []
    assert body["offset"] == 0
    assert body["limit"] == 50

    # ── 2. POST create — happy path ──────────────────────────────────────
    create_resp = await client.post(
        "/api/v1/transmittals/",
        json={
            "project_id": project_id,
            "subject": "Issued for Construction — L01 Walls",
            "purpose_code": "for_construction",
            "issued_date": "2026-05-28",
            "cover_note": "Please find attached the IFC drawings for L01.",
            "recipients": [
                {"action_required": "review"},
            ],
            "items": [
                {"item_number": 1, "description": "L01-A101 Floor Plan"},
            ],
        },
        headers=header,
    )
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    transmittal_id = created["id"]
    assert created["status"] == "draft"
    assert created["is_locked"] is False
    assert created["transmittal_number"]  # auto-generated
    assert created["subject"] == "Issued for Construction — L01 Walls"
    assert len(created["recipients"]) == 1
    assert len(created["items"]) == 1

    # ── 3. GET by id — happy path ────────────────────────────────────────
    got = await client.get(
        f"/api/v1/transmittals/{transmittal_id}",
        headers=header,
    )
    assert got.status_code == 200, got.text
    assert got.json()["id"] == transmittal_id

    # ── 4. GET by id — 404 on bogus uuid ─────────────────────────────────
    missing = await client.get(
        f"/api/v1/transmittals/{uuid.uuid4()}",
        headers=header,
    )
    assert missing.status_code == 404, missing.text

    # ── 5. PATCH update — happy path on a draft transmittal ──────────────
    patched = await client.patch(
        f"/api/v1/transmittals/{transmittal_id}",
        json={"subject": "Revised subject — IFC drawings L01"},
        headers=header,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["subject"] == "Revised subject — IFC drawings L01"

    # ── 6. POST /issue — locks the transmittal ───────────────────────────
    issued = await client.post(
        f"/api/v1/transmittals/{transmittal_id}/issue/",
        headers=header,
    )
    assert issued.status_code == 200, issued.text
    issued_body = issued.json()
    assert issued_body["status"] == "issued"
    assert issued_body["is_locked"] is True

    # ── 7. PATCH after issue → 409 (locked) ──────────────────────────────
    locked_patch = await client.patch(
        f"/api/v1/transmittals/{transmittal_id}",
        json={"subject": "Should not be allowed"},
        headers=header,
    )
    assert locked_patch.status_code == 409, locked_patch.text

    # ── 8. DELETE issued transmittal → 409 (audit-trail guard) ───────────
    locked_delete = await client.delete(
        f"/api/v1/transmittals/{transmittal_id}",
        headers=header,
    )
    assert locked_delete.status_code == 409, locked_delete.text

    # ── 10. DELETE a fresh DRAFT — should succeed with 204 ───────────────
    fresh = await client.post(
        "/api/v1/transmittals/",
        json={
            "project_id": project_id,
            "subject": "Draft to delete",
            "purpose_code": "for_information",
        },
        headers=header,
    )
    assert fresh.status_code == 201, fresh.text
    fresh_id = fresh.json()["id"]
    deleted = await client.delete(
        f"/api/v1/transmittals/{fresh_id}",
        headers=header,
    )
    assert deleted.status_code == 204, deleted.text

    # And confirm it's gone.
    gone = await client.get(
        f"/api/v1/transmittals/{fresh_id}",
        headers=header,
    )
    assert gone.status_code == 404, gone.text


@pytest.mark.asyncio
async def test_transmittals_rbac_viewer_denied(client: AsyncClient):
    """A viewer must hit 403 on every gated transmittal route.

    The transmittals module does NOT register its permissions with
    ``permission_registry`` (no ``permissions.py`` file ships in the
    package), so for non-admin roles the live-registry fallback in
    ``RequirePermission`` returns False ("Unknown permission") and the
    request is denied with 403. Admins still pass via the role bypass.
    """
    _, viewer_hdr = await _login_as(client, "viewer")

    # Random project_id — auth/RBAC check fires BEFORE any project lookup.
    forbidden = await client.get(
        "/api/v1/transmittals/",
        params={"project_id": str(uuid.uuid4())},
        headers=viewer_hdr,
    )
    assert forbidden.status_code == 403, forbidden.text

    # Same for write surface — create attempt must also 403.
    forbidden_create = await client.post(
        "/api/v1/transmittals/",
        json={
            "project_id": str(uuid.uuid4()),
            "subject": "Forbidden create",
            "purpose_code": "for_information",
        },
        headers=viewer_hdr,
    )
    assert forbidden_create.status_code == 403, forbidden_create.text

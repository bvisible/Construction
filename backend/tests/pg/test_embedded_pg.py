"""Embedded-PostgreSQL runtime helper: boot -> set URLs -> connect -> shutdown.

Exercises app.core.embedded_pg directly (the helper the CLI wires into
_setup_env). Gated to the PG lane like the rest of tests/pg.
"""
from __future__ import annotations

import os

import pytest

from app.core import embedded_pg

pytestmark = pytest.mark.asyncio


async def test_boot_sets_urls_connects_and_shuts_down(tmp_path, monkeypatch) -> None:
    # Preserve the URLs the session fixture set; boot() writes os.environ directly.
    saved_url = os.environ.get("DATABASE_URL")
    saved_sync = os.environ.get("DATABASE_SYNC_URL")
    monkeypatch.setenv("OE_USE_EMBEDDED_PG", "1")

    assert embedded_pg.is_requested() is True
    assert embedded_pg.is_running() is False

    booted = embedded_pg.boot(tmp_path)
    try:
        assert booted is True
        assert embedded_pg.is_running() is True

        async_url = os.environ["DATABASE_URL"]
        sync_url = os.environ["DATABASE_SYNC_URL"]
        assert async_url.startswith("postgresql+asyncpg://")
        assert sync_url.startswith("postgresql+psycopg2://")
        assert (tmp_path / "pgdata").is_dir()

        # The URL actually connects.
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool

        eng = create_async_engine(async_url, poolclass=NullPool)
        try:
            async with eng.connect() as conn:
                assert (await conn.execute(text("SELECT 1"))).scalar_one() == 1
        finally:
            await eng.dispose()

        # boot() is idempotent.
        assert embedded_pg.boot(tmp_path) is True
    finally:
        embedded_pg.shutdown()
        assert embedded_pg.is_running() is False
        # Restore the session fixture's URLs (boot overwrote them in os.environ).
        if saved_url is not None:
            os.environ["DATABASE_URL"] = saved_url
        if saved_sync is not None:
            os.environ["DATABASE_SYNC_URL"] = saved_sync

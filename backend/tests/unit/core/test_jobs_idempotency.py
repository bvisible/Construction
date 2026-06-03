"""Idempotency tests for the W0.1 job runner (RFC 34 §4 W0.1).

Contract:
    submit_job() with the same ``idempotency_key`` MUST return the same
    JobRun row, regardless of how many concurrent callers race the
    submission. No duplicate ``oe_job_run`` rows may be inserted, and
    only ONE Celery dispatch must be queued.

This test deliberately mocks the Celery dispatch — we are testing the
DB-side idempotency contract, not Celery delivery. The integration
test ``test_jobs_celery_redis.py`` covers the dispatch path end-to-end.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.job_run import JobRun
from app.core.job_runner import submit_job
from tests._pg import isolated_engine


@pytest_asyncio.fixture
async def session_factory():
    """Async session factory bound to a per-test throwaway PostgreSQL database.

    ``submit_job`` opens its own sessions from the factory, commits, and
    re-reads the committed rows from separate sessions — and the cross-thread
    test below spins up a fresh event loop per thread that must see those
    commits. A real throwaway database (cloned from the schema-loaded template)
    provides the required cross-connection commit visibility, which a
    savepoint-rolled-back shared session cannot.
    """
    async with isolated_engine() as engine:
        yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.mark.asyncio
async def test_same_idempotency_key_returns_existing_jobrun(session_factory) -> None:
    """Second call with the same key MUST return the original JobRun id."""
    with patch("app.core.job_runner._dispatch_to_celery") as mock_dispatch:
        mock_dispatch.return_value = "celery-task-id-1"

        first = await submit_job(
            kind="test.noop",
            payload={"x": 1},
            idempotency_key="run-001",
            session_factory=session_factory,
        )
        second = await submit_job(
            kind="test.noop",
            payload={"x": 2},  # different payload — must still de-dupe
            idempotency_key="run-001",
            session_factory=session_factory,
        )

    assert first.id == second.id
    assert first.idempotency_key == "run-001"
    # Celery dispatch must only fire ONCE for the de-duped key.
    assert mock_dispatch.call_count == 1


@pytest.mark.asyncio
async def test_different_idempotency_keys_create_distinct_jobs(session_factory) -> None:
    """Different keys must produce distinct JobRuns."""
    with patch("app.core.job_runner._dispatch_to_celery") as mock_dispatch:
        mock_dispatch.return_value = "celery-task-id"

        a = await submit_job(
            kind="test.noop",
            payload={},
            idempotency_key="key-A",
            session_factory=session_factory,
        )
        b = await submit_job(
            kind="test.noop",
            payload={},
            idempotency_key="key-B",
            session_factory=session_factory,
        )

    assert a.id != b.id
    assert mock_dispatch.call_count == 2


@pytest.mark.asyncio
async def test_no_idempotency_key_creates_new_jobrun_each_time(session_factory) -> None:
    """Missing idempotency_key means every submit_job creates a fresh row."""
    with patch("app.core.job_runner._dispatch_to_celery") as mock_dispatch:
        mock_dispatch.return_value = "celery-task-id"

        a = await submit_job(
            kind="test.noop",
            payload={},
            session_factory=session_factory,
        )
        b = await submit_job(
            kind="test.noop",
            payload={},
            session_factory=session_factory,
        )

    assert a.id != b.id
    assert mock_dispatch.call_count == 2


@pytest.mark.asyncio
async def test_concurrent_submits_with_same_key_dedupe(session_factory) -> None:
    """Five concurrent submit_job calls on the same key must collapse to one row."""
    with patch("app.core.job_runner._dispatch_to_celery") as mock_dispatch:
        mock_dispatch.return_value = "celery-task-id"

        async def submit() -> JobRun:
            return await submit_job(
                kind="test.noop",
                payload={"i": 1},
                idempotency_key="concurrent-key",
                session_factory=session_factory,
            )

        results = await asyncio.gather(
            submit(),
            submit(),
            submit(),
            submit(),
            submit(),
        )

    ids = {r.id for r in results}
    assert len(ids) == 1, f"Expected 1 distinct JobRun id, got {len(ids)}: {ids}"

    # And only one DB row exists for that key.
    async with session_factory() as s:
        from sqlalchemy import select

        rows = (await s.execute(select(JobRun).where(JobRun.idempotency_key == "concurrent-key"))).scalars().all()
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_idempotency_key_uniqueness_across_threads(
    session_factory,
    monkeypatch,
) -> None:
    """Same key used from multiple threads (sync wrapper) must not duplicate.

    Each thread spins its own event loop via ``asyncio.run`` — the
    contract here is that the UNIQUE constraint on ``idempotency_key``
    plus the IntegrityError-recovery branch in ``submit_job`` collapse
    every concurrent caller onto one row.

    NOTE: We use ``monkeypatch.setattr`` (process-wide for the test
    duration) rather than ``with patch(...)`` inside each thread, because
    ``unittest.mock.patch`` is NOT thread-safe — concurrent enter/exit
    races leave the module attribute swapped permanently if two threads
    overlap, which leaks the mock into later tests in the same session.
    """

    def fake_dispatch(_job_id):
        return "thread-task-id"

    monkeypatch.setattr(
        "app.core.job_runner._dispatch_to_celery",
        fake_dispatch,
    )

    def submit_sync() -> str:
        async def _run() -> str:
            jr = await submit_job(
                kind="test.noop",
                payload={},
                idempotency_key="threaded-key",
                session_factory=session_factory,
            )
            return str(jr.id)

        # Use a fresh loop per thread and tear it down explicitly so
        # we do not leak event-loop state into other tests in the same
        # pytest session.
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_run())
        finally:
            loop.close()

    with ThreadPoolExecutor(max_workers=5) as pool:
        ids = list(pool.map(lambda _: submit_sync(), range(5)))

    # Every thread must observe the same JobRun id.
    assert len(set(ids)) == 1

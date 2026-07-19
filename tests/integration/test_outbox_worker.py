import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.application.outbox_worker import OutboxWorker
from app.infrastructure.database.models import OutboxEvent
from app.infrastructure.database.outbox_store import OutboxStore

pytestmark = pytest.mark.integration


class RecordingPublisher:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.ids: list[str] = []

    async def publish(self, event_id: str, event_type: str, payload: dict[str, object]) -> None:
        if self.fail:
            raise RuntimeError("queue unavailable")
        self.ids.append(event_id)


async def test_concurrent_workers_claim_an_event_once(migrated_database_url: str) -> None:
    engine = create_async_engine(migrated_database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    event = OutboxEvent(
        id=uuid4(),
        aggregate_type="booking_operation",
        aggregate_id=uuid4(),
        event_type="booking.confirmed",
        payload={"safe": "value"},
        status="pending",
        attempts=0,
        available_at=now,
    )
    async with sessions() as session, session.begin():
        session.add(event)
    publisher = RecordingPublisher()
    try:
        counts = await asyncio.gather(
            *(OutboxWorker(OutboxStore(sessions), publisher).run_once(now=now) for _ in range(8))
        )
        async with sessions() as session:
            stored = await session.get(OutboxEvent, event.id)
        assert sum(counts) == 1
        assert publisher.ids == [str(event.id)]
        assert stored is not None
        assert stored.status == "published"
        assert stored.attempts == 1
    finally:
        await engine.dispose()


async def test_publish_failure_is_rescheduled_without_losing_event(
    migrated_database_url: str,
) -> None:
    engine = create_async_engine(migrated_database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    event = OutboxEvent(
        id=uuid4(),
        aggregate_type="follow_up",
        aggregate_id=uuid4(),
        event_type="follow_up.created",
        payload={},
        status="pending",
        attempts=0,
        available_at=now,
    )
    async with sessions() as session, session.begin():
        session.add(event)
    try:
        assert (
            await OutboxWorker(OutboxStore(sessions), RecordingPublisher(fail=True)).run_once(
                now=now
            )
            == 0
        )
        async with sessions() as session:
            stored = await session.get(OutboxEvent, event.id)
        assert stored is not None
        assert stored.status == "pending"
        assert stored.available_at >= now + timedelta(seconds=5)
        assert stored.last_error == "publish_failed"
    finally:
        await engine.dispose()

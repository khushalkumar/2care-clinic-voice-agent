import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.infrastructure.database.replay_store import PostgresReplayStore

pytestmark = pytest.mark.integration


async def test_only_one_concurrent_request_can_claim_an_event_id(
    migrated_database_url: str,
) -> None:
    engine = create_async_engine(migrated_database_url)
    store = PostgresReplayStore(async_sessionmaker(engine, expire_on_commit=False))
    expires_at = datetime.now(UTC) + timedelta(minutes=5)
    try:
        results = await asyncio.gather(*(store.claim("same-event", expires_at) for _ in range(12)))
    finally:
        await engine.dispose()

    assert results.count(True) == 1
    assert results.count(False) == 11


async def test_expired_event_id_can_be_claimed_again(migrated_database_url: str) -> None:
    engine = create_async_engine(migrated_database_url)
    store = PostgresReplayStore(async_sessionmaker(engine, expire_on_commit=False))
    try:
        assert await store.claim("expired-event", datetime.now(UTC) - timedelta(seconds=1))
        assert await store.claim("expired-event", datetime.now(UTC) + timedelta(minutes=5))
    finally:
        await engine.dispose()

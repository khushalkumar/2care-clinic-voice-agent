import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

pytestmark = pytest.mark.integration


def _store_api():
    try:
        from app.infrastructure.database.booking_store import (
            BookingStore,
            ReservationRequest,
            SlotAlreadyReserved,
        )
    except ImportError:
        pytest.fail("atomic booking store is not implemented")
    return BookingStore, ReservationRequest, SlotAlreadyReserved


def _request(reservation_request, idempotency_key: str, practitioner: str = "nadia_zainab"):
    start = datetime(2026, 7, 20, 9, 0, tzinfo=UTC)
    return reservation_request(
        idempotency_key=idempotency_key,
        practitioner_key=practitioner,
        reserved_from=start,
        reserved_until=start + timedelta(minutes=70),
        expires_at=datetime.now(UTC) + timedelta(minutes=2),
    )


@pytest.mark.asyncio
async def test_reservation_commits_operation_slot_and_outbox_atomically(migrated_database_url):
    booking_store, reservation_request, _ = _store_api()
    engine = create_async_engine(migrated_database_url)
    store = booking_store(async_sessionmaker(engine, expire_on_commit=False))
    before_reservation = datetime.now(UTC)
    try:
        result = await store.reserve(_request(reservation_request, "atomic-1"))
        async with engine.connect() as connection:
            counts = {
                table: await connection.scalar(text(f"SELECT count(*) FROM {table}"))
                for table in ("booking_operations", "slot_reservations", "outbox_events")
            }
            outbox_available_at = await connection.scalar(
                text("SELECT available_at FROM outbox_events")
            )
    finally:
        await engine.dispose()

    assert result.replayed is False
    assert counts == {
        "booking_operations": 1,
        "slot_reservations": 1,
        "outbox_events": 1,
    }
    assert before_reservation <= outbox_available_at <= datetime.now(UTC)


@pytest.mark.asyncio
async def test_idempotent_replay_returns_original_operation_without_new_rows(migrated_database_url):
    booking_store, reservation_request, _ = _store_api()
    engine = create_async_engine(migrated_database_url)
    store = booking_store(async_sessionmaker(engine, expire_on_commit=False))
    request = _request(reservation_request, "replay-1")
    try:
        original = await store.reserve(request)
        replay = await store.reserve(request)
        async with engine.connect() as connection:
            operation_count = await connection.scalar(
                text("SELECT count(*) FROM booking_operations")
            )
            outbox_count = await connection.scalar(text("SELECT count(*) FROM outbox_events"))
    finally:
        await engine.dispose()

    assert replay.operation_id == original.operation_id
    assert replay.replayed is True
    assert operation_count == 1
    assert outbox_count == 1


@pytest.mark.asyncio
async def test_slot_conflict_rolls_back_losing_operation_and_outbox(migrated_database_url):
    booking_store, reservation_request, slot_already_reserved = _store_api()
    engine = create_async_engine(migrated_database_url)
    store = booking_store(async_sessionmaker(engine, expire_on_commit=False))
    try:
        await store.reserve(_request(reservation_request, "winner"))
        with pytest.raises(slot_already_reserved):
            await store.reserve(_request(reservation_request, "loser"))
        async with engine.connect() as connection:
            operation_count = await connection.scalar(
                text("SELECT count(*) FROM booking_operations")
            )
            outbox_count = await connection.scalar(text("SELECT count(*) FROM outbox_events"))
    finally:
        await engine.dispose()

    assert operation_count == 1
    assert outbox_count == 1


@pytest.mark.asyncio
async def test_concurrent_idempotent_requests_share_one_operation(migrated_database_url):
    booking_store, reservation_request, _ = _store_api()
    engine = create_async_engine(migrated_database_url)
    store = booking_store(async_sessionmaker(engine, expire_on_commit=False))
    request = _request(reservation_request, "concurrent-replay")
    try:
        results = await asyncio.gather(*(store.reserve(request) for _ in range(10)))
        async with engine.connect() as connection:
            operation_count = await connection.scalar(
                text("SELECT count(*) FROM booking_operations")
            )
            reservation_count = await connection.scalar(
                text("SELECT count(*) FROM slot_reservations")
            )
            outbox_count = await connection.scalar(text("SELECT count(*) FROM outbox_events"))
    finally:
        await engine.dispose()

    assert len({result.operation_id for result in results}) == 1
    assert sum(result.replayed for result in results) == 9
    assert (operation_count, reservation_count, outbox_count) == (1, 1, 1)

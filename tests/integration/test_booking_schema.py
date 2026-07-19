import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import asyncpg
import pytest

pytestmark = pytest.mark.integration


def _asyncpg_url(database_url: str) -> str:
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


@pytest.mark.asyncio
async def test_baseline_migration_creates_booking_outbox_and_reservation_tables(
    migrated_database_url,
):
    connection = await asyncpg.connect(_asyncpg_url(migrated_database_url))
    try:
        tables = await connection.fetch(
            """
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public'
            """
        )
        constraints = await connection.fetch(
            """
            SELECT conname
            FROM pg_constraint
            WHERE connamespace = 'public'::regnamespace
            """
        )
    finally:
        await connection.close()

    assert {row["tablename"] for row in tables} >= {
        "booking_operations",
        "slot_reservations",
        "outbox_events",
    }
    assert {row["conname"] for row in constraints} >= {
        "uq_booking_operations_idempotency_key",
        "no_overlapping_practitioner_reservations",
    }


@pytest.mark.asyncio
async def test_twenty_concurrent_reservations_allow_exactly_one_winner(
    migrated_database_url,
):
    url = _asyncpg_url(migrated_database_url)
    start = datetime(2026, 7, 20, 9, 0, tzinfo=UTC)
    end = start + timedelta(minutes=70)

    async def reserve_once(attempt: int) -> bool:
        connection = await asyncpg.connect(url)
        operation_id = uuid4()
        try:
            async with connection.transaction():
                await connection.execute(
                    """
                    INSERT INTO booking_operations
                        (id, operation_type, idempotency_key, status, version)
                    VALUES ($1, 'book', $2, 'received', 1)
                    """,
                    operation_id,
                    f"race-{attempt}",
                )
                await connection.execute(
                    """
                    INSERT INTO slot_reservations
                        (id, booking_operation_id, practitioner_key, reserved_from,
                         reserved_until, status, expires_at)
                    VALUES ($1, $2, 'manjiri_arvind', $3, $4, 'held', $5)
                    """,
                    uuid4(),
                    operation_id,
                    start,
                    end,
                    datetime.now(UTC) + timedelta(minutes=2),
                )
            return True
        except (asyncpg.ExclusionViolationError, asyncpg.DeadlockDetectedError):
            return False
        finally:
            await connection.close()

    results = await asyncio.gather(*(reserve_once(attempt) for attempt in range(20)))

    assert results.count(True) == 1
    assert results.count(False) == 19

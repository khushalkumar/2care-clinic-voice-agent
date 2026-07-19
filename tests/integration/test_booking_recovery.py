from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.application.availability_token import AvailabilityTokenService
from app.application.booking_reconciler import BookingReconciler
from app.application.booking_service import BookingService
from app.infrastructure.database.booking_store import BookingStore
from app.infrastructure.database.models import BookingOperation, MockPmsAppointment
from app.infrastructure.pms.mock import (
    FailureKind,
    FailurePlan,
    MockPmsGateway,
    seed_mock_pms,
)

pytestmark = pytest.mark.integration


async def test_unknown_create_is_reconciled_without_a_duplicate(
    migrated_database_url: str,
) -> None:
    engine = create_async_engine(migrated_database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await seed_mock_pms(sessions)
    now = datetime.now(UTC)
    stable_pms = MockPmsGateway(sessions)
    failing_pms = MockPmsGateway(
        sessions, failure_plan=FailurePlan.once(FailureKind.TIMEOUT_AFTER_WRITE)
    )
    service = BookingService(
        failing_pms,
        BookingStore(sessions),
        AvailabilityTokenService(b"t" * 32, clock=lambda: now),
        clock=lambda: now,
    )
    try:
        offered = await service.search_availability(
            call_id="recovery-call",
            business_id="jayanagar",
            practitioner_ids=["nadia-zainab"],
            appointment_type_id="follow-up",
            starts_at=datetime(2026, 7, 23, 4, 30, tzinfo=UTC),
            ends_at=datetime(2026, 7, 23, 5, 0, tzinfo=UTC),
        )
        pending = await service.book(
            call_id="recovery-call",
            patient_id="aarav-sharma",
            full_name="Aarav Sharma",
            availability_token=offered[0].availability_token,
            idempotency_key="recover-create-1",
        )
        assert pending.status == "pending_verification"

        reconciled = await BookingReconciler(stable_pms, BookingStore(sessions)).run_once()

        async with sessions() as session:
            operation = await session.scalar(
                select(BookingOperation).where(
                    BookingOperation.idempotency_key == "recover-create-1"
                )
            )
            appointment_count = len((await session.scalars(select(MockPmsAppointment))).all())
        assert reconciled == 1
        assert operation is not None
        assert operation.status == "confirmed"
        assert appointment_count == 1
    finally:
        await engine.dispose()

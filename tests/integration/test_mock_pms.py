import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.application.ports.pms import (
    CreateAppointment,
    PmsConflict,
    PmsRateLimited,
    PmsTransientError,
    PmsUnknownOutcome,
    PmsValidationError,
)
from app.infrastructure.pms.mock import FailureKind, FailurePlan, MockPmsGateway, seed_mock_pms

pytestmark = pytest.mark.integration


@pytest.fixture
async def mock_pms(migrated_database_url: str) -> MockPmsGateway:
    engine = create_async_engine(migrated_database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await seed_mock_pms(sessions)
    gateway = MockPmsGateway(sessions)
    try:
        yield gateway
    finally:
        await engine.dispose()


async def test_patient_lookup_returns_every_patient_on_a_shared_phone(
    mock_pms: MockPmsGateway,
) -> None:
    patients = await mock_pms.find_patients_by_phone("+919900000001")

    assert [patient.full_name for patient in patients] == ["Aarav Sharma", "Meera Sharma"]


async def test_records_survive_a_new_gateway_instance(
    mock_pms: MockPmsGateway,
) -> None:
    businesses = await mock_pms.list_businesses()
    replacement = MockPmsGateway(mock_pms.session_factory)

    assert await replacement.list_businesses() == businesses


async def test_create_is_idempotent_and_rejects_a_competing_slot(
    mock_pms: MockPmsGateway,
) -> None:
    request = CreateAppointment(
        business_id="jayanagar",
        practitioner_id="nadia-zainab",
        appointment_type_id="initial-consultation",
        patient_id="aarav-sharma",
        starts_at=datetime(2026, 7, 20, 4, 30, tzinfo=UTC),
        ends_at=datetime(2026, 7, 20, 5, 30, tzinfo=UTC),
    )

    first = await mock_pms.create_appointment(request, idempotency_key="book-call-1")
    replay = await mock_pms.create_appointment(request, idempotency_key="book-call-1")

    assert replay == first
    with pytest.raises(PmsConflict, match="slot_unavailable"):
        await mock_pms.create_appointment(request, idempotency_key="book-call-2")


async def test_concurrent_create_has_one_winner(mock_pms: MockPmsGateway) -> None:
    request = CreateAppointment(
        business_id="indiranagar",
        practitioner_id="manjiri-arvind",
        appointment_type_id="initial-consultation",
        patient_id="aarav-sharma",
        starts_at=datetime(2026, 7, 20, 6, 30, tzinfo=UTC),
        ends_at=datetime(2026, 7, 20, 7, 30, tzinfo=UTC),
    )

    results = await asyncio.gather(
        *(
            mock_pms.create_appointment(request, idempotency_key=f"race-{index}")
            for index in range(8)
        ),
        return_exceptions=True,
    )

    assert sum(not isinstance(result, BaseException) for result in results) == 1
    assert sum(isinstance(result, PmsConflict) for result in results) == 7


async def test_timeout_after_write_is_reconciled_by_idempotency_key(
    mock_pms: MockPmsGateway,
) -> None:
    request = CreateAppointment(
        business_id="jayanagar",
        practitioner_id="sai-shweta-b",
        appointment_type_id="follow-up",
        patient_id="meera-sharma",
        starts_at=datetime(2026, 7, 20, 8, 30, tzinfo=UTC),
        ends_at=datetime(2026, 7, 20, 9, 0, tzinfo=UTC),
    )
    failing = MockPmsGateway(
        mock_pms.session_factory,
        failure_plan=FailurePlan.once(FailureKind.TIMEOUT_AFTER_WRITE),
    )

    with pytest.raises(PmsUnknownOutcome, match="timeout_after_write"):
        await failing.create_appointment(request, idempotency_key="uncertain-1")

    recovered = await mock_pms.create_appointment(request, idempotency_key="uncertain-1")
    assert recovered.patient_id == "meera-sharma"


async def test_read_contract_filters_and_returns_conflict_free_availability(
    mock_pms: MockPmsGateway,
) -> None:
    practitioners = await mock_pms.list_practitioners("jayanagar")
    appointment_types = await mock_pms.list_appointment_types()
    request = CreateAppointment(
        business_id="jayanagar",
        practitioner_id="nadia-zainab",
        appointment_type_id="initial-consultation",
        patient_id="aarav-sharma",
        starts_at=datetime(2026, 7, 20, 4, 30, tzinfo=UTC),
        ends_at=datetime(2026, 7, 20, 5, 30, tzinfo=UTC),
    )
    created = await mock_pms.create_appointment(request, idempotency_key="read-contract")

    slots = await mock_pms.search_available_times(
        business_id="jayanagar",
        practitioner_ids=["nadia-zainab"],
        appointment_type_id="initial-consultation",
        starts_at=datetime(2026, 7, 20, 3, 30, tzinfo=UTC),
        ends_at=datetime(2026, 7, 20, 7, 30, tzinfo=UTC),
    )
    conflicts = await mock_pms.find_conflicts(
        "nadia-zainab",
        datetime(2026, 7, 20, 5, 0, tzinfo=UTC),
        datetime(2026, 7, 20, 5, 15, tzinfo=UTC),
    )

    assert [item.name for item in practitioners] == ["Dr Nadia Zainab", "Dr Sai Shweta B"]
    assert [item.duration_minutes for item in appointment_types] == [30, 60]
    assert created in await mock_pms.get_patient_appointments("aarav-sharma")
    assert await mock_pms.get_appointment(created.id) == created
    assert conflicts == [created]
    assert all(
        slot.ends_at <= created.starts_at or slot.starts_at >= created.ends_at for slot in slots
    )
    assert slots


async def test_reschedule_and_cancel_are_idempotent(mock_pms: MockPmsGateway) -> None:
    original = await mock_pms.create_appointment(
        CreateAppointment(
            business_id="indiranagar",
            practitioner_id="silki-gupta",
            appointment_type_id="follow-up",
            patient_id="meera-sharma",
            starts_at=datetime(2026, 7, 21, 4, 30, tzinfo=UTC),
            ends_at=datetime(2026, 7, 21, 5, 0, tzinfo=UTC),
        ),
        idempotency_key="lifecycle-create",
    )

    moved = await mock_pms.reschedule_appointment(
        original.id,
        starts_at=datetime(2026, 7, 21, 5, 30, tzinfo=UTC),
        ends_at=datetime(2026, 7, 21, 6, 0, tzinfo=UTC),
        idempotency_key="lifecycle-move",
    )
    replayed_move = await mock_pms.reschedule_appointment(
        original.id,
        starts_at=datetime(2026, 7, 21, 5, 30, tzinfo=UTC),
        ends_at=datetime(2026, 7, 21, 6, 0, tzinfo=UTC),
        idempotency_key="lifecycle-move",
    )
    cancelled = await mock_pms.cancel_appointment(original.id, idempotency_key="lifecycle-cancel")
    replayed_cancel = await mock_pms.cancel_appointment(
        original.id, idempotency_key="lifecycle-cancel"
    )

    assert moved == replayed_move
    assert moved.starts_at == datetime(2026, 7, 21, 5, 30, tzinfo=UTC)
    assert cancelled == replayed_cancel
    assert cancelled.status == "cancelled"


@pytest.mark.parametrize(
    ("failure", "expected_error"),
    [
        (FailureKind.TIMEOUT_BEFORE_WRITE, PmsTransientError),
        (FailureKind.RATE_LIMITED, PmsRateLimited),
        (FailureKind.TRANSIENT, PmsTransientError),
        (FailureKind.VALIDATION, PmsValidationError),
        (FailureKind.CONFLICT, PmsConflict),
    ],
)
async def test_failure_injection_happens_before_a_write(
    mock_pms: MockPmsGateway,
    failure: FailureKind,
    expected_error: type[Exception],
) -> None:
    failing = MockPmsGateway(
        mock_pms.session_factory,
        failure_plan=FailurePlan.once(failure),
    )
    request = CreateAppointment(
        business_id="jayanagar",
        practitioner_id="nadia-zainab",
        appointment_type_id="follow-up",
        patient_id="aarav-sharma",
        starts_at=datetime(2026, 7, 22, 4, 30, tzinfo=UTC),
        ends_at=datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
    )

    with pytest.raises(expected_error):
        await failing.create_appointment(request, idempotency_key=f"failure-{failure}")

    assert await mock_pms.get_patient_appointments("aarav-sharma") == []


async def test_latency_injection_uses_the_configured_delay(
    mock_pms: MockPmsGateway,
) -> None:
    delays: list[float] = []

    async def sleep(delay: float) -> None:
        delays.append(delay)

    delayed = MockPmsGateway(
        mock_pms.session_factory,
        failure_plan=FailurePlan.once(FailureKind.LATENCY, delay_seconds=0.75),
        sleep=sleep,
    )
    request = CreateAppointment(
        business_id="jayanagar",
        practitioner_id="nadia-zainab",
        appointment_type_id="follow-up",
        patient_id="aarav-sharma",
        starts_at=datetime(2026, 7, 24, 4, 30, tzinfo=UTC),
        ends_at=datetime(2026, 7, 24, 5, 0, tzinfo=UTC),
    )

    appointment = await delayed.create_appointment(request, idempotency_key="delayed-1")

    assert appointment.status == "booked"
    assert delays == [0.75]

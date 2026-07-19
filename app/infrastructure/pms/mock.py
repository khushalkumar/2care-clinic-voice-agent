import asyncio
import hashlib
import json
from collections import deque
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.ports.pms import (
    Appointment,
    AppointmentType,
    AvailableTime,
    Business,
    CreateAppointment,
    Patient,
    PmsConflict,
    PmsRateLimited,
    PmsTransientError,
    PmsUnknownOutcome,
    PmsValidationError,
    Practitioner,
)
from app.infrastructure.database.models import (
    MockPmsAppointment,
    MockPmsAppointmentType,
    MockPmsBusiness,
    MockPmsMutation,
    MockPmsPatient,
    MockPmsPractitioner,
)


class FailureKind(StrEnum):
    LATENCY = "latency"
    TIMEOUT_BEFORE_WRITE = "timeout_before_write"
    TIMEOUT_AFTER_WRITE = "timeout_after_write"
    RATE_LIMITED = "rate_limited"
    TRANSIENT = "transient"
    VALIDATION = "validation"
    CONFLICT = "conflict"


class FailurePlan:
    def __init__(self, failures: Sequence[FailureKind] = (), *, delay_seconds: float = 0) -> None:
        self._failures = deque(failures)
        self.delay_seconds = delay_seconds
        self._lock = asyncio.Lock()

    @classmethod
    def once(cls, failure: FailureKind, *, delay_seconds: float = 0) -> "FailurePlan":
        return cls((failure,), delay_seconds=delay_seconds)

    async def take(self) -> FailureKind | None:
        async with self._lock:
            return self._failures.popleft() if self._failures else None


def _appointment(row: MockPmsAppointment) -> Appointment:
    return Appointment(
        id=row.id,
        business_id=row.business_id,
        practitioner_id=row.practitioner_id,
        appointment_type_id=row.appointment_type_id,
        patient_id=row.patient_id,
        starts_at=row.starts_at,
        ends_at=row.ends_at,
        status=row.status,
    )


def _fingerprint(request: CreateAppointment) -> str:
    value = {
        "business_id": request.business_id,
        "practitioner_id": request.practitioner_id,
        "appointment_type_id": request.appointment_type_id,
        "patient_id": request.patient_id,
        "starts_at": request.starts_at.isoformat(),
        "ends_at": request.ends_at.isoformat(),
    }
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


class MockPmsGateway:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        failure_plan: FailurePlan | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self.session_factory = session_factory
        self._failure_plan = failure_plan or FailurePlan()
        self._sleep = sleep or asyncio.sleep

    async def list_businesses(self) -> Sequence[Business]:
        async with self.session_factory() as session:
            rows = (
                await session.scalars(select(MockPmsBusiness).order_by(MockPmsBusiness.id))
            ).all()
        return [Business(row.id, row.name, row.timezone) for row in rows]

    async def list_practitioners(self, business_id: str) -> Sequence[Practitioner]:
        async with self.session_factory() as session:
            rows = (
                await session.scalars(
                    select(MockPmsPractitioner)
                    .where(MockPmsPractitioner.business_id == business_id)
                    .order_by(MockPmsPractitioner.name)
                )
            ).all()
        return [Practitioner(row.id, row.business_id, row.name) for row in rows]

    async def list_appointment_types(self) -> Sequence[AppointmentType]:
        async with self.session_factory() as session:
            rows = (
                await session.scalars(
                    select(MockPmsAppointmentType).order_by(MockPmsAppointmentType.duration_minutes)
                )
            ).all()
        return [AppointmentType(row.id, row.name, row.duration_minutes) for row in rows]

    async def find_patients_by_phone(self, phone_e164: str) -> Sequence[Patient]:
        async with self.session_factory() as session:
            rows = (
                await session.scalars(
                    select(MockPmsPatient)
                    .where(MockPmsPatient.phone_e164 == phone_e164)
                    .order_by(MockPmsPatient.full_name)
                )
            ).all()
        return [Patient(row.id, row.full_name, row.phone_e164) for row in rows]

    async def get_patient(self, patient_id: str) -> Patient | None:
        async with self.session_factory() as session:
            row = await session.get(MockPmsPatient, patient_id)
        return Patient(row.id, row.full_name, row.phone_e164) if row is not None else None

    async def get_patient_appointments(self, patient_id: str) -> Sequence[Appointment]:
        async with self.session_factory() as session:
            rows = (
                await session.scalars(
                    select(MockPmsAppointment)
                    .where(MockPmsAppointment.patient_id == patient_id)
                    .order_by(MockPmsAppointment.starts_at)
                )
            ).all()
        return [_appointment(row) for row in rows]

    async def search_available_times(
        self,
        *,
        business_id: str,
        practitioner_ids: Sequence[str],
        appointment_type_id: str,
        starts_at: datetime,
        ends_at: datetime,
    ) -> Sequence[AvailableTime]:
        async with self.session_factory() as session:
            appointment_type = await session.get(MockPmsAppointmentType, appointment_type_id)
            if appointment_type is None:
                raise PmsValidationError("appointment_type_not_found")
            practitioners = (
                await session.scalars(
                    select(MockPmsPractitioner).where(
                        MockPmsPractitioner.id.in_(practitioner_ids),
                        MockPmsPractitioner.business_id == business_id,
                    )
                )
            ).all()
            conflicts = (
                await session.scalars(
                    select(MockPmsAppointment).where(
                        MockPmsAppointment.practitioner_id.in_([item.id for item in practitioners]),
                        MockPmsAppointment.status == "booked",
                        MockPmsAppointment.starts_at < ends_at,
                        MockPmsAppointment.ends_at > starts_at,
                    )
                )
            ).all()

        duration = timedelta(minutes=appointment_type.duration_minutes)
        slots: list[AvailableTime] = []
        for practitioner in practitioners:
            candidate = starts_at
            practitioner_conflicts = [
                row for row in conflicts if row.practitioner_id == practitioner.id
            ]
            while candidate + duration <= ends_at:
                candidate_end = candidate + duration
                if not any(
                    row.starts_at < candidate_end and row.ends_at > candidate
                    for row in practitioner_conflicts
                ):
                    slots.append(
                        AvailableTime(
                            business_id=business_id,
                            practitioner_id=practitioner.id,
                            appointment_type_id=appointment_type_id,
                            starts_at=candidate,
                            ends_at=candidate_end,
                        )
                    )
                candidate += timedelta(minutes=30)
        return sorted(slots, key=lambda item: (item.starts_at, item.practitioner_id))

    async def create_appointment(
        self, request: CreateAppointment, *, idempotency_key: str
    ) -> Appointment:
        failure = await self._failure_plan.take()
        await self._apply_before_write(failure)
        fingerprint = _fingerprint(request)
        appointment_id = uuid4().hex
        try:
            async with self.session_factory() as session, session.begin():
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                    {"key": request.practitioner_id},
                )
                existing = await self._find_mutation(session, idempotency_key)
                if existing is not None:
                    if existing.request_fingerprint != fingerprint:
                        raise PmsValidationError("idempotency_key_reused")
                    appointment = await session.get(MockPmsAppointment, existing.appointment_id)
                    if appointment is None:
                        raise RuntimeError("mock PMS mutation references a missing appointment")
                    return _appointment(appointment)

                row = MockPmsAppointment(
                    id=appointment_id,
                    business_id=request.business_id,
                    practitioner_id=request.practitioner_id,
                    appointment_type_id=request.appointment_type_id,
                    patient_id=request.patient_id,
                    starts_at=request.starts_at,
                    ends_at=request.ends_at,
                    status="booked",
                )
                session.add(row)
                session.add(
                    MockPmsMutation(
                        idempotency_key=idempotency_key,
                        operation_type="create",
                        appointment_id=appointment_id,
                        request_fingerprint=fingerprint,
                    )
                )
                await session.flush()
        except IntegrityError as error:
            if "no_overlapping_mock_pms_appointments" in str(error):
                raise PmsConflict("slot_unavailable") from error
            raise

        if failure == FailureKind.TIMEOUT_AFTER_WRITE:
            raise PmsUnknownOutcome("timeout_after_write")
        return Appointment(
            id=appointment_id,
            business_id=request.business_id,
            practitioner_id=request.practitioner_id,
            appointment_type_id=request.appointment_type_id,
            patient_id=request.patient_id,
            starts_at=request.starts_at,
            ends_at=request.ends_at,
            status="booked",
        )

    async def reschedule_appointment(
        self,
        appointment_id: str,
        *,
        starts_at: datetime,
        ends_at: datetime,
        idempotency_key: str,
    ) -> Appointment:
        if starts_at.tzinfo is None or ends_at.tzinfo is None or ends_at <= starts_at:
            raise PmsValidationError("invalid_time_range")
        fingerprint = hashlib.sha256(
            f"{appointment_id}|{starts_at.isoformat()}|{ends_at.isoformat()}".encode()
        ).hexdigest()
        try:
            async with self.session_factory() as session, session.begin():
                row = await session.get(MockPmsAppointment, appointment_id)
                if row is None:
                    raise PmsValidationError("appointment_not_found")
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                    {"key": row.practitioner_id},
                )
                existing = await self._find_mutation(session, idempotency_key)
                if existing is not None:
                    if existing.request_fingerprint != fingerprint:
                        raise PmsValidationError("idempotency_key_reused")
                    return _appointment(row)
                row.starts_at = starts_at
                row.ends_at = ends_at
                session.add(
                    MockPmsMutation(
                        idempotency_key=idempotency_key,
                        operation_type="reschedule",
                        appointment_id=appointment_id,
                        request_fingerprint=fingerprint,
                    )
                )
                await session.flush()
                result = _appointment(row)
        except IntegrityError as error:
            if "no_overlapping_mock_pms_appointments" in str(error):
                raise PmsConflict("slot_unavailable") from error
            raise
        return result

    async def cancel_appointment(self, appointment_id: str, *, idempotency_key: str) -> Appointment:
        fingerprint = hashlib.sha256(f"cancel|{appointment_id}".encode()).hexdigest()
        async with self.session_factory() as session, session.begin():
            row = await session.get(MockPmsAppointment, appointment_id)
            if row is None:
                raise PmsValidationError("appointment_not_found")
            existing = await self._find_mutation(session, idempotency_key)
            if existing is not None:
                if existing.request_fingerprint != fingerprint:
                    raise PmsValidationError("idempotency_key_reused")
                return _appointment(row)
            row.status = "cancelled"
            session.add(
                MockPmsMutation(
                    idempotency_key=idempotency_key,
                    operation_type="cancel",
                    appointment_id=appointment_id,
                    request_fingerprint=fingerprint,
                )
            )
            await session.flush()
            return _appointment(row)

    async def get_appointment(self, appointment_id: str) -> Appointment | None:
        async with self.session_factory() as session:
            row = await session.get(MockPmsAppointment, appointment_id)
        return _appointment(row) if row is not None else None

    async def find_conflicts(
        self, practitioner_id: str, starts_at: datetime, ends_at: datetime
    ) -> Sequence[Appointment]:
        async with self.session_factory() as session:
            rows = (
                await session.scalars(
                    select(MockPmsAppointment)
                    .where(
                        MockPmsAppointment.practitioner_id == practitioner_id,
                        MockPmsAppointment.status == "booked",
                        MockPmsAppointment.starts_at < ends_at,
                        MockPmsAppointment.ends_at > starts_at,
                    )
                    .order_by(MockPmsAppointment.starts_at)
                )
            ).all()
        return [_appointment(row) for row in rows]

    async def _apply_before_write(self, failure: FailureKind | None) -> None:
        if failure == FailureKind.LATENCY:
            await self._sleep(self._failure_plan.delay_seconds)
        if failure == FailureKind.TIMEOUT_BEFORE_WRITE:
            raise PmsTransientError("timeout_before_write")
        if failure == FailureKind.RATE_LIMITED:
            raise PmsRateLimited("rate_limited", retry_after_seconds=30)
        if failure == FailureKind.TRANSIENT:
            raise PmsTransientError("upstream_500")
        if failure == FailureKind.VALIDATION:
            raise PmsValidationError("injected_validation_error")
        if failure == FailureKind.CONFLICT:
            raise PmsConflict("injected_conflict")

    @staticmethod
    async def _find_mutation(session: AsyncSession, idempotency_key: str) -> MockPmsMutation | None:
        return await session.get(MockPmsMutation, idempotency_key)


async def seed_mock_pms(session_factory: async_sessionmaker[AsyncSession]) -> None:
    tables_and_rows = (
        (
            MockPmsBusiness,
            [
                {
                    "id": "indiranagar",
                    "name": "Physiotattva Indiranagar",
                    "timezone": "Asia/Kolkata",
                },
                {"id": "jayanagar", "name": "Physiotattva Jayanagar", "timezone": "Asia/Kolkata"},
            ],
        ),
        (
            MockPmsPractitioner,
            [
                {"id": "nadia-zainab", "business_id": "jayanagar", "name": "Dr Nadia Zainab"},
                {"id": "sai-shweta-b", "business_id": "jayanagar", "name": "Dr Sai Shweta B"},
                {"id": "manjiri-arvind", "business_id": "indiranagar", "name": "Dr Manjiri Arvind"},
                {"id": "silki-gupta", "business_id": "indiranagar", "name": "Dr Silki Gupta"},
            ],
        ),
        (
            MockPmsAppointmentType,
            [
                {
                    "id": "initial-consultation",
                    "name": "Initial consultation",
                    "duration_minutes": 60,
                },
                {"id": "follow-up", "name": "Follow-up", "duration_minutes": 30},
            ],
        ),
        (
            MockPmsPatient,
            [
                {"id": "aarav-sharma", "full_name": "Aarav Sharma", "phone_e164": "+919900000001"},
                {"id": "meera-sharma", "full_name": "Meera Sharma", "phone_e164": "+919900000001"},
            ],
        ),
    )
    async with session_factory() as session, session.begin():
        for model, rows in tables_and_rows:
            await session.execute(insert(model).values(rows).on_conflict_do_nothing())

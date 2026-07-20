from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.application.availability_token import (
    AvailabilityClaim,
    AvailabilityTokenService,
)
from app.application.ports.pms import (
    Appointment,
    AvailableTime,
    CreateAppointment,
    PmsError,
    PmsGateway,
    PmsUnknownOutcome,
)
from app.infrastructure.database.booking_store import BookingStore, ReservationRequest


@dataclass(frozen=True, slots=True)
class OfferedSlot:
    slot: AvailableTime
    availability_token: str


@dataclass(frozen=True, slots=True)
class BookingOutcome:
    status: str
    operation_id: str
    appointment: Appointment | None


class IdentityVerificationError(Exception):
    pass


class BookingService:
    def __init__(
        self,
        pms: PmsGateway,
        booking_store: BookingStore,
        token_service: AvailabilityTokenService,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._pms = pms
        self._booking_store = booking_store
        self._tokens = token_service
        self._clock = clock or (lambda: datetime.now(UTC))

    async def search_availability(
        self,
        *,
        session_id: str,
        business_id: str,
        practitioner_ids: Sequence[str],
        appointment_type_id: str,
        starts_at: datetime,
        ends_at: datetime,
    ) -> list[OfferedSlot]:
        slots = await self._pms.search_available_times(
            business_id=business_id,
            practitioner_ids=practitioner_ids,
            appointment_type_id=appointment_type_id,
            starts_at=starts_at,
            ends_at=ends_at,
        )
        query_id = uuid4().hex
        expires_at = self._clock() + timedelta(minutes=5)
        return [
            OfferedSlot(
                slot,
                self._tokens.issue(
                    AvailabilityClaim(
                        session_id=session_id,
                        query_id=query_id,
                        business_id=slot.business_id,
                        practitioner_id=slot.practitioner_id,
                        appointment_type_id=slot.appointment_type_id,
                        starts_at=slot.starts_at,
                        ends_at=slot.ends_at,
                        expires_at=expires_at,
                    )
                ),
            )
            for slot in slots
        ]

    async def book(
        self,
        *,
        session_id: str,
        patient_id: str,
        full_name: str,
        availability_token: str,
        idempotency_key: str,
    ) -> BookingOutcome:
        claim = self._tokens.verify(availability_token, expected_session_id=session_id)
        patient = await self._pms.get_patient(patient_id)
        supplied_name = " ".join(full_name.casefold().split())
        expected_name = " ".join(patient.full_name.casefold().split()) if patient else None
        if not supplied_name or supplied_name != expected_name:
            raise IdentityVerificationError("full_name_mismatch")
        reservation = await self._booking_store.reserve(
            ReservationRequest(
                idempotency_key=idempotency_key,
                practitioner_key=claim.practitioner_id,
                reserved_from=claim.starts_at,
                reserved_until=claim.ends_at,
                expires_at=self._clock() + timedelta(minutes=5),
                pms_payload={
                    "business_id": claim.business_id,
                    "practitioner_id": claim.practitioner_id,
                    "appointment_type_id": claim.appointment_type_id,
                    "patient_id": patient_id,
                    "starts_at": claim.starts_at.isoformat(),
                    "ends_at": claim.ends_at.isoformat(),
                },
            )
        )
        request = CreateAppointment(
            business_id=claim.business_id,
            practitioner_id=claim.practitioner_id,
            appointment_type_id=claim.appointment_type_id,
            patient_id=patient_id,
            starts_at=claim.starts_at,
            ends_at=claim.ends_at,
        )
        try:
            appointment = await self._pms.create_appointment(
                request, idempotency_key=idempotency_key
            )
        except PmsUnknownOutcome as error:
            await self._booking_store.mark_pending_verification(
                reservation.operation_id, error.code
            )
            return BookingOutcome("pending_verification", str(reservation.operation_id), None)
        except PmsError as error:
            await self._booking_store.mark_failed(reservation.operation_id, error.code)
            raise
        await self._booking_store.mark_confirmed(reservation.operation_id, appointment.id)
        return BookingOutcome("confirmed", str(reservation.operation_id), appointment)

    async def list_patient_appointments(self, patient_id: str) -> Sequence[Appointment]:
        return await self._pms.get_patient_appointments(patient_id)

    async def reschedule(
        self,
        *,
        appointment_id: str,
        starts_at: datetime,
        ends_at: datetime,
        idempotency_key: str,
    ) -> Appointment:
        return await self._pms.reschedule_appointment(
            appointment_id,
            starts_at=starts_at,
            ends_at=ends_at,
            idempotency_key=idempotency_key,
        )

    async def cancel(self, *, appointment_id: str, idempotency_key: str) -> Appointment:
        return await self._pms.cancel_appointment(appointment_id, idempotency_key=idempotency_key)

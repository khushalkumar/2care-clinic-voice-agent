import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.application.availability_token import (
    AvailabilityClaim,
    AvailabilityTokenError,
    AvailabilityTokenService,
)
from app.application.ports.pms import (
    Appointment,
    AvailableTime,
    CreateAppointment,
    PmsError,
    PmsGateway,
    PmsUnknownOutcome,
    PmsValidationError,
)
from app.infrastructure.database.booking_store import BookingStore, ReservationRequest

CLINIC_TIMEZONE = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True, slots=True)
class OfferedSlot:
    slot: AvailableTime
    availability_token: str


@dataclass(frozen=True, slots=True)
class AvailabilitySearchTarget:
    business_id: str
    practitioner_ids: tuple[str, ...]
    appointment_type_id: str


@dataclass(frozen=True, slots=True)
class AvailabilitySearchResult:
    slots: tuple[OfferedSlot, ...]
    target_count: int
    total_slot_count: int

    @property
    def truncated(self) -> bool:
        return self.total_slot_count > len(self.slots)


@dataclass(frozen=True, slots=True)
class BookingOutcome:
    status: str
    operation_id: str
    appointment: Appointment | None


class IdentityVerificationError(Exception):
    pass


def apply_same_day_buffer(
    requested_start: datetime,
    *,
    now: datetime,
    buffer: timedelta,
    timezone: ZoneInfo = CLINIC_TIMEZONE,
) -> datetime:
    if requested_start.astimezone(timezone).date() != now.astimezone(timezone).date():
        return requested_start
    minimum_start = now + buffer
    if requested_start < minimum_start:
        return minimum_start.astimezone(requested_start.tzinfo)
    return requested_start


class BookingService:
    MAX_SEARCH_TARGETS = 4
    MAX_VOICE_SLOTS = 3

    def __init__(
        self,
        pms: PmsGateway,
        booking_store: BookingStore,
        token_service: AvailabilityTokenService,
        *,
        clock: Callable[[], datetime] | None = None,
        same_day_buffer: timedelta = timedelta(minutes=60),
    ) -> None:
        self._pms = pms
        self._booking_store = booking_store
        self._tokens = token_service
        self._clock = clock or (lambda: datetime.now(UTC))
        self._same_day_buffer = same_day_buffer

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
        effective_starts_at = apply_same_day_buffer(
            starts_at,
            now=self._clock(),
            buffer=self._same_day_buffer,
        )
        if effective_starts_at >= ends_at:
            return []
        slots = await self._pms.search_available_times(
            business_id=business_id,
            practitioner_ids=practitioner_ids,
            appointment_type_id=appointment_type_id,
            starts_at=effective_starts_at,
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

    async def search_availability_across_targets(
        self,
        *,
        session_id: str,
        targets: Sequence[AvailabilitySearchTarget],
        starts_at: datetime,
        ends_at: datetime,
    ) -> AvailabilitySearchResult:
        if not 1 <= len(targets) <= self.MAX_SEARCH_TARGETS:
            raise ValueError("availability search requires between 1 and 4 targets")

        if any(not target.practitioner_ids for target in targets):
            raise ValueError("availability search target requires practitioners")

        unique_targets = tuple(dict.fromkeys(targets))
        target_results = await asyncio.gather(
            *(
                self.search_availability(
                    session_id=session_id,
                    business_id=target.business_id,
                    practitioner_ids=target.practitioner_ids,
                    appointment_type_id=target.appointment_type_id,
                    starts_at=starts_at,
                    ends_at=ends_at,
                )
                for target in unique_targets
            )
        )
        offered = [item for target_result in target_results for item in target_result]

        unique = {
            (
                item.slot.business_id,
                item.slot.practitioner_id,
                item.slot.appointment_type_id,
                item.slot.starts_at,
                item.slot.ends_at,
            ): item
            for item in offered
        }
        ranked = sorted(
            unique.values(),
            key=lambda item: (
                item.slot.starts_at,
                item.slot.ends_at,
                item.slot.business_id,
                item.slot.practitioner_id,
                item.slot.appointment_type_id,
            ),
        )
        return AvailabilitySearchResult(
            slots=tuple(ranked[: self.MAX_VOICE_SLOTS]),
            target_count=len(unique_targets),
            total_slot_count=len(ranked),
        )

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
        session_id: str,
        patient_id: str,
        availability_token: str,
        appointment_id: str,
        idempotency_key: str,
    ) -> BookingOutcome:
        claim = self._tokens.verify(availability_token, expected_session_id=session_id)
        existing = await self._pms.get_appointment(appointment_id)
        self._verify_owned_appointment(existing, patient_id)
        assert existing is not None
        if existing.status != "booked":
            raise PmsValidationError("appointment_not_active")
        if (
            existing.business_id != claim.business_id
            or existing.practitioner_id != claim.practitioner_id
            or existing.appointment_type_id != claim.appointment_type_id
        ):
            raise AvailabilityTokenError("appointment_slot_mismatch")
        reservation = await self._booking_store.reserve(
            ReservationRequest(
                idempotency_key=idempotency_key,
                practitioner_key=claim.practitioner_id,
                reserved_from=claim.starts_at,
                reserved_until=claim.ends_at,
                expires_at=self._clock() + timedelta(minutes=5),
                operation_type="reschedule",
                pms_payload={
                    "operation_type": "reschedule",
                    "appointment_id": appointment_id,
                    "patient_id": patient_id,
                    "business_id": claim.business_id,
                    "practitioner_id": claim.practitioner_id,
                    "appointment_type_id": claim.appointment_type_id,
                    "starts_at": claim.starts_at.isoformat(),
                    "ends_at": claim.ends_at.isoformat(),
                },
            )
        )
        try:
            appointment = await self._pms.reschedule_appointment(
                appointment_id,
                starts_at=claim.starts_at,
                ends_at=claim.ends_at,
                idempotency_key=idempotency_key,
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
        await self._booking_store.release_prior_reservations(
            appointment.id, except_operation_id=reservation.operation_id
        )
        return BookingOutcome("confirmed", str(reservation.operation_id), appointment)

    async def cancel(
        self, *, patient_id: str, appointment_id: str, idempotency_key: str
    ) -> BookingOutcome:
        existing = await self._pms.get_appointment(appointment_id)
        self._verify_owned_appointment(existing, patient_id)
        mutation = await self._booking_store.start_mutation(
            operation_type="cancel",
            idempotency_key=idempotency_key,
            remote_appointment_id=appointment_id,
            request_payload={
                "operation_type": "cancel",
                "appointment_id": appointment_id,
                "patient_id": patient_id,
            },
        )
        try:
            appointment = await self._pms.cancel_appointment(
                appointment_id, idempotency_key=idempotency_key
            )
        except PmsUnknownOutcome as error:
            await self._booking_store.mark_pending_verification(mutation.operation_id, error.code)
            return BookingOutcome("pending_verification", str(mutation.operation_id), None)
        except PmsError as error:
            await self._booking_store.mark_failed(mutation.operation_id, error.code)
            raise
        await self._booking_store.mark_confirmed(mutation.operation_id, appointment.id)
        await self._booking_store.release_prior_reservations(
            appointment.id, except_operation_id=mutation.operation_id
        )
        return BookingOutcome("confirmed", str(mutation.operation_id), appointment)

    @staticmethod
    def _verify_owned_appointment(appointment: Appointment | None, patient_id: str) -> None:
        if appointment is None:
            raise LookupError("appointment not found")
        if appointment.patient_id != patient_id:
            raise IdentityVerificationError("appointment_patient_mismatch")

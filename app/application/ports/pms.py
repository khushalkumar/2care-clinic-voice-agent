from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


def _require_aware(*values: datetime) -> None:
    if any(value.tzinfo is None or value.utcoffset() is None for value in values):
        raise ValueError("appointment times must be timezone-aware")


@dataclass(frozen=True, slots=True)
class Business:
    id: str
    name: str
    timezone: str


@dataclass(frozen=True, slots=True)
class Practitioner:
    id: str
    business_id: str
    name: str


@dataclass(frozen=True, slots=True)
class AppointmentType:
    id: str
    name: str
    duration_minutes: int


@dataclass(frozen=True, slots=True)
class Patient:
    id: str
    full_name: str
    phone_e164: str


@dataclass(frozen=True, slots=True)
class AvailableTime:
    business_id: str
    practitioner_id: str
    appointment_type_id: str
    starts_at: datetime
    ends_at: datetime

    def __post_init__(self) -> None:
        _require_aware(self.starts_at, self.ends_at)
        if self.ends_at <= self.starts_at:
            raise ValueError("available time must end after it starts")


@dataclass(frozen=True, slots=True)
class Appointment:
    id: str
    business_id: str
    practitioner_id: str
    appointment_type_id: str
    patient_id: str
    starts_at: datetime
    ends_at: datetime
    status: str

    def __post_init__(self) -> None:
        _require_aware(self.starts_at, self.ends_at)
        if self.ends_at <= self.starts_at:
            raise ValueError("appointment must end after it starts")


@dataclass(frozen=True, slots=True)
class CreateAppointment:
    business_id: str
    practitioner_id: str
    appointment_type_id: str
    patient_id: str
    starts_at: datetime
    ends_at: datetime

    def __post_init__(self) -> None:
        _require_aware(self.starts_at, self.ends_at)
        if self.ends_at <= self.starts_at:
            raise ValueError("appointment must end after it starts")


class PmsError(Exception):
    retryable = False
    outcome_unknown = False

    def __init__(
        self, code: str, *, status_code: int | None = None, path: str | None = None
    ) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.path = path


class PmsConflict(PmsError):
    pass


class PmsValidationError(PmsError):
    pass


class PmsTransientError(PmsError):
    retryable = True


class PmsRateLimited(PmsTransientError):
    def __init__(self, code: str, retry_after_seconds: int) -> None:
        super().__init__(code)
        self.retry_after_seconds = retry_after_seconds


class PmsUnknownOutcome(PmsTransientError):
    outcome_unknown = True


class PmsGateway(Protocol):
    async def list_businesses(self) -> Sequence[Business]: ...

    async def list_practitioners(self, business_id: str) -> Sequence[Practitioner]: ...

    async def list_appointment_types(self) -> Sequence[AppointmentType]: ...

    async def find_patients_by_phone(self, phone_e164: str) -> Sequence[Patient]: ...

    async def get_patient(self, patient_id: str) -> Patient | None: ...

    async def get_patient_appointments(self, patient_id: str) -> Sequence[Appointment]: ...

    async def search_available_times(
        self,
        *,
        business_id: str,
        practitioner_ids: Sequence[str],
        appointment_type_id: str,
        starts_at: datetime,
        ends_at: datetime,
    ) -> Sequence[AvailableTime]: ...

    async def create_appointment(
        self, request: CreateAppointment, *, idempotency_key: str
    ) -> Appointment: ...

    async def reschedule_appointment(
        self,
        appointment_id: str,
        *,
        starts_at: datetime,
        ends_at: datetime,
        idempotency_key: str,
    ) -> Appointment: ...

    async def cancel_appointment(
        self, appointment_id: str, *, idempotency_key: str
    ) -> Appointment: ...

    async def get_appointment(self, appointment_id: str) -> Appointment | None: ...

    async def find_conflicts(
        self, practitioner_id: str, starts_at: datetime, ends_at: datetime
    ) -> Sequence[Appointment]: ...

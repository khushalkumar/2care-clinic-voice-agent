from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from app.application.ports.pms import (
    Appointment,
    AppointmentType,
    AvailableTime,
    Business,
    CreateAppointment,
    Patient,
    PmsTransientError,
    PmsValidationError,
    Practitioner,
)


class ClinikoReader(Protocol):
    async def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]: ...


class ClinikoGateway:
    def __init__(
        self,
        client: ClinikoReader,
        *,
        timezone: str = "Asia/Kolkata",
        patient_ids_by_phone: dict[str, str] | None = None,
    ) -> None:
        self._client = client
        self._timezone = ZoneInfo(timezone)
        self._patient_ids_by_phone = patient_ids_by_phone or {}

    async def list_businesses(self) -> Sequence[Business]:
        return [
            Business(
                id=str(item["id"]),
                name=str(item["business_name"]),
                timezone=self._timezone.key,
            )
            for item in await self._get_all("businesses", collection="businesses")
        ]

    async def list_practitioners(self, business_id: str) -> Sequence[Practitioner]:
        practitioners = await self._get_all("practitioners", collection="practitioners")
        return [
            Practitioner(
                id=str(item["id"]),
                business_id=business_id,
                name=" ".join(
                    part
                    for part in (
                        str(item.get("first_name", "")),
                        str(item.get("last_name", "")),
                    )
                    if part
                ),
            )
            for item in practitioners
        ]

    async def list_appointment_types(self) -> Sequence[AppointmentType]:
        return [
            AppointmentType(
                id=str(item["id"]),
                name=str(item["name"]),
                duration_minutes=_positive_int(item.get("duration_in_minutes")),
            )
            for item in await self._get_all("appointment_types", collection="appointment_types")
        ]

    async def find_patients_by_phone(self, phone_e164: str) -> Sequence[Patient]:
        patient_id = self._patient_ids_by_phone.get(phone_e164)
        if patient_id is None:
            return []
        patient = await self.get_patient(patient_id)
        if patient is None or patient.phone_e164 != phone_e164:
            return []
        return [patient]

    async def create_patient(
        self, *, full_name: str, phone_e164: str, idempotency_key: str
    ) -> Patient:
        parts = full_name.split()
        if len(parts) < 2:
            raise PmsValidationError("full_name_required")
        payload = await self._client.request(
            "POST",
            "patients",
            json={
                "first_name": parts[0],
                "last_name": " ".join(parts[1:]),
                "patient_phone_numbers": [{"number": phone_e164, "phone_type": "Mobile"}],
            },
        )
        del idempotency_key
        return _patient(payload)

    async def get_patient(self, patient_id: str) -> Patient | None:
        try:
            payload = await self._client.request("GET", f"patients/{patient_id}")
        except PmsValidationError:
            return None
        return _patient(payload)

    async def get_patient_appointments(self, patient_id: str) -> Sequence[Appointment]:
        appointments = await self._get_all(
            "individual_appointments",
            collection="individual_appointments",
            params={"q[]": f"patient_id:={patient_id}", "per_page": 100},
        )
        return sorted(
            (_appointment(item) for item in appointments), key=lambda item: item.starts_at
        )

    async def find_conflicts(
        self, practitioner_id: str, starts_at: datetime, ends_at: datetime
    ) -> Sequence[Appointment]:
        appointments = await self._get_all(
            "individual_appointments",
            collection="individual_appointments",
            params={
                "q[]": [
                    f"practitioner_id:={practitioner_id}",
                    f"starts_at:<{ends_at.isoformat()}",
                    f"ends_at:>{starts_at.isoformat()}",
                ],
                "per_page": 100,
            },
        )
        return [_appointment(item) for item in appointments]

    async def search_available_times(
        self,
        *,
        business_id: str,
        practitioner_ids: Sequence[str],
        appointment_type_id: str,
        starts_at: datetime,
        ends_at: datetime,
    ) -> Sequence[AvailableTime]:
        if starts_at.tzinfo is None or ends_at.tzinfo is None:
            raise ValueError("availability window must be timezone-aware")
        if ends_at <= starts_at:
            raise ValueError("availability window must end after it starts")

        appointment_type = await self._client.request(
            "GET", f"appointment_types/{appointment_type_id}"
        )
        duration_minutes = appointment_type.get("duration_in_minutes")
        if not isinstance(duration_minutes, int) or duration_minutes <= 0:
            raise PmsTransientError("malformed_appointment_type")
        eligible_practitioners = {
            str(item["id"])
            for item in await self._get_all(
                f"appointment_types/{appointment_type_id}/practitioners",
                collection="practitioners",
            )
            if isinstance(item.get("id"), str) and item["id"]
        }

        slots: dict[tuple[str, datetime], AvailableTime] = {}
        for practitioner_id in practitioner_ids:
            if practitioner_id not in eligible_practitioners:
                continue
            for chunk_start, chunk_end in _date_chunks(starts_at, ends_at, self._timezone):
                path = (
                    f"businesses/{business_id}/practitioners/{practitioner_id}/"
                    f"appointment_types/{appointment_type_id}/available_times"
                )
                for item in await self._available_times(
                    path,
                    params={
                        "from": chunk_start.isoformat(),
                        "to": chunk_end.isoformat(),
                        "per_page": 100,
                    },
                ):
                    starts = _parse_start(item)
                    if starts < starts_at or starts >= ends_at:
                        continue
                    slot = AvailableTime(
                        business_id=business_id,
                        practitioner_id=practitioner_id,
                        appointment_type_id=appointment_type_id,
                        starts_at=starts,
                        ends_at=starts + timedelta(minutes=duration_minutes),
                    )
                    slots[(practitioner_id, starts)] = slot
        return sorted(slots.values(), key=lambda slot: (slot.starts_at, slot.practitioner_id))

    async def create_appointment(
        self, request: CreateAppointment, *, idempotency_key: str
    ) -> Appointment:
        payload = await self._client.request(
            "POST",
            "individual_appointments",
            json={
                "appointment_type_id": request.appointment_type_id,
                "business_id": request.business_id,
                "ends_at": request.ends_at.isoformat(),
                "notes": f"2care-operation:{idempotency_key}",
                "patient_id": request.patient_id,
                "practitioner_id": request.practitioner_id,
                "starts_at": request.starts_at.isoformat(),
            },
        )
        return _appointment(payload)

    async def reschedule_appointment(
        self,
        appointment_id: str,
        *,
        starts_at: datetime,
        ends_at: datetime,
        idempotency_key: str,
    ) -> Appointment:
        del idempotency_key
        payload = await self._client.request(
            "PATCH",
            f"individual_appointments/{appointment_id}",
            json={"starts_at": starts_at.isoformat(), "ends_at": ends_at.isoformat()},
        )
        return _appointment(payload)

    async def cancel_appointment(self, appointment_id: str, *, idempotency_key: str) -> Appointment:
        del idempotency_key
        await self._client.request(
            "PATCH",
            f"individual_appointments/{appointment_id}/cancel",
            json={"cancellation_reason": 50},
        )
        appointment = await self.get_appointment(appointment_id)
        if appointment is None:
            raise PmsTransientError("cancelled_appointment_not_found")
        return appointment

    async def get_appointment(self, appointment_id: str) -> Appointment | None:
        try:
            payload = await self._client.request("GET", f"individual_appointments/{appointment_id}")
        except PmsValidationError:
            return None
        return _appointment(payload)

    async def _available_times(
        self, path: str, *, params: dict[str, object]
    ) -> list[dict[str, Any]]:
        slots: list[dict[str, Any]] = []
        next_path: str | None = path
        next_params: dict[str, object] | None = params
        while next_path:
            payload = await self._client.request("GET", next_path, params=next_params)
            page = payload.get("available_times")
            if not isinstance(page, list) or not all(isinstance(item, dict) for item in page):
                raise PmsTransientError("malformed_available_times")
            slots.extend(page)
            links = payload.get("links")
            next_value = links.get("next") if isinstance(links, dict) else None
            next_path = str(next_value) if next_value else None
            next_params = None
        return slots

    async def _get_all(
        self, path: str, *, collection: str, params: dict[str, object] | None = None
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        next_path: str | None = path
        next_params = params
        while next_path:
            payload = await self._client.request("GET", next_path, params=next_params)
            page = payload.get(collection)
            if not isinstance(page, list) or not all(isinstance(item, dict) for item in page):
                raise PmsTransientError("malformed_response")
            items.extend(page)
            links = payload.get("links")
            next_value = links.get("next") if isinstance(links, dict) else None
            next_path = str(next_value) if next_value else None
            next_params = None
        return items


def _date_chunks(
    starts_at: datetime, ends_at: datetime, timezone: ZoneInfo
) -> list[tuple[date, date]]:
    start_date = starts_at.astimezone(timezone).date()
    final_date = (ends_at - timedelta(microseconds=1)).astimezone(timezone).date()
    chunks: list[tuple[date, date]] = []
    current = start_date
    while current <= final_date:
        chunk_end = min(current + timedelta(days=6), final_date)
        chunks.append((current, chunk_end))
        current = chunk_end + timedelta(days=1)
    return chunks


def _parse_start(value: dict[str, Any]) -> datetime:
    raw = value.get("appointment_start")
    return _parse_timestamp(raw, error_code="malformed_available_time")


def _positive_int(value: object) -> int:
    if not isinstance(value, int) or value <= 0:
        raise PmsTransientError("malformed_appointment_type")
    return value


def _parse_timestamp(raw: object, *, error_code: str) -> datetime:
    if not isinstance(raw, str):
        raise PmsTransientError(error_code)
    try:
        result = datetime.fromisoformat(raw)
    except ValueError as error:
        raise PmsTransientError(error_code) from error
    if result.tzinfo is None or result.utcoffset() is None:
        raise PmsValidationError(error_code)
    return result.astimezone(UTC)


def _patient(payload: dict[str, Any]) -> Patient:
    identifier = payload.get("id")
    first_name = payload.get("first_name")
    last_name = payload.get("last_name")
    phones = payload.get("patient_phone_numbers")
    name_parts = (identifier, first_name, last_name)
    if not all(isinstance(value, str) and value for value in name_parts):
        raise PmsTransientError("malformed_patient")
    assert isinstance(identifier, str)
    assert isinstance(first_name, str)
    assert isinstance(last_name, str)
    if not isinstance(phones, list) or not phones or not isinstance(phones[0], dict):
        raise PmsTransientError("malformed_patient")
    phone = phones[0].get("normalized_number")
    if not isinstance(phone, str) or not phone:
        raise PmsTransientError("malformed_patient")
    return Patient(
        id=identifier,
        full_name=f"{first_name} {last_name}",
        phone_e164=f"+{phone.lstrip('+')}",
    )


def _appointment(payload: dict[str, Any]) -> Appointment:
    identifier = payload.get("id")
    if not isinstance(identifier, str) or not identifier:
        raise PmsTransientError("malformed_appointment")
    return Appointment(
        id=identifier,
        business_id=_linked_id(payload, "business"),
        practitioner_id=_linked_id(payload, "practitioner"),
        appointment_type_id=_linked_id(payload, "appointment_type"),
        patient_id=_linked_id(payload, "patient"),
        starts_at=_parse_timestamp(payload.get("starts_at"), error_code="malformed_appointment"),
        ends_at=_parse_timestamp(payload.get("ends_at"), error_code="malformed_appointment"),
        status="cancelled" if payload.get("cancelled_at") else "booked",
    )


def _linked_id(payload: dict[str, Any], field: str) -> str:
    resource = payload.get(field)
    links = resource.get("links") if isinstance(resource, dict) else None
    self_link = links.get("self") if isinstance(links, dict) else None
    if not isinstance(self_link, str) or not self_link.rsplit("/", 1)[-1]:
        raise PmsTransientError("malformed_appointment")
    return self_link.rsplit("/", 1)[-1]

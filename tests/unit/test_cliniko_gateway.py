from datetime import UTC, datetime
from typing import Any

from app.application.ports.pms import CreateAppointment, Patient
from app.infrastructure.pms.cliniko_gateway import ClinikoGateway


class RecordingTransport:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict[str, Any]]] = []

    async def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        self.requests.append((method, path, kwargs))
        if path == "appointment_types/type-1":
            return {"id": "type-1", "duration_in_minutes": 30}
        if path == "appointment_types/type-1/practitioners":
            return {
                "practitioners": [{"id": "practitioner-1"}],
                "links": {"next": None},
            }
        if path.endswith("available_times"):
            request_dates = kwargs["params"]
            if request_dates["from"] == "2026-07-20":
                return {
                    "available_times": [{"appointment_start": "2026-07-20T09:00:00+05:30"}],
                    "links": {"next": "/v1/page-two"},
                }
            return {
                "available_times": [{"appointment_start": "2026-07-27T09:00:00+05:30"}],
                "links": {"next": None},
            }
        if path == "/v1/page-two":
            return {
                "available_times": [{"appointment_start": "2026-07-20T09:00:00+05:30"}],
                "links": {"next": None},
            }
        raise AssertionError(f"unexpected request: {method} {path}")


async def test_search_availability_chunks_paginates_and_deduplicates_slots() -> None:
    transport = RecordingTransport()
    gateway = ClinikoGateway(transport)  # type: ignore[arg-type]

    slots = await gateway.search_available_times(
        business_id="business-1",
        practitioner_ids=["practitioner-1"],
        appointment_type_id="type-1",
        starts_at=datetime(2026, 7, 20, 0, 0, tzinfo=UTC),
        ends_at=datetime(2026, 7, 29, 0, 0, tzinfo=UTC),
    )

    assert [(slot.starts_at.isoformat(), slot.ends_at.isoformat()) for slot in slots] == [
        ("2026-07-20T03:30:00+00:00", "2026-07-20T04:00:00+00:00"),
        ("2026-07-27T03:30:00+00:00", "2026-07-27T04:00:00+00:00"),
    ]
    availability_requests = [
        request for request in transport.requests if request[1].endswith("available_times")
    ]
    assert [request[2]["params"] for request in availability_requests] == [
        {"from": "2026-07-20", "to": "2026-07-26", "per_page": 100},
        {"from": "2026-07-27", "to": "2026-07-29", "per_page": 100},
    ]


async def test_search_availability_uses_practitioners_enabled_for_appointment_type() -> None:
    class AppointmentTypeTransport:
        def __init__(self) -> None:
            self.availability_practitioners: list[str] = []

        async def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
            if path == "appointment_types/type-1":
                return {"id": "type-1", "duration_in_minutes": 30}
            if path == "appointment_types/type-1/practitioners":
                return {
                    "practitioners": [{"id": "practitioner-1"}],
                    "links": {"next": None},
                }
            if path.endswith("available_times"):
                self.availability_practitioners.append(path.split("/")[3])
                return {"available_times": [], "links": {"next": None}}
            raise AssertionError(f"unexpected request: {method} {path} {kwargs}")

    transport = AppointmentTypeTransport()
    await ClinikoGateway(transport).search_available_times(
        business_id="business-1",
        practitioner_ids=["practitioner-1", "practitioner-2"],
        appointment_type_id="type-1",
        starts_at=datetime(2026, 7, 20, 0, 0, tzinfo=UTC),
        ends_at=datetime(2026, 7, 21, 0, 0, tzinfo=UTC),
    )

    assert transport.availability_practitioners == ["practitioner-1"]


async def test_create_appointment_adds_a_reconciliation_marker() -> None:
    class CreateTransport:
        def __init__(self) -> None:
            self.json: dict[str, Any] | None = None

        async def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
            if (method, path) == ("POST", "individual_appointments"):
                self.json = kwargs["json"]
                return {
                    "id": "appointment-1",
                    "starts_at": "2026-07-20T09:00:00+05:30",
                    "ends_at": "2026-07-20T09:30:00+05:30",
                    "business": {
                        "links": {"self": "https://api.au5.cliniko.com/v1/businesses/business-1"}
                    },
                    "practitioner": {
                        "links": {
                            "self": "https://api.au5.cliniko.com/v1/practitioners/practitioner-1"
                        }
                    },
                    "appointment_type": {
                        "links": {"self": "https://api.au5.cliniko.com/v1/appointment_types/type-1"}
                    },
                    "patient": {
                        "links": {"self": "https://api.au5.cliniko.com/v1/patients/patient-1"}
                    },
                    "cancelled_at": None,
                }
            raise AssertionError(f"unexpected request: {method} {path}")

    transport = CreateTransport()
    gateway = ClinikoGateway(transport)  # type: ignore[arg-type]

    appointment = await gateway.create_appointment(
        CreateAppointment(
            business_id="business-1",
            practitioner_id="practitioner-1",
            appointment_type_id="type-1",
            patient_id="patient-1",
            starts_at=datetime(2026, 7, 20, 3, 30, tzinfo=UTC),
            ends_at=datetime(2026, 7, 20, 4, 0, tzinfo=UTC),
        ),
        idempotency_key="operation-1",
    )

    assert appointment.id == "appointment-1"
    assert transport.json == {
        "appointment_type_id": "type-1",
        "business_id": "business-1",
        "ends_at": "2026-07-20T04:00:00+00:00",
        "notes": "2care-operation:operation-1",
        "patient_id": "patient-1",
        "practitioner_id": "practitioner-1",
        "starts_at": "2026-07-20T03:30:00+00:00",
    }


async def test_cancel_appointment_retrieves_the_final_cancelled_state() -> None:
    class CancelTransport:
        def __init__(self) -> None:
            self.requests: list[tuple[str, str, dict[str, Any]]] = []

        async def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
            self.requests.append((method, path, kwargs))
            if (method, path) == ("PATCH", "individual_appointments/appointment-1/cancel"):
                return {}
            if (method, path) == ("GET", "individual_appointments/appointment-1"):
                return {
                    "id": "appointment-1",
                    "starts_at": "2026-07-20T09:00:00+05:30",
                    "ends_at": "2026-07-20T09:30:00+05:30",
                    "business": {
                        "links": {"self": "https://api.au5.cliniko.com/v1/businesses/business-1"}
                    },
                    "practitioner": {
                        "links": {
                            "self": "https://api.au5.cliniko.com/v1/practitioners/practitioner-1"
                        }
                    },
                    "appointment_type": {
                        "links": {"self": "https://api.au5.cliniko.com/v1/appointment_types/type-1"}
                    },
                    "patient": {
                        "links": {"self": "https://api.au5.cliniko.com/v1/patients/patient-1"}
                    },
                    "cancelled_at": "2026-07-19T09:00:00+05:30",
                }
            raise AssertionError(f"unexpected request: {method} {path}")

    transport = CancelTransport()
    appointment = await ClinikoGateway(transport).cancel_appointment(  # type: ignore[arg-type]
        "appointment-1", idempotency_key="operation-2"
    )

    assert appointment.status == "cancelled"
    assert transport.requests[0] == (
        "PATCH",
        "individual_appointments/appointment-1/cancel",
        {"json": {"cancellation_reason": 50}},
    )


async def test_patient_lookup_uses_the_configured_phone_mapping() -> None:
    class PatientTransport:
        async def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
            assert (method, path, kwargs) == ("GET", "patients/patient-1", {})
            return {
                "id": "patient-1",
                "first_name": "Demo",
                "last_name": "Patient",
                "patient_phone_numbers": [{"normalized_number": "919999999999"}],
            }

    gateway = ClinikoGateway(
        PatientTransport(), patient_ids_by_phone={"+919999999999": "patient-1"}
    )

    assert await gateway.find_patients_by_phone("+919999999999") == [
        Patient(id="patient-1", full_name="Demo Patient", phone_e164="+919999999999")
    ]


async def test_create_patient_sends_name_and_phone_to_cliniko() -> None:
    class CreatePatientTransport:
        def __init__(self) -> None:
            self.json: dict[str, Any] | None = None

        async def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
            assert (method, path) == ("POST", "patients")
            self.json = kwargs["json"]
            return {
                "id": "patient-new",
                "first_name": "Krishal",
                "last_name": "Kumar",
                "patient_phone_numbers": [{"normalized_number": "919900000099"}],
            }

    transport = CreatePatientTransport()
    patient = await ClinikoGateway(transport).create_patient(
        full_name="Krishal Kumar",
        phone_e164="+919900000099",
        idempotency_key="new-patient-1",
    )

    assert patient == Patient(
        id="patient-new", full_name="Krishal Kumar", phone_e164="+919900000099"
    )
    assert transport.json == {
        "first_name": "Krishal",
        "last_name": "Kumar",
        "patient_phone_numbers": [{"number": "+919900000099", "phone_type": "Mobile"}],
    }


async def test_patient_appointments_use_the_documented_patient_filter() -> None:
    class AppointmentTransport:
        async def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
            assert (method, path) == ("GET", "individual_appointments")
            assert kwargs == {"params": {"q[]": "patient_id:=patient-1", "per_page": 100}}
            return {
                "individual_appointments": [
                    {
                        "id": "appointment-1",
                        "starts_at": "2026-07-20T09:00:00+05:30",
                        "ends_at": "2026-07-20T09:30:00+05:30",
                        "business": {
                            "links": {
                                "self": "https://api.au5.cliniko.com/v1/businesses/business-1"
                            }
                        },
                        "practitioner": {
                            "links": {
                                "self": "https://api.au5.cliniko.com/v1/practitioners/practitioner-1"
                            }
                        },
                        "appointment_type": {
                            "links": {
                                "self": "https://api.au5.cliniko.com/v1/appointment_types/type-1"
                            }
                        },
                        "patient": {
                            "links": {"self": "https://api.au5.cliniko.com/v1/patients/patient-1"}
                        },
                        "cancelled_at": None,
                    }
                ],
                "links": {"next": None},
            }

    appointments = await ClinikoGateway(AppointmentTransport()).get_patient_appointments(  # type: ignore[arg-type]
        "patient-1"
    )

    assert [appointment.id for appointment in appointments] == ["appointment-1"]


async def test_conflict_lookup_filters_by_practitioner_and_overlap() -> None:
    class ConflictTransport:
        async def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
            assert (method, path) == ("GET", "individual_appointments")
            assert kwargs == {
                "params": {
                    "q[]": [
                        "practitioner_id:=practitioner-1",
                        "starts_at:<2026-07-20T04:00:00+00:00",
                        "ends_at:>2026-07-20T03:30:00+00:00",
                    ],
                    "per_page": 100,
                }
            }
            return {"individual_appointments": [], "links": {"next": None}}

    conflicts = await ClinikoGateway(ConflictTransport()).find_conflicts(  # type: ignore[arg-type]
        "practitioner-1",
        datetime(2026, 7, 20, 3, 30, tzinfo=UTC),
        datetime(2026, 7, 20, 4, 0, tzinfo=UTC),
    )

    assert conflicts == []

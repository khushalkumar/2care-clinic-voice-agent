from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.app import (
    CancelAppointmentRequest,
    PatientAppointmentsRequest,
    RescheduleAppointmentRequest,
)


def test_patient_mutation_requests_use_session_bound_identity() -> None:
    session_id = uuid4()

    appointments = PatientAppointmentsRequest(
        session_id=session_id,
        patient_id="patient-1",
        full_name="Aarav Sharma",
    )
    cancellation = CancelAppointmentRequest(
        session_id=session_id,
        patient_id="patient-1",
        full_name="Aarav Sharma",
        appointment_id="appointment-1",
        idempotency_key="cancel-1",
    )

    assert appointments.session_id == session_id
    assert cancellation.session_id == session_id


def test_reschedule_requires_a_fresh_availability_token() -> None:
    with pytest.raises(ValidationError):
        RescheduleAppointmentRequest(
            session_id=uuid4(),
            patient_id="patient-1",
            full_name="Aarav Sharma",
            appointment_id="appointment-1",
            starts_at="2026-07-20T08:30:00Z",
            ends_at="2026-07-20T09:30:00Z",
            idempotency_key="move-1",
        )


def test_legacy_call_id_is_not_accepted_for_patient_mutations() -> None:
    with pytest.raises(ValidationError):
        PatientAppointmentsRequest(call_id="retell-call-1", patient_id="patient-1")

from datetime import UTC, datetime

from app.application.ports.pms import (
    Appointment,
    PmsConflict,
    PmsRateLimited,
    PmsTransientError,
    PmsUnknownOutcome,
)


def test_appointment_requires_timezone_aware_times() -> None:
    try:
        Appointment(
            id="appointment-1",
            business_id="business-1",
            practitioner_id="practitioner-1",
            appointment_type_id="type-1",
            patient_id="patient-1",
            starts_at=datetime(2026, 7, 20, 9, 0),
            ends_at=datetime(2026, 7, 20, 10, 0, tzinfo=UTC),
            status="booked",
        )
    except ValueError as error:
        assert str(error) == "appointment times must be timezone-aware"
    else:
        raise AssertionError("naive appointment time was accepted")


def test_gateway_errors_expose_stable_retry_and_outcome_semantics() -> None:
    assert not PmsConflict("occupied").retryable
    assert PmsTransientError("upstream_500").retryable

    rate_limited = PmsRateLimited("quota", retry_after_seconds=12)
    assert rate_limited.retryable
    assert rate_limited.retry_after_seconds == 12

    unknown = PmsUnknownOutcome("timeout_after_write")
    assert unknown.retryable
    assert unknown.outcome_unknown

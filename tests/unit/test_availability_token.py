from datetime import UTC, datetime, timedelta

import pytest

from app.application.availability_token import (
    AvailabilityClaim,
    AvailabilityTokenError,
    AvailabilityTokenService,
)


def _claim(now: datetime) -> AvailabilityClaim:
    return AvailabilityClaim(
        session_id="00000000-0000-0000-0000-000000000001",
        query_id="query-1",
        business_id="jayanagar",
        practitioner_id="nadia-zainab",
        appointment_type_id="initial-consultation",
        starts_at=now + timedelta(minutes=20),
        ends_at=now + timedelta(minutes=80),
        expires_at=now + timedelta(minutes=5),
    )


def test_token_round_trip_is_bound_to_call_session() -> None:
    now = datetime(2026, 7, 18, 8, 0, tzinfo=UTC)
    service = AvailabilityTokenService(b"a" * 32, clock=lambda: now)

    token = service.issue(_claim(now))

    assert service.verify(
        token,
        expected_session_id="00000000-0000-0000-0000-000000000001",
    ) == _claim(now)
    with pytest.raises(AvailabilityTokenError, match="session_mismatch"):
        service.verify(token, expected_session_id="00000000-0000-0000-0000-000000000002")


def test_token_rejects_tampering_and_expiry() -> None:
    now = datetime(2026, 7, 18, 8, 0, tzinfo=UTC)
    service = AvailabilityTokenService(b"b" * 32, clock=lambda: now)
    token = service.issue(_claim(now))

    with pytest.raises(AvailabilityTokenError, match="invalid_signature"):
        service.verify(
            token[:-1] + ("A" if token[-1] != "A" else "B"),
            expected_session_id="00000000-0000-0000-0000-000000000001",
        )

    expired = AvailabilityTokenService(b"b" * 32, clock=lambda: now + timedelta(minutes=6))
    with pytest.raises(AvailabilityTokenError, match="expired"):
        expired.verify(
            token,
            expected_session_id="00000000-0000-0000-0000-000000000001",
        )


def test_token_secret_must_be_cryptographically_useful() -> None:
    with pytest.raises(ValueError, match="at least 32 bytes"):
        AvailabilityTokenService(b"short")

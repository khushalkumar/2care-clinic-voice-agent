import base64
import hashlib
import hmac
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any


class AvailabilityTokenError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class AvailabilityClaim:
    call_id: str
    query_id: str
    business_id: str
    practitioner_id: str
    appointment_type_id: str
    starts_at: datetime
    ends_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        values = (self.starts_at, self.ends_at, self.expires_at)
        if any(value.tzinfo is None or value.utcoffset() is None for value in values):
            raise ValueError("availability claim times must be timezone-aware")


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


class AvailabilityTokenService:
    def __init__(
        self,
        secret: bytes,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if len(secret) < 32:
            raise ValueError("availability token secret must be at least 32 bytes")
        self._secret = secret
        self._clock = clock or (lambda: datetime.now(UTC))

    def issue(self, claim: AvailabilityClaim) -> str:
        payload: dict[str, Any] = asdict(claim)
        for field in ("starts_at", "ends_at", "expires_at"):
            payload[field] = payload[field].isoformat()
        encoded_payload = _encode(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        )
        signature = _encode(
            hmac.new(self._secret, encoded_payload.encode(), hashlib.sha256).digest()
        )
        return f"{encoded_payload}.{signature}"

    def verify(self, token: str, *, expected_call_id: str) -> AvailabilityClaim:
        try:
            encoded_payload, supplied_signature = token.split(".", maxsplit=1)
        except ValueError as error:
            raise AvailabilityTokenError("malformed") from error
        expected_signature = _encode(
            hmac.new(self._secret, encoded_payload.encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise AvailabilityTokenError("invalid_signature")
        try:
            payload = json.loads(_decode(encoded_payload))
            claim = AvailabilityClaim(
                call_id=payload["call_id"],
                query_id=payload["query_id"],
                business_id=payload["business_id"],
                practitioner_id=payload["practitioner_id"],
                appointment_type_id=payload["appointment_type_id"],
                starts_at=datetime.fromisoformat(payload["starts_at"]),
                ends_at=datetime.fromisoformat(payload["ends_at"]),
                expires_at=datetime.fromisoformat(payload["expires_at"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise AvailabilityTokenError("malformed") from error
        if claim.expires_at <= self._clock():
            raise AvailabilityTokenError("expired")
        if claim.call_id != expected_call_id:
            raise AvailabilityTokenError("call_mismatch")
        return claim

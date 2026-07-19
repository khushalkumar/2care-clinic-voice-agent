import hashlib
import hmac
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol


class RequestAuthError(Exception):
    pass


class ReplayStore(Protocol):
    async def claim(self, event_id: str, expires_at: datetime) -> bool: ...


@dataclass(frozen=True, slots=True)
class SignedRequest:
    timestamp: str
    event_id: str
    method: str
    path: str
    body: bytes

    def canonical(self) -> bytes:
        body_hash = hashlib.sha256(self.body).hexdigest()
        return "\n".join(
            (self.timestamp, self.event_id, self.method.upper(), self.path, body_hash)
        ).encode()


class RequestAuthenticator:
    def __init__(
        self,
        secret: bytes,
        replay_store: ReplayStore,
        *,
        clock: Callable[[], datetime] | None = None,
        replay_window: timedelta = timedelta(minutes=5),
    ) -> None:
        if len(secret) < 32:
            raise ValueError("request authentication secret must be at least 32 bytes")
        self._secret = secret
        self._replay_store = replay_store
        self._clock = clock or (lambda: datetime.now(UTC))
        self._replay_window = replay_window

    def sign(self, request: SignedRequest) -> str:
        return hmac.new(self._secret, request.canonical(), hashlib.sha256).hexdigest()

    async def verify(self, request: SignedRequest, signature: str) -> None:
        expected = self.sign(request)
        if not hmac.compare_digest(signature, expected):
            raise RequestAuthError("invalid_signature")
        try:
            sent_at = datetime.fromtimestamp(int(request.timestamp), tz=UTC)
        except (ValueError, OverflowError) as error:
            raise RequestAuthError("invalid_timestamp") from error
        now = self._clock()
        if abs(now - sent_at) > self._replay_window:
            raise RequestAuthError("expired")
        claimed = await self._replay_store.claim(
            request.event_id, expires_at=now + self._replay_window
        )
        if not claimed:
            raise RequestAuthError("replayed")

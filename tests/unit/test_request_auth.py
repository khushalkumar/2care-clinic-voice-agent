from datetime import UTC, datetime

import pytest

from app.application.request_auth import (
    RequestAuthenticator,
    RequestAuthError,
    SignedRequest,
)


class MemoryReplayStore:
    def __init__(self) -> None:
        self.ids: set[str] = set()

    async def claim(self, event_id: str, expires_at: datetime) -> bool:
        if event_id in self.ids:
            return False
        self.ids.add(event_id)
        return True


async def test_valid_signature_is_accepted_once() -> None:
    now = datetime(2026, 7, 18, 8, 0, tzinfo=UTC)
    store = MemoryReplayStore()
    auth = RequestAuthenticator(b"s" * 32, store, clock=lambda: now)
    request = SignedRequest(
        timestamp="1784361600",
        event_id="event-1",
        method="POST",
        path="/v1/tools/search-availability",
        body=b'{"call_id":"call-1"}',
    )
    signature = auth.sign(request)

    await auth.verify(request, signature)
    with pytest.raises(RequestAuthError, match="replayed"):
        await auth.verify(request, signature)


async def test_tampered_body_does_not_claim_event_id() -> None:
    now = datetime(2026, 7, 18, 8, 0, tzinfo=UTC)
    store = MemoryReplayStore()
    auth = RequestAuthenticator(b"s" * 32, store, clock=lambda: now)
    original = SignedRequest("1784361600", "event-2", "POST", "/v1/tools/book", b"one")
    tampered = SignedRequest("1784361600", "event-2", "POST", "/v1/tools/book", b"two")

    with pytest.raises(RequestAuthError, match="invalid_signature"):
        await auth.verify(tampered, auth.sign(original))

    await auth.verify(original, auth.sign(original))


async def test_timestamp_outside_replay_window_is_rejected() -> None:
    now = datetime(2026, 7, 18, 8, 10, tzinfo=UTC)
    auth = RequestAuthenticator(b"s" * 32, MemoryReplayStore(), clock=lambda: now)
    request = SignedRequest("1784361600", "event-3", "POST", "/v1/tools/book", b"{}")

    with pytest.raises(RequestAuthError, match="expired"):
        await auth.verify(request, auth.sign(request))

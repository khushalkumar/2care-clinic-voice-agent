import base64
from collections.abc import Awaitable, Callable

import httpx
import pytest

from app.application.ports.pms import (
    PmsConflict,
    PmsTransientError,
    PmsUnknownOutcome,
    PmsValidationError,
)
from app.infrastructure.pms.cliniko import ClinikoConfig, ClinikoTransport


def _client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    sleep: Callable[[float], Awaitable[None]] | None = None,
) -> ClinikoTransport:
    return ClinikoTransport(
        ClinikoConfig(
            api_key="test-secret-key",
            shard="au4",
            user_agent="2care-assignment/0.1 contact@example.com",
        ),
        transport=httpx.MockTransport(handler),
        sleep=sleep,
        now=lambda: 100.0,
    )


async def test_required_auth_user_agent_and_pagination_are_applied() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "businesses": [{"id": "1"}],
                    "links": {"next": "/v1/businesses?page=2"},
                },
            )
        return httpx.Response(200, json={"businesses": [{"id": "2"}], "links": {"next": None}})

    result = await _client(handler).get_all("businesses", collection="businesses")

    expected_auth = base64.b64encode(b"test-secret-key:").decode()
    assert result == [{"id": "1"}, {"id": "2"}]
    assert requests[0].url == "https://api.au4.cliniko.com/v1/businesses"
    assert requests[0].headers["Authorization"] == f"Basic {expected_auth}"
    assert requests[0].headers["User-Agent"] == "2care-assignment/0.1 contact@example.com"
    assert requests[1].url == "https://api.au4.cliniko.com/v1/businesses?page=2"


async def test_429_waits_until_rate_limit_reset_then_retries() -> None:
    attempts = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"X-RateLimit-Reset": "102"})
        return httpx.Response(200, json={"businesses": [], "links": {"next": None}})

    async def sleep(delay: float) -> None:
        delays.append(delay)

    assert await _client(handler, sleep=sleep).get_all("businesses", collection="businesses") == []
    assert attempts == 2
    assert delays == [2.0]


@pytest.mark.parametrize(
    ("status", "expected"),
    [(400, PmsValidationError), (409, PmsConflict), (500, PmsTransientError)],
)
async def test_http_errors_map_without_leaking_credentials(
    status: int, expected: type[Exception]
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="vendor details")

    with pytest.raises(expected) as caught:
        await _client(handler).get_all("businesses", collection="businesses")

    assert "test-secret-key" not in str(caught.value)


async def test_post_timeout_is_an_unknown_outcome_without_a_retry() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("uncertain", request=request)

    with pytest.raises(PmsUnknownOutcome):
        await _client(handler).request("POST", "individual_appointments", json={"patient_id": "1"})

    assert attempts == 1


async def test_no_content_response_returns_an_empty_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    assert await _client(handler).request("PATCH", "individual_appointments/1/cancel") == {}

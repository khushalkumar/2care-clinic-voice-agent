import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx

from app.application.ports.pms import (
    PmsConflict,
    PmsRateLimited,
    PmsTransientError,
    PmsUnknownOutcome,
    PmsValidationError,
)

LOGGER = logging.getLogger("voice_agent.pms")


@dataclass(frozen=True, slots=True)
class ClinikoConfig:
    api_key: str
    shard: str
    user_agent: str
    max_retries: int = 2

    def __post_init__(self) -> None:
        if not self.shard.isalnum():
            raise ValueError("Cliniko shard must be alphanumeric")
        if "@" not in self.user_agent:
            raise ValueError("Cliniko User-Agent must contain a contact address")


class ClinikoTransport:
    def __init__(
        self,
        config: ClinikoConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        now: Callable[[], float] | None = None,
    ) -> None:
        self._config = config
        self._sleep = sleep or asyncio.sleep
        self._now = now or time.time
        self._client = httpx.AsyncClient(
            base_url=f"https://api.{config.shard}.cliniko.com/v1/",
            auth=httpx.BasicAuth(config.api_key, ""),
            headers={"User-Agent": config.user_agent, "Accept": "application/json"},
            timeout=httpx.Timeout(connect=3, read=10, write=10, pool=3),
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_all(self, path: str, *, collection: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        next_url: str | None = path
        while next_url:
            payload = await self.request("GET", next_url)
            page = payload.get(collection)
            if not isinstance(page, list) or not all(isinstance(item, dict) for item in page):
                raise PmsTransientError("malformed_response")
            items.extend(page)
            links = payload.get("links", {})
            next_value = links.get("next") if isinstance(links, dict) else None
            next_url = str(next_value) if next_value else None
        return items

    async def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        if path.startswith("/v1/"):
            path = path.removeprefix("/v1/")
        retryable_request = method.upper() in {"GET", "HEAD"}
        for attempt in range(self._config.max_retries + 1):
            try:
                response = await self._client.request(method, path, **kwargs)
            except httpx.TimeoutException as error:
                if retryable_request and attempt < self._config.max_retries:
                    continue
                if not retryable_request:
                    raise PmsUnknownOutcome("transport_timeout_after_write") from error
                raise PmsTransientError("transport_timeout") from error

            if response.status_code == 429:
                reset = response.headers.get("X-RateLimit-Reset")
                delay = max(0.0, float(reset) - self._now()) if reset else 1.0
                if attempt < self._config.max_retries:
                    await self._sleep(min(delay, 30.0))
                    continue
                raise PmsRateLimited("rate_limited", retry_after_seconds=max(1, int(delay)))
            if response.status_code in {408, 425} or response.status_code >= 500:
                if retryable_request and attempt < self._config.max_retries:
                    continue
                if not retryable_request:
                    raise PmsUnknownOutcome("upstream_error_after_write")
                raise PmsTransientError("upstream_unavailable")
            if response.status_code == 409:
                raise PmsConflict("conflict")
            if 400 <= response.status_code < 500:
                LOGGER.warning(
                    json.dumps(
                        {
                            "event": "cliniko_request_rejected",
                            "method": method.upper(),
                            "path": path,
                            "status_code": response.status_code,
                        },
                        separators=(",", ":"),
                    )
                )
                raise PmsValidationError(
                    "request_rejected", status_code=response.status_code, path=path
                )
            if response.status_code == 204:
                return {}

            try:
                payload = response.json()
            except ValueError as error:
                raise PmsTransientError("malformed_response") from error
            if not isinstance(payload, dict):
                raise PmsTransientError("malformed_response")
            return payload
        raise RuntimeError("unreachable")

from typing import cast

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.app import ApiSettings, create_app
from app.application.ports.pms import PmsGateway


@pytest.mark.asyncio
async def test_api_sets_security_headers_and_keeps_cors_default_deny() -> None:
    app = create_app(
        ApiSettings(b"h" * 32, b"t" * 32),
        session_factory=cast(async_sessionmaker[AsyncSession], None),
        pms=cast(PmsGateway, None),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://api.example.test"
    ) as client:
        response = await client.get("/live", headers={"Origin": "https://untrusted.example"})

    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "Access-Control-Allow-Origin" not in response.headers


@pytest.mark.asyncio
async def test_api_allows_only_explicit_cors_origins() -> None:
    app = create_app(
        ApiSettings(
            b"h" * 32,
            b"t" * 32,
            cors_allowed_origins=("https://demo.example",),
        ),
        session_factory=cast(async_sessionmaker[AsyncSession], None),
        pms=cast(PmsGateway, None),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://api.example.test"
    ) as client:
        allowed = await client.options(
            "/v1/tools/clinic-catalog",
            headers={
                "Origin": "https://demo.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        denied = await client.options(
            "/v1/tools/clinic-catalog",
            headers={
                "Origin": "https://untrusted.example",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert allowed.headers["Access-Control-Allow-Origin"] == "https://demo.example"
    assert "Access-Control-Allow-Origin" not in denied.headers

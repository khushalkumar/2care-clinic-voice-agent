import json
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.app import ApiSettings, create_app
from app.application.request_auth import RequestAuthenticator, SignedRequest
from app.infrastructure.database.replay_store import PostgresReplayStore
from app.infrastructure.pms.mock import MockPmsGateway, seed_mock_pms

pytestmark = pytest.mark.integration


def _headers(
    auth: RequestAuthenticator,
    *,
    event_id: str,
    path: str,
    body: bytes,
    timestamp: str,
) -> dict[str, str]:
    request = SignedRequest(timestamp, event_id, "POST", path, body)
    return {
        "Content-Type": "application/json",
        "X-2Care-Timestamp": request.timestamp,
        "X-2Care-Event-Id": request.event_id,
        "X-2Care-Signature": auth.sign(request),
    }


async def test_new_patient_booking_registers_before_pms_write(
    migrated_database_url: str,
) -> None:
    engine = create_async_engine(migrated_database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await seed_mock_pms(sessions)
    now = datetime.now(UTC)
    timestamp = str(int(now.timestamp()))
    auth = RequestAuthenticator(b"h" * 32, PostgresReplayStore(sessions), clock=lambda: now)
    app = create_app(
        ApiSettings(b"h" * 32, b"t" * 32),
        session_factory=sessions,
        pms=MockPmsGateway(sessions),
        clock=lambda: now,
    )
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    async def post(path: str, event_id: str, payload: dict[str, object]) -> httpx.Response:
        body = json.dumps(payload, separators=(",", ":")).encode()
        return await client.post(
            path,
            content=body,
            headers=_headers(
                auth,
                event_id=event_id,
                path=path,
                body=body,
                timestamp=timestamp,
            ),
        )

    try:
        bootstrap = await post(
            "/v1/tools/bootstrap-call",
            "new-patient-bootstrap",
            {
                "platform_call_id": "new-patient-call",
                "direction": "inbound",
                "caller_phone": "+919900000099",
                "called_phone": "+918012345678",
            },
        )
        assert bootstrap.status_code == 200, bootstrap.text
        assert bootstrap.json()["patient_lookup"] == {"match_count": 0, "mode": "new_patient"}
        session_id = bootstrap.json()["session_id"]

        search = await post(
            "/v1/tools/search-availability",
            "new-patient-search",
            {
                "session_id": session_id,
                "business_id": "indiranagar",
                "practitioner_ids": ["manjiri-arvind"],
                "appointment_type_id": "initial-consultation",
                "starts_at": "2026-07-21T03:30:00Z",
                "ends_at": "2026-07-21T07:30:00Z",
            },
        )
        assert search.status_code == 200, search.text
        slot = search.json()["slots"][0]

        booked = await post(
            "/v1/tools/book-appointment",
            "new-patient-book",
            {
                "session_id": session_id,
                "patient_id": "new_patient",
                "full_name": "Krishal Kumar",
                "availability_token": slot["availability_token"],
                "idempotency_key": "new-patient-book-1",
            },
        )
        assert booked.status_code == 200, booked.text
        assert booked.json()["status"] == "confirmed"
        assert booked.json()["appointment"]["patient_id"] != "new_patient"
    finally:
        await client.aclose()
        await engine.dispose()

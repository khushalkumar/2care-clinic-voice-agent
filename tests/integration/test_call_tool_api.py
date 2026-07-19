import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.app import ApiSettings, create_app
from app.application.request_auth import RequestAuthenticator, SignedRequest
from app.infrastructure.database.call_store import CallStore
from app.infrastructure.database.replay_store import PostgresReplayStore
from app.infrastructure.pms.mock import MockPmsGateway, seed_mock_pms

pytestmark = pytest.mark.integration


async def test_bootstrap_checkpoint_followup_and_drop_recovery(
    migrated_database_url: str,
) -> None:
    engine = create_async_engine(migrated_database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await seed_mock_pms(sessions)
    now = datetime.now(UTC)
    timestamp = str(int(now.timestamp()))
    auth = RequestAuthenticator(b"h" * 32, PostgresReplayStore(sessions), clock=lambda: now)
    call_store = CallStore(sessions)
    await call_store.create_outbound_context(
        phone_e164="+919900000001",
        campaign="follow-up",
        purpose="post-visit check-in",
        expires_at=now + timedelta(days=1),
        now=now,
    )
    app = create_app(
        ApiSettings(b"h" * 32, b"t" * 32),
        session_factory=sessions,
        pms=MockPmsGateway(sessions),
        clock=lambda: now,
    )
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    async def post(path: str, event_id: str, payload: dict[str, object]) -> httpx.Response:
        body = json.dumps(payload, separators=(",", ":")).encode()
        signed = SignedRequest(timestamp, event_id, "POST", path, body)
        return await client.post(
            path,
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-2Care-Timestamp": timestamp,
                "X-2Care-Event-Id": event_id,
                "X-2Care-Signature": auth.sign(signed),
            },
        )

    try:
        bootstrap = await post(
            "/v1/tools/bootstrap-call",
            "bootstrap-1",
            {
                "platform_call_id": "voice-call-1",
                "direction": "inbound",
                "caller_phone": "+919900000001",
                "called_phone": "+918012345678",
            },
        )
        assert bootstrap.status_code == 200, bootstrap.text
        started = bootstrap.json()
        assert started["patient_lookup"] == {"match_count": 2, "mode": "disambiguate"}
        assert started["callback_context"]["purpose"] == "post-visit check-in"
        session_id = started["session_id"]

        checkpoint = await post(
            "/v1/tools/save-call-checkpoint",
            "checkpoint-1",
            {
                "session_id": session_id,
                "patient_id": "aarav-sharma",
                "language_mode": "hi-en",
                "checkpoint": {
                    "intent": "book",
                    "business_id": "jayanagar",
                    "availability_token": "must-not-survive",
                },
            },
        )
        assert checkpoint.status_code == 200, checkpoint.text

        followup_payload = {
            "session_id": session_id,
            "idempotency_key": "followup-1",
            "reason": "needs-clinic-review",
            "details": {"preferred_language": "Hindi"},
        }
        first_followup = await post("/v1/tools/log-follow-up", "followup-event-1", followup_payload)
        replayed_followup = await post(
            "/v1/tools/log-follow-up", "followup-event-2", followup_payload
        )
        assert first_followup.json()["replayed"] is False
        assert replayed_followup.json()["replayed"] is True
        assert first_followup.json()["follow_up_id"] == replayed_followup.json()["follow_up_id"]

        await call_store.end(
            UUID(started["session_id"]),
            disposition="dropped",
            reason="network_disconnect",
            now=now + timedelta(minutes=2),
        )
        resumed = await post(
            "/v1/tools/bootstrap-call",
            "bootstrap-2",
            {
                "platform_call_id": "voice-call-2",
                "direction": "inbound",
                "caller_phone": "+919900000001",
                "called_phone": "+918012345678",
            },
        )
        assert resumed.status_code == 200, resumed.text
        assert resumed.json()["resumed"] is True
        assert resumed.json()["checkpoint"] == {
            "intent": "book",
            "business_id": "jayanagar",
        }
    finally:
        await client.aclose()
        await engine.dispose()

import json
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.app import ApiSettings, create_app
from app.application.request_auth import RequestAuthenticator, SignedRequest
from app.infrastructure.database.replay_store import PostgresReplayStore
from app.infrastructure.pms.mock import MockPmsGateway, seed_mock_pms

pytestmark = pytest.mark.integration


def _signed_headers(
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


async def test_authenticated_search_and_booking_flow(migrated_database_url: str) -> None:
    engine = create_async_engine(migrated_database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await seed_mock_pms(sessions)
    replay_store = PostgresReplayStore(sessions)
    now = datetime.now(UTC)
    timestamp = str(int(now.timestamp()))
    auth = RequestAuthenticator(b"h" * 32, replay_store, clock=lambda: now)
    app = create_app(
        ApiSettings(
            request_hmac_secret=b"h" * 32,
            availability_token_secret=b"t" * 32,
        ),
        session_factory=sessions,
        pms=MockPmsGateway(sessions),
        clock=lambda: now,
    )
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    try:
        assert (await client.get("/live")).status_code == 200
        assert (await client.get("/ready")).status_code == 200
        unauthenticated = await client.post("/v1/tools/search-availability", json={})
        assert unauthenticated.status_code == 401

        non_json_body = b"not-json"
        non_json_headers = _signed_headers(
            auth,
            event_id="wrong-content-type",
            path="/v1/tools/search-availability",
            body=non_json_body,
            timestamp=timestamp,
        )
        non_json_headers["Content-Type"] = "text/plain"
        non_json = await client.post(
            "/v1/tools/search-availability",
            content=non_json_body,
            headers=non_json_headers,
        )
        assert non_json.status_code == 415

        oversized_body = b"{" + b"x" * (64 * 1024) + b"}"
        oversized = await client.post(
            "/v1/tools/search-availability",
            content=oversized_body,
            headers=_signed_headers(
                auth,
                event_id="oversized",
                path="/v1/tools/search-availability",
                body=oversized_body,
                timestamp=timestamp,
            ),
        )
        assert oversized.status_code == 413

        bootstrap_payload = {
            "platform_call_id": "voice-api-flow-1",
            "direction": "inbound",
            "caller_phone": "+919900000001",
            "called_phone": "+918012345678",
        }
        bootstrap_body = json.dumps(bootstrap_payload, separators=(",", ":")).encode()
        bootstrap = await client.post(
            "/v1/tools/bootstrap-call",
            content=bootstrap_body,
            headers=_signed_headers(
                auth,
                event_id="bootstrap-api-flow-1",
                path="/v1/tools/bootstrap-call",
                body=bootstrap_body,
                timestamp=timestamp,
            ),
        )
        assert bootstrap.status_code == 200, bootstrap.text
        session_id = bootstrap.json()["session_id"]

        search_payload = {
            "session_id": session_id,
            "targets": [
                {
                    "business_id": "jayanagar",
                    "practitioner_ids": ["nadia-zainab"],
                    "appointment_type_id": "initial-consultation",
                },
                {
                    "business_id": "indiranagar",
                    "practitioner_ids": ["manjiri-arvind"],
                    "appointment_type_id": "initial-consultation",
                },
            ],
            "starts_at": "2026-07-21T03:30:00Z",
            "ends_at": "2026-07-21T07:30:00Z",
        }
        search_body = json.dumps(search_payload, separators=(",", ":")).encode()
        search_headers = _signed_headers(
            auth,
            event_id="search-1",
            path="/v1/tools/search-availability",
            body=search_body,
            timestamp=timestamp,
        )
        search = await client.post(
            "/v1/tools/search-availability", content=search_body, headers=search_headers
        )
        assert search.status_code == 200, search.text
        assert search.headers["X-Request-ID"] == "search-1"
        offered = search.json()["slots"]
        assert offered
        assert all("availability_token" in slot for slot in offered)
        assert all("spoken_label" in slot for slot in offered)
        assert all("spoken_date" in slot for slot in offered)
        assert all("spoken_time_range" in slot for slot in offered)
        assert len(offered) == 3
        assert search.json()["search_scope"] == {
            "target_count": 2,
            "globally_ranked": True,
            "returned_slot_count": 3,
            "total_slot_count": 14,
            "truncated": True,
        }

        replay = await client.post(
            "/v1/tools/search-availability", content=search_body, headers=search_headers
        )
        assert replay.status_code == 401
        assert replay.json()["error"]["code"] == "replayed"

        book_payload = {
            "session_id": session_id,
            "patient_id": "aarav-sharma",
            "full_name": "Aarav Sharma",
            "availability_token": offered[0]["availability_token"],
            "idempotency_key": "book-api-1",
        }
        wrong_identity_payload = book_payload | {
            "full_name": "Someone Else",
            "idempotency_key": "book-wrong-identity",
        }
        wrong_identity_body = json.dumps(wrong_identity_payload, separators=(",", ":")).encode()
        wrong_identity = await client.post(
            "/v1/tools/book-appointment",
            content=wrong_identity_body,
            headers=_signed_headers(
                auth,
                event_id="book-wrong-identity",
                path="/v1/tools/book-appointment",
                body=wrong_identity_body,
                timestamp=timestamp,
            ),
        )
        assert wrong_identity.status_code == 403
        assert wrong_identity.json()["error"]["code"] == "full_name_mismatch"

        book_body = json.dumps(book_payload, separators=(",", ":")).encode()
        booked = await client.post(
            "/v1/tools/book-appointment",
            content=book_body,
            headers=_signed_headers(
                auth,
                event_id="book-1",
                path="/v1/tools/book-appointment",
                body=book_body,
                timestamp=timestamp,
            ),
        )
        assert booked.status_code == 200, booked.text
        assert booked.json()["status"] == "confirmed"
        assert booked.json()["appointment"]["patient_id"] == "aarav-sharma"
        appointment_id = booked.json()["appointment"]["id"]

        list_payload = {
            "session_id": session_id,
            "patient_id": "aarav-sharma",
            "full_name": "Aarav Sharma",
        }
        list_body = json.dumps(list_payload, separators=(",", ":")).encode()
        listed = await client.post(
            "/v1/tools/list-patient-appointments",
            content=list_body,
            headers=_signed_headers(
                auth,
                event_id="list-1",
                path="/v1/tools/list-patient-appointments",
                body=list_body,
                timestamp=timestamp,
            ),
        )
        assert listed.status_code == 200, listed.text
        assert [item["id"] for item in listed.json()["appointments"]] == [appointment_id]

        wrong_patient_payload = list_payload | {
            "patient_id": "meera-sharma",
            "full_name": "Meera Sharma",
        }
        wrong_patient_body = json.dumps(wrong_patient_payload, separators=(",", ":")).encode()
        wrong_patient = await client.post(
            "/v1/tools/list-patient-appointments",
            content=wrong_patient_body,
            headers=_signed_headers(
                auth,
                event_id="list-wrong-patient",
                path="/v1/tools/list-patient-appointments",
                body=wrong_patient_body,
                timestamp=timestamp,
            ),
        )
        assert wrong_patient.status_code == 403
        assert wrong_patient.json()["error"]["code"] == "patient_mismatch"

        fresh_search_payload = search_payload | {
            "starts_at": "2026-07-21T07:30:00Z",
            "ends_at": "2026-07-21T10:30:00Z",
        }
        fresh_search_body = json.dumps(fresh_search_payload, separators=(",", ":")).encode()
        fresh_search = await client.post(
            "/v1/tools/search-availability",
            content=fresh_search_body,
            headers=_signed_headers(
                auth,
                event_id="search-reschedule-target",
                path="/v1/tools/search-availability",
                body=fresh_search_body,
                timestamp=timestamp,
            ),
        )
        assert fresh_search.status_code == 200, fresh_search.text
        reschedule_slot = fresh_search.json()["slots"][0]

        move_payload = {
            "session_id": session_id,
            "patient_id": "aarav-sharma",
            "full_name": "Aarav Sharma",
            "appointment_id": appointment_id,
            "availability_token": reschedule_slot["availability_token"],
            "idempotency_key": "move-api-1",
        }
        move_body = json.dumps(move_payload, separators=(",", ":")).encode()
        moved = await client.post(
            "/v1/tools/reschedule-appointment",
            content=move_body,
            headers=_signed_headers(
                auth,
                event_id="move-1",
                path="/v1/tools/reschedule-appointment",
                body=move_body,
                timestamp=timestamp,
            ),
        )
        assert moved.status_code == 200, moved.text
        assert moved.json()["appointment"]["starts_at"] == reschedule_slot["starts_at"]
        async with engine.connect() as connection:
            reservation_statuses = (
                (
                    await connection.execute(
                        text(
                            "SELECT sr.status "
                            "FROM slot_reservations sr "
                            "JOIN booking_operations bo ON bo.id = sr.booking_operation_id "
                            "WHERE bo.remote_appointment_id = :appointment_id "
                            "ORDER BY sr.created_at"
                        ),
                        {"appointment_id": appointment_id},
                    )
                )
                .scalars()
                .all()
            )
        assert reservation_statuses == ["cancelled", "confirmed"]

        cancel_payload = {
            "session_id": session_id,
            "patient_id": "aarav-sharma",
            "full_name": "Aarav Sharma",
            "appointment_id": appointment_id,
            "idempotency_key": "cancel-api-1",
        }
        cancel_body = json.dumps(cancel_payload, separators=(",", ":")).encode()
        cancelled = await client.post(
            "/v1/tools/cancel-appointment",
            content=cancel_body,
            headers=_signed_headers(
                auth,
                event_id="cancel-1",
                path="/v1/tools/cancel-appointment",
                body=cancel_body,
                timestamp=timestamp,
            ),
        )
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["appointment"]["status"] == "cancelled"
        async with engine.connect() as connection:
            final_reservation_statuses = (
                (
                    await connection.execute(
                        text(
                            "SELECT sr.status "
                            "FROM slot_reservations sr "
                            "JOIN booking_operations bo ON bo.id = sr.booking_operation_id "
                            "WHERE bo.remote_appointment_id = :appointment_id"
                        ),
                        {"appointment_id": appointment_id},
                    )
                )
                .scalars()
                .all()
            )
        assert final_reservation_statuses == ["cancelled", "cancelled"]
    finally:
        await client.aclose()
        await engine.dispose()


async def test_retell_platform_token_can_call_voice_tools(migrated_database_url: str) -> None:
    engine = create_async_engine(migrated_database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await seed_mock_pms(sessions)
    app = create_app(
        ApiSettings(
            request_hmac_secret=b"h" * 32,
            availability_token_secret=b"t" * 32,
            retell_tool_token=b"r" * 32,
        ),
        session_factory=sessions,
        pms=MockPmsGateway(sessions),
    )
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    try:
        bootstrap = await client.post(
            "/v1/tools/bootstrap-call",
            headers={"X-2Care-Platform-Token": "r" * 32},
            json={
                "platform_call_id": "voice-platform-search-1",
                "direction": "inbound",
                "caller_phone": "+919900000001",
                "called_phone": "+918012345678",
            },
        )
        assert bootstrap.status_code == 200, bootstrap.text
        response = await client.post(
            "/v1/tools/search-availability",
            headers={"X-2Care-Platform-Token": "r" * 32},
            json={
                "session_id": bootstrap.json()["session_id"],
                "targets": [
                    {
                        "business_id": "jayanagar",
                        "practitioner_ids": ["nadia-zainab"],
                        "appointment_type_id": "initial-consultation",
                    }
                ],
                "starts_at": "2026-07-20T03:30:00Z",
                "ends_at": "2026-07-20T07:30:00Z",
            },
        )

        assert response.status_code == 200, response.text
    finally:
        await client.aclose()
        await engine.dispose()


async def test_retell_platform_token_can_read_clinic_catalog(migrated_database_url: str) -> None:
    engine = create_async_engine(migrated_database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await seed_mock_pms(sessions)
    app = create_app(
        ApiSettings(
            request_hmac_secret=b"h" * 32,
            availability_token_secret=b"t" * 32,
            retell_tool_token=b"r" * 32,
        ),
        session_factory=sessions,
        pms=MockPmsGateway(sessions),
    )
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    try:
        response = await client.get(
            "/v1/tools/clinic-catalog",
            headers={"X-2Care-Platform-Token": "r" * 32},
        )

        assert response.status_code == 200, response.text
        assert response.json()["businesses"] == [
            {
                "id": "indiranagar",
                "name": "Physiotattva Indiranagar",
                "timezone": "Asia/Kolkata",
            },
            {
                "id": "jayanagar",
                "name": "Physiotattva Jayanagar",
                "timezone": "Asia/Kolkata",
            },
        ]
        assert {item["name"] for item in response.json()["appointment_types"]} == {
            "Follow-up",
            "Initial consultation",
        }
    finally:
        await client.aclose()
        await engine.dispose()

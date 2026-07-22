import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.infrastructure.database.call_store import CallStore, StartCall

pytestmark = pytest.mark.integration


@pytest.fixture
async def call_store(migrated_database_url: str) -> CallStore:
    engine = create_async_engine(migrated_database_url)
    store = CallStore(async_sessionmaker(engine, expire_on_commit=False))
    try:
        yield store
    finally:
        await engine.dispose()


async def test_start_is_idempotent_and_normalizes_indian_numbers(call_store: CallStore) -> None:
    now = datetime(2026, 7, 18, 8, 0, tzinfo=UTC)
    request = StartCall("provider-call-1", "inbound", "09900000001", "+918012345678")

    first = await call_store.start(request, now=now)
    replay = await call_store.start(request, now=now + timedelta(seconds=2))

    assert first.replayed is False
    assert replay.replayed is True
    assert replay.session.id == first.session.id
    assert first.session.caller_phone_e164 == "+919900000001"


async def test_dropped_call_resumes_checkpoint_inside_window(call_store: CallStore) -> None:
    now = datetime(2026, 7, 18, 8, 0, tzinfo=UTC)
    original = await call_store.start(
        StartCall("provider-call-2", "inbound", "+919900000001", "+918012345678"),
        now=now,
    )
    await call_store.save_checkpoint(
        original.session.id,
        checkpoint={"intent": "book", "business_id": "jayanagar"},
        patient_id="aarav-sharma",
        language_mode="hi-en",
        now=now + timedelta(minutes=2),
    )
    await call_store.end(
        original.session.id,
        disposition="dropped",
        reason="network_disconnect",
        now=now + timedelta(minutes=3),
    )

    resumed = await call_store.start(
        StartCall("provider-call-3", "inbound", "+919900000001", "+918012345678"),
        now=now + timedelta(minutes=10),
    )

    assert resumed.session.resumed_from_id == original.session.id
    assert resumed.session.checkpoint == {"intent": "book", "business_id": "jayanagar"}
    assert resumed.session.patient_id == "aarav-sharma"
    assert resumed.session.language_mode == "hi-en"


async def test_old_dropped_call_is_not_resumed(call_store: CallStore) -> None:
    now = datetime(2026, 7, 18, 8, 0, tzinfo=UTC)
    original = await call_store.start(
        StartCall("provider-call-4", "inbound", "+919900000002", "+918012345678"),
        now=now,
    )
    await call_store.end(
        original.session.id,
        disposition="dropped",
        reason="hangup",
        now=now + timedelta(minutes=1),
    )

    later = await call_store.start(
        StartCall("provider-call-5", "inbound", "+919900000002", "+918012345678"),
        now=now + timedelta(minutes=40),
    )

    assert later.session.resumed_from_id is None


async def test_callback_context_is_consumed_exactly_once(call_store: CallStore) -> None:
    now = datetime(2026, 7, 18, 8, 0, tzinfo=UTC)
    await call_store.create_outbound_context(
        phone_e164="+919900000003",
        campaign="follow-up",
        purpose="post-visit check-in",
        expires_at=now + timedelta(days=1),
        now=now,
    )

    results = await asyncio.gather(
        *(call_store.consume_outbound_context("+919900000003", now=now) for _ in range(8))
    )

    assert sum(result is not None for result in results) == 1
    context = next(result for result in results if result is not None)
    assert context.purpose == "post-visit check-in"


async def test_start_attaches_callback_context_and_replay_keeps_it(call_store: CallStore) -> None:
    now = datetime(2026, 7, 18, 8, 0, tzinfo=UTC)
    await call_store.create_outbound_context(
        phone_e164="+919900000004",
        campaign="referral",
        purpose="complete referral booking",
        expires_at=now + timedelta(days=1),
        now=now,
    )
    request = StartCall("provider-callback", "inbound", "+919900000004", "+918012345678")

    first = await call_store.start(request, now=now)
    replay = await call_store.start(request, now=now + timedelta(seconds=1))

    assert first.session.callback_campaign == "referral"
    assert first.session.callback_purpose == "complete referral booking"
    assert replay.session.callback_purpose == first.session.callback_purpose


async def test_checkpoint_without_identity_does_not_clear_bound_patient(
    call_store: CallStore,
) -> None:
    now = datetime(2026, 7, 18, 8, 0, tzinfo=UTC)
    started = await call_store.start(
        StartCall("provider-bound-patient", "inbound", "+919900000001", "+918012345678"),
        now=now,
    )
    await call_store.save_checkpoint(
        started.session.id,
        checkpoint={"intent": "book"},
        patient_id="aarav-sharma",
        language_mode="en",
        now=now,
    )
    await call_store.save_checkpoint(
        started.session.id,
        checkpoint={"intent": "book", "step": "confirmed"},
        patient_id=None,
        language_mode=None,
        now=now + timedelta(seconds=1),
    )

    current = await call_store.get(started.session.id)

    assert current is not None
    assert current.patient_id == "aarav-sharma"
    assert current.language_mode == "en"


async def test_phone_identity_supports_single_and_shared_numbers(call_store: CallStore) -> None:
    now = datetime(2026, 7, 18, 8, 0, tzinfo=UTC)

    await call_store.bind_phone_identity("+919900000009", "patient-1", source="cliniko", now=now)
    await call_store.bind_phone_identity("+919900000009", "patient-1", source="cliniko", now=now)
    assert await call_store.patient_ids_for_phone("09900000009") == ("patient-1",)

    await call_store.bind_phone_identity("+919900000009", "patient-2", source="cliniko", now=now)
    assert await call_store.patient_ids_for_phone("+919900000009") == (
        "patient-1",
        "patient-2",
    )

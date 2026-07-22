from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import phonenumbers
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.database.models import (
    CallSession,
    FollowUp,
    OutboundContext,
    PatientPhoneIdentity,
)


def normalize_phone(value: str) -> str:
    try:
        parsed = phonenumbers.parse(value, "IN")
    except phonenumbers.NumberParseException as error:
        raise ValueError("invalid phone number") from error
    if not phonenumbers.is_valid_number(parsed):
        raise ValueError("invalid phone number")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


@dataclass(frozen=True, slots=True)
class StartCall:
    platform_call_id: str
    direction: str
    caller_phone: str
    called_phone: str


@dataclass(frozen=True, slots=True)
class CallSessionRecord:
    id: UUID
    platform_call_id: str
    caller_phone_e164: str
    called_phone_e164: str
    status: str
    language_mode: str | None
    patient_id: str | None
    checkpoint: dict[str, object]
    resumed_from_id: UUID | None
    callback_campaign: str | None
    callback_purpose: str | None


@dataclass(frozen=True, slots=True)
class StartCallResult:
    session: CallSessionRecord
    replayed: bool


@dataclass(frozen=True, slots=True)
class OutboundContextRecord:
    id: UUID
    campaign: str
    purpose: str


@dataclass(frozen=True, slots=True)
class FollowUpResult:
    follow_up_id: UUID
    replayed: bool


def _record(row: CallSession) -> CallSessionRecord:
    return CallSessionRecord(
        id=row.id,
        platform_call_id=row.platform_call_id,
        caller_phone_e164=row.caller_phone_e164,
        called_phone_e164=row.called_phone_e164,
        status=row.status,
        language_mode=row.language_mode,
        patient_id=row.patient_id,
        checkpoint=row.checkpoint,
        resumed_from_id=row.resumed_from_id,
        callback_campaign=row.callback_campaign,
        callback_purpose=row.callback_purpose,
    )


class CallStore:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        resume_window: timedelta = timedelta(minutes=30),
    ) -> None:
        self._session_factory = session_factory
        self._resume_window = resume_window

    async def start(self, request: StartCall, *, now: datetime) -> StartCallResult:
        caller = normalize_phone(request.caller_phone)
        called = normalize_phone(request.called_phone)
        if request.direction not in {"inbound", "outbound"}:
            raise ValueError("invalid call direction")
        async with self._session_factory() as session, session.begin():
            existing = await session.scalar(
                select(CallSession).where(CallSession.platform_call_id == request.platform_call_id)
            )
            if existing is not None:
                return StartCallResult(_record(existing), replayed=True)
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:phone, 0))"),
                {"phone": caller},
            )
            resumable = await session.scalar(
                select(CallSession)
                .where(
                    CallSession.caller_phone_e164 == caller,
                    CallSession.status == "dropped",
                    CallSession.ended_at >= now - self._resume_window,
                    CallSession.resume_consumed_at.is_(None),
                )
                .order_by(CallSession.ended_at.desc())
                .limit(1)
                .with_for_update()
            )
            callback = (
                await self._consume_outbound_context(session, caller, now=now)
                if request.direction == "inbound"
                else None
            )
            row = CallSession(
                id=uuid4(),
                platform_call_id=request.platform_call_id,
                direction=request.direction,
                caller_phone_e164=caller,
                called_phone_e164=called,
                status="active",
                language_mode=resumable.language_mode if resumable else None,
                patient_id=resumable.patient_id if resumable else None,
                checkpoint=dict(resumable.checkpoint) if resumable else {},
                resumed_from_id=resumable.id if resumable else None,
                callback_campaign=callback.campaign if callback else None,
                callback_purpose=callback.purpose if callback else None,
                started_at=now,
                updated_at=now,
            )
            if resumable is not None:
                resumable.resume_consumed_at = now
            session.add(row)
            await session.flush()
            return StartCallResult(_record(row), replayed=False)

    async def save_checkpoint(
        self,
        session_id: UUID,
        *,
        checkpoint: dict[str, object],
        patient_id: str | None,
        language_mode: str | None,
        now: datetime,
    ) -> None:
        async with self._session_factory() as session, session.begin():
            row = await session.get(CallSession, session_id, with_for_update=True)
            if row is None:
                raise LookupError("call session not found")
            row.checkpoint = checkpoint
            if patient_id is not None:
                row.patient_id = patient_id
            if language_mode is not None:
                row.language_mode = language_mode
            row.updated_at = now

    async def get(self, session_id: UUID) -> CallSessionRecord | None:
        async with self._session_factory() as session:
            row = await session.get(CallSession, session_id)
            return _record(row) if row is not None else None

    async def bind_patient(self, session_id: UUID, patient_id: str, *, now: datetime) -> bool:
        async with self._session_factory() as session, session.begin():
            row = await session.get(CallSession, session_id, with_for_update=True)
            if row is None:
                raise LookupError("call session not found")
            if row.patient_id is not None and row.patient_id != patient_id:
                return False
            row.patient_id = patient_id
            row.updated_at = now
            return True

    async def bind_phone_identity(
        self,
        phone_e164: str,
        patient_id: str,
        *,
        source: str,
        now: datetime,
    ) -> None:
        phone = normalize_phone(phone_e164)
        async with self._session_factory() as session, session.begin():
            await session.execute(
                insert(PatientPhoneIdentity)
                .values(
                    phone_e164=phone,
                    patient_id=patient_id,
                    source=source,
                    created_at=now,
                )
                .on_conflict_do_nothing()
            )

    async def patient_ids_for_phone(self, phone_e164: str) -> tuple[str, ...]:
        phone = normalize_phone(phone_e164)
        async with self._session_factory() as session:
            patient_ids = (
                await session.scalars(
                    select(PatientPhoneIdentity.patient_id)
                    .where(PatientPhoneIdentity.phone_e164 == phone)
                    .order_by(PatientPhoneIdentity.patient_id)
                )
            ).all()
        return tuple(patient_ids)

    async def end(
        self,
        session_id: UUID,
        *,
        disposition: str,
        reason: str,
        now: datetime,
    ) -> None:
        if disposition not in {"completed", "dropped", "failed"}:
            raise ValueError("invalid call disposition")
        async with self._session_factory() as session, session.begin():
            row = await session.get(CallSession, session_id, with_for_update=True)
            if row is None:
                raise LookupError("call session not found")
            if row.status != "active":
                return
            row.status = disposition
            row.disconnect_reason = reason
            row.ended_at = now
            row.updated_at = now

    async def log_follow_up(
        self,
        session_id: UUID,
        *,
        idempotency_key: str,
        reason: str,
        details: dict[str, object],
        now: datetime,
    ) -> FollowUpResult:
        async with self._session_factory() as session, session.begin():
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": idempotency_key},
            )
            existing = await session.scalar(
                select(FollowUp).where(FollowUp.idempotency_key == idempotency_key)
            )
            if existing is not None:
                return FollowUpResult(existing.id, replayed=True)
            if await session.get(CallSession, session_id) is None:
                raise LookupError("call session not found")
            row = FollowUp(
                id=uuid4(),
                call_session_id=session_id,
                idempotency_key=idempotency_key,
                reason=reason,
                details=details,
                status="pending",
                created_at=now,
            )
            session.add(row)
            await session.flush()
            return FollowUpResult(row.id, replayed=False)

    async def create_outbound_context(
        self,
        *,
        phone_e164: str,
        campaign: str,
        purpose: str,
        expires_at: datetime,
        now: datetime,
    ) -> UUID:
        row = OutboundContext(
            id=uuid4(),
            phone_e164=normalize_phone(phone_e164),
            campaign=campaign,
            purpose=purpose,
            status="eligible",
            expires_at=expires_at,
            created_at=now,
        )
        async with self._session_factory() as session, session.begin():
            session.add(row)
        return row.id

    async def consume_outbound_context(
        self, phone_e164: str, *, now: datetime
    ) -> OutboundContextRecord | None:
        phone = normalize_phone(phone_e164)
        async with self._session_factory() as session, session.begin():
            return await self._consume_outbound_context(session, phone, now=now)

    @staticmethod
    async def _consume_outbound_context(
        session: AsyncSession, phone: str, *, now: datetime
    ) -> OutboundContextRecord | None:
        row = await session.scalar(
            select(OutboundContext)
            .where(
                OutboundContext.phone_e164 == phone,
                OutboundContext.status == "eligible",
                OutboundContext.expires_at > now,
            )
            .order_by(OutboundContext.created_at.desc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if row is None:
            return None
        row.status = "consumed"
        row.consumed_at = now
        return OutboundContextRecord(row.id, row.campaign, row.purpose)

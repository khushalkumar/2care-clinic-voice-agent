from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.database.models import OutboxEvent


@dataclass(frozen=True, slots=True)
class OutboxMessage:
    id: UUID
    event_type: str
    payload: dict[str, Any]


class OutboxStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def claim(
        self,
        *,
        now: datetime,
        limit: int = 10,
        lease: timedelta = timedelta(seconds=30),
    ) -> list[OutboxMessage]:
        async with self._session_factory() as session, session.begin():
            rows = (
                await session.scalars(
                    select(OutboxEvent)
                    .where(
                        OutboxEvent.status == "pending",
                        OutboxEvent.available_at <= now,
                    )
                    .order_by(OutboxEvent.available_at, OutboxEvent.created_at)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).all()
            for row in rows:
                row.attempts += 1
                row.available_at = now + lease
            return [OutboxMessage(row.id, row.event_type, row.payload) for row in rows]

    async def mark_published(self, event_id: UUID, *, now: datetime) -> None:
        async with self._session_factory() as session, session.begin():
            row = await session.get(OutboxEvent, event_id, with_for_update=True)
            if row is None:
                raise LookupError("outbox event not found")
            row.status = "published"
            row.published_at = now
            row.last_error = None

    async def reschedule(
        self,
        event_id: UUID,
        *,
        now: datetime,
        backoff: timedelta = timedelta(seconds=5),
    ) -> None:
        async with self._session_factory() as session, session.begin():
            row = await session.get(OutboxEvent, event_id, with_for_update=True)
            if row is None:
                raise LookupError("outbox event not found")
            row.status = "pending"
            row.available_at = now + backoff
            row.last_error = "publish_failed"

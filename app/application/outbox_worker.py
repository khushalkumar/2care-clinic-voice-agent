from datetime import datetime
from typing import Protocol

from app.infrastructure.database.outbox_store import OutboxStore


class EventPublisher(Protocol):
    async def publish(self, event_id: str, event_type: str, payload: dict[str, object]) -> None: ...


class OutboxWorker:
    def __init__(self, store: OutboxStore, publisher: EventPublisher) -> None:
        self._store = store
        self._publisher = publisher

    async def run_once(self, *, now: datetime, limit: int = 10) -> int:
        published = 0
        for event in await self._store.claim(now=now, limit=limit):
            try:
                await self._publisher.publish(str(event.id), event.event_type, event.payload)
            except Exception:
                await self._store.reschedule(event.id, now=now)
                continue
            await self._store.mark_published(event.id, now=now)
            published += 1
        return published

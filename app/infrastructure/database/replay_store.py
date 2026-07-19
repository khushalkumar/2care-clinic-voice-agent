from datetime import datetime

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.database.models import RequestReplay


class PostgresReplayStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def claim(self, event_id: str, expires_at: datetime) -> bool:
        insert_statement = insert(RequestReplay).values(event_id=event_id, expires_at=expires_at)
        statement = insert_statement.on_conflict_do_update(
            index_elements=[RequestReplay.event_id],
            set_={"expires_at": expires_at, "created_at": func.now()},
            where=RequestReplay.expires_at <= func.now(),
        ).returning(RequestReplay.event_id)
        async with self._session_factory() as session, session.begin():
            claimed = await session.scalar(statement)
        return claimed is not None

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.database.models import BookingOperation, OutboxEvent, SlotReservation


class SlotAlreadyReserved(Exception):
    """The requested practitioner range overlaps an active reservation."""


@dataclass(frozen=True, slots=True)
class ReservationRequest:
    idempotency_key: str
    practitioner_key: str
    reserved_from: datetime
    reserved_until: datetime
    expires_at: datetime
    pms_payload: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ReservationResult:
    operation_id: UUID
    reservation_id: UUID
    replayed: bool


@dataclass(frozen=True, slots=True)
class PendingBooking:
    operation_id: UUID
    idempotency_key: str
    request_payload: dict[str, Any]


def _database_error_details(error: BaseException) -> tuple[str | None, str | None]:
    constraint = None
    sqlstate = None
    current: BaseException | None = error
    while current is not None:
        constraint = constraint or getattr(current, "constraint_name", None)
        sqlstate = sqlstate or getattr(current, "sqlstate", None)
        current = current.__cause__
    return constraint, sqlstate


class BookingStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def reserve(self, request: ReservationRequest) -> ReservationResult:
        operation_id = uuid4()
        reservation_id = uuid4()
        try:
            async with self._session_factory() as session, session.begin():
                # The database exclusion constraint is authoritative. This lock only serializes
                # same-practitioner contenders to avoid GiST deadlocks under heavy races.
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                    {"key": request.practitioner_key},
                )
                session.add(
                    BookingOperation(
                        id=operation_id,
                        operation_type="book",
                        idempotency_key=request.idempotency_key,
                        status="reserved",
                        version=1,
                        request_payload=request.pms_payload,
                    )
                )
                session.add(
                    SlotReservation(
                        id=reservation_id,
                        booking_operation_id=operation_id,
                        practitioner_key=request.practitioner_key,
                        reserved_from=request.reserved_from,
                        reserved_until=request.reserved_until,
                        status="held",
                        expires_at=request.expires_at,
                    )
                )
                session.add(
                    OutboxEvent(
                        id=uuid4(),
                        aggregate_type="booking_operation",
                        aggregate_id=operation_id,
                        event_type="booking.reserved",
                        payload={
                            "operation_id": str(operation_id),
                            "practitioner_key": request.practitioner_key,
                            "reserved_from": request.reserved_from.isoformat(),
                            "reserved_until": request.reserved_until.isoformat(),
                        },
                        status="pending",
                        attempts=0,
                        available_at=datetime.now(UTC),
                    )
                )
                await session.flush()
        except IntegrityError as error:
            constraint, sqlstate = _database_error_details(error)
            if constraint == "uq_booking_operations_idempotency_key":
                return await self._get_existing(request.idempotency_key)
            if constraint == "no_overlapping_practitioner_reservations" or sqlstate == "23P01":
                raise SlotAlreadyReserved from error
            raise
        except DBAPIError as error:
            _, sqlstate = _database_error_details(error)
            if sqlstate == "40P01":
                raise SlotAlreadyReserved from error
            raise

        return ReservationResult(operation_id, reservation_id, replayed=False)

    async def _get_existing(self, idempotency_key: str) -> ReservationResult:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(BookingOperation.id, SlotReservation.id)
                    .join(
                        SlotReservation,
                        SlotReservation.booking_operation_id == BookingOperation.id,
                    )
                    .where(BookingOperation.idempotency_key == idempotency_key)
                )
            ).one()
        return ReservationResult(row[0], row[1], replayed=True)

    async def mark_confirmed(self, operation_id: UUID, remote_appointment_id: str) -> None:
        await self._set_outcome(
            operation_id,
            operation_status="confirmed",
            reservation_status="confirmed",
            remote_appointment_id=remote_appointment_id,
            error_code=None,
        )

    async def mark_pending_verification(self, operation_id: UUID, error_code: str) -> None:
        await self._set_outcome(
            operation_id,
            operation_status="pending_verification",
            reservation_status="pending_remote",
            remote_appointment_id=None,
            error_code=error_code,
        )

    async def mark_failed(self, operation_id: UUID, error_code: str) -> None:
        await self._set_outcome(
            operation_id,
            operation_status="failed",
            reservation_status="cancelled",
            remote_appointment_id=None,
            error_code=error_code,
        )

    async def _set_outcome(
        self,
        operation_id: UUID,
        *,
        operation_status: str,
        reservation_status: str,
        remote_appointment_id: str | None,
        error_code: str | None,
    ) -> None:
        async with self._session_factory() as session, session.begin():
            updated_id = await session.scalar(
                update(BookingOperation)
                .where(BookingOperation.id == operation_id)
                .values(
                    status=operation_status,
                    remote_appointment_id=remote_appointment_id,
                    last_error_code=error_code,
                    version=BookingOperation.version + 1,
                )
                .returning(BookingOperation.id)
            )
            if updated_id is None:
                raise LookupError("booking operation not found")
            await session.execute(
                update(SlotReservation)
                .where(SlotReservation.booking_operation_id == operation_id)
                .values(status=reservation_status)
            )

    async def list_pending_verification(self, *, limit: int = 50) -> list[PendingBooking]:
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(
                        BookingOperation.id,
                        BookingOperation.idempotency_key,
                        BookingOperation.request_payload,
                    )
                    .where(
                        BookingOperation.status == "pending_verification",
                        BookingOperation.request_payload.is_not(None),
                    )
                    .order_by(BookingOperation.updated_at)
                    .limit(limit)
                )
            ).all()
        return [
            PendingBooking(row.id, row.idempotency_key, row.request_payload)
            for row in rows
            if row.request_payload is not None
        ]

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.infrastructure.database.base import Base


class BookingOperation(Base):
    __tablename__ = "booking_operations"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_booking_operations_idempotency_key"),
        CheckConstraint(
            "operation_type IN ('book', 'reschedule', 'cancel')",
            name="operation_type",
        ),
        CheckConstraint("version > 0", name="positive_version"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    operation_type: Mapped[str] = mapped_column(String(20), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    remote_appointment_id: Mapped[str | None] = mapped_column(String(100))
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    request_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class SlotReservation(Base):
    __tablename__ = "slot_reservations"
    __table_args__ = (
        CheckConstraint("reserved_until > reserved_from", name="valid_time_range"),
        CheckConstraint(
            "status IN ('held', 'pending_remote', 'confirmed', 'expired', 'cancelled')",
            name="status",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    booking_operation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("booking_operations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    practitioner_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    reserved_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reserved_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'published', 'failed')", name="status"),
        CheckConstraint("attempts >= 0", name="nonnegative_attempts"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    aggregate_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MockPmsBusiness(Base):
    __tablename__ = "mock_pms_businesses"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    timezone: Mapped[str] = mapped_column(String(100), nullable=False)


class MockPmsPractitioner(Base):
    __tablename__ = "mock_pms_practitioners"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("mock_pms_businesses.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)


class MockPmsAppointmentType(Base):
    __tablename__ = "mock_pms_appointment_types"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)


class MockPmsPatient(Base):
    __tablename__ = "mock_pms_patients"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone_e164: Mapped[str] = mapped_column(String(20), nullable=False, index=True)


class MockPmsAppointment(Base):
    __tablename__ = "mock_pms_appointments"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="valid_time_range"),
        CheckConstraint("status IN ('booked', 'cancelled')", name="status"),
    )

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    business_id: Mapped[str] = mapped_column(ForeignKey("mock_pms_businesses.id"), nullable=False)
    practitioner_id: Mapped[str] = mapped_column(
        ForeignKey("mock_pms_practitioners.id"), nullable=False, index=True
    )
    appointment_type_id: Mapped[str] = mapped_column(
        ForeignKey("mock_pms_appointment_types.id"), nullable=False
    )
    patient_id: Mapped[str] = mapped_column(ForeignKey("mock_pms_patients.id"), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MockPmsMutation(Base):
    __tablename__ = "mock_pms_mutations"
    __table_args__ = (
        CheckConstraint(
            "operation_type IN ('create', 'reschedule', 'cancel')", name="operation_type"
        ),
    )

    idempotency_key: Mapped[str] = mapped_column(String(200), primary_key=True)
    operation_type: Mapped[str] = mapped_column(String(20), nullable=False)
    appointment_id: Mapped[str] = mapped_column(
        ForeignKey("mock_pms_appointments.id"), nullable=False
    )
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RequestReplay(Base):
    __tablename__ = "request_replays"

    event_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CallSession(Base):
    __tablename__ = "call_sessions"
    __table_args__ = (
        CheckConstraint("direction IN ('inbound', 'outbound')", name="direction"),
        CheckConstraint("status IN ('active', 'completed', 'dropped', 'failed')", name="status"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    platform_call_id: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    caller_phone_e164: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    called_phone_e164: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    language_mode: Mapped[str | None] = mapped_column(String(20))
    patient_id: Mapped[str | None] = mapped_column(String(100))
    checkpoint: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    callback_campaign: Mapped[str | None] = mapped_column(String(100))
    callback_purpose: Mapped[str | None] = mapped_column(String(500))
    disconnect_reason: Mapped[str | None] = mapped_column(String(100))
    resumed_from_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("call_sessions.id")
    )
    resume_consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OutboundContext(Base):
    __tablename__ = "outbound_contexts"
    __table_args__ = (
        CheckConstraint("status IN ('eligible', 'consumed', 'expired')", name="status"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    phone_e164: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    campaign: Mapped[str] = mapped_column(String(100), nullable=False)
    purpose: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FollowUp(Base):
    __tablename__ = "follow_ups"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'completed', 'failed')", name="status"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    call_session_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("call_sessions.id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

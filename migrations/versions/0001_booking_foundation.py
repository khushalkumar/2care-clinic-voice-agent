"""Create booking operations, reservations, and outbox.

Revision ID: 0001_booking_foundation
Revises: None
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_booking_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.create_table(
        "booking_operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation_type", sa.String(length=20), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("remote_appointment_id", sa.String(length=100), nullable=True),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "operation_type IN ('book', 'reschedule', 'cancel')",
            name="ck_booking_operations_operation_type",
        ),
        sa.CheckConstraint("version > 0", name="ck_booking_operations_positive_version"),
        sa.PrimaryKeyConstraint("id", name="pk_booking_operations"),
        sa.UniqueConstraint("idempotency_key", name="uq_booking_operations_idempotency_key"),
    )

    op.create_table(
        "slot_reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("booking_operation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("practitioner_key", sa.String(length=100), nullable=False),
        sa.Column("reserved_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reserved_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('held', 'pending_remote', 'confirmed', 'expired', 'cancelled')",
            name="ck_slot_reservations_status",
        ),
        sa.CheckConstraint(
            "reserved_until > reserved_from", name="ck_slot_reservations_valid_time_range"
        ),
        sa.ForeignKeyConstraint(
            ["booking_operation_id"],
            ["booking_operations.id"],
            name="fk_slot_reservations_booking_operation_id_booking_operations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_slot_reservations"),
        sa.UniqueConstraint(
            "booking_operation_id", name="uq_slot_reservations_booking_operation_id"
        ),
    )
    op.create_index(
        "ix_slot_reservations_practitioner_key",
        "slot_reservations",
        ["practitioner_key"],
    )
    op.execute(
        """
        ALTER TABLE slot_reservations
        ADD CONSTRAINT no_overlapping_practitioner_reservations
        EXCLUDE USING gist (
            practitioner_key WITH =,
            tstzrange(reserved_from, reserved_until, '[)') WITH &&
        )
        WHERE (status IN ('held', 'pending_remote', 'confirmed'))
        """
    )

    op.create_table(
        "outbox_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aggregate_type", sa.String(length=100), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_outbox_events_nonnegative_attempts"),
        sa.CheckConstraint(
            "status IN ('pending', 'published', 'failed')", name="ck_outbox_events_status"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_outbox_events"),
    )
    op.create_index("ix_outbox_events_aggregate_id", "outbox_events", ["aggregate_id"])


def downgrade() -> None:
    op.drop_index("ix_outbox_events_aggregate_id", table_name="outbox_events")
    op.drop_table("outbox_events")
    op.execute(
        """
        ALTER TABLE slot_reservations
        DROP CONSTRAINT no_overlapping_practitioner_reservations
        """
    )
    op.drop_index("ix_slot_reservations_practitioner_key", table_name="slot_reservations")
    op.drop_table("slot_reservations")
    op.drop_table("booking_operations")

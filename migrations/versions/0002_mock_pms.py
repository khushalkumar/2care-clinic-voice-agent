"""Add the durable contract-compatible mock PMS.

Revision ID: 0002_mock_pms
Revises: 0001_booking_foundation
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_mock_pms"
down_revision = "0001_booking_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mock_pms_businesses",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("timezone", sa.String(100), nullable=False),
    )
    op.create_table(
        "mock_pms_appointment_types",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
    )
    op.create_table(
        "mock_pms_patients",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("phone_e164", sa.String(20), nullable=False),
    )
    op.create_index("ix_mock_pms_patients_phone_e164", "mock_pms_patients", ["phone_e164"])
    op.create_table(
        "mock_pms_practitioners",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column(
            "business_id",
            sa.String(100),
            sa.ForeignKey("mock_pms_businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
    )
    op.create_table(
        "mock_pms_appointments",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column(
            "business_id", sa.String(100), sa.ForeignKey("mock_pms_businesses.id"), nullable=False
        ),
        sa.Column(
            "practitioner_id",
            sa.String(100),
            sa.ForeignKey("mock_pms_practitioners.id"),
            nullable=False,
        ),
        sa.Column(
            "appointment_type_id",
            sa.String(100),
            sa.ForeignKey("mock_pms_appointment_types.id"),
            nullable=False,
        ),
        sa.Column(
            "patient_id", sa.String(100), sa.ForeignKey("mock_pms_patients.id"), nullable=False
        ),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("ends_at > starts_at", name="ck_mock_pms_appointments_valid_time_range"),
        sa.CheckConstraint(
            "status IN ('booked', 'cancelled')", name="ck_mock_pms_appointments_status"
        ),
    )
    op.create_index(
        "ix_mock_pms_appointments_practitioner_id", "mock_pms_appointments", ["practitioner_id"]
    )
    op.execute(
        """
        ALTER TABLE mock_pms_appointments
        ADD CONSTRAINT no_overlapping_mock_pms_appointments
        EXCLUDE USING gist (
            practitioner_id WITH =,
            tstzrange(starts_at, ends_at, '[)') WITH &&
        ) WHERE (status = 'booked')
        """
    )
    op.create_table(
        "mock_pms_mutations",
        sa.Column("idempotency_key", sa.String(200), primary_key=True),
        sa.Column("operation_type", sa.String(20), nullable=False),
        sa.Column(
            "appointment_id",
            sa.String(100),
            sa.ForeignKey("mock_pms_appointments.id"),
            nullable=False,
        ),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "operation_type IN ('create', 'reschedule', 'cancel')",
            name="ck_mock_pms_mutations_operation_type",
        ),
    )


def downgrade() -> None:
    op.drop_table("mock_pms_mutations")
    op.execute(
        "ALTER TABLE mock_pms_appointments DROP CONSTRAINT no_overlapping_mock_pms_appointments"
    )
    op.drop_index("ix_mock_pms_appointments_practitioner_id", table_name="mock_pms_appointments")
    op.drop_table("mock_pms_appointments")
    op.drop_table("mock_pms_practitioners")
    op.drop_index("ix_mock_pms_patients_phone_e164", table_name="mock_pms_patients")
    op.drop_table("mock_pms_patients")
    op.drop_table("mock_pms_appointment_types")
    op.drop_table("mock_pms_businesses")

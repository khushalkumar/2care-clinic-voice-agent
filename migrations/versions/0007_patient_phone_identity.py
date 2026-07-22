"""Add durable phone-to-patient identities.

Revision ID: 0007_patient_phone_identity
Revises: 0006_booking_recovery
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_patient_phone_identity"
down_revision = "0006_booking_recovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "patient_phone_identities",
        sa.Column("phone_e164", sa.String(20), nullable=False),
        sa.Column("patient_id", sa.String(100), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("phone_e164", "patient_id"),
    )
    op.execute(
        """
        INSERT INTO patient_phone_identities (phone_e164, patient_id, source, created_at)
        SELECT caller_phone_e164, patient_id, 'call_session_backfill', MIN(started_at)
        FROM call_sessions
        WHERE patient_id IS NOT NULL
        GROUP BY caller_phone_e164, patient_id
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("patient_phone_identities")

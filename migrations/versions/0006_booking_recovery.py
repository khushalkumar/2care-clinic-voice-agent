"""Persist the minimum booking payload required for reconciliation.

Revision ID: 0006_booking_recovery
Revises: 0005_follow_ups
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_booking_recovery"
down_revision = "0005_follow_ups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "booking_operations",
        sa.Column("request_payload", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("booking_operations", "request_payload")

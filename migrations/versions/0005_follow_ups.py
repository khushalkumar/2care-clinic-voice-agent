"""Add durable follow-up work items.

Revision ID: 0005_follow_ups
Revises: 0004_call_state
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_follow_ups"
down_revision = "0004_call_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "follow_ups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "call_session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("call_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(200), nullable=False, unique=True),
        sa.Column("reason", sa.String(200), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'failed')", name="ck_follow_ups_status"
        ),
    )


def downgrade() -> None:
    op.drop_table("follow_ups")

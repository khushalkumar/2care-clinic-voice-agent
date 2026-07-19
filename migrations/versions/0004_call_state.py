"""Add durable call sessions and outbound callback context.

Revision ID: 0004_call_state
Revises: 0003_request_replays
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_call_state"
down_revision = "0003_request_replays"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "call_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("platform_call_id", sa.String(200), nullable=False, unique=True),
        sa.Column("direction", sa.String(20), nullable=False),
        sa.Column("caller_phone_e164", sa.String(20), nullable=False),
        sa.Column("called_phone_e164", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("language_mode", sa.String(20)),
        sa.Column("patient_id", sa.String(100)),
        sa.Column("checkpoint", postgresql.JSONB(), nullable=False),
        sa.Column("callback_campaign", sa.String(100)),
        sa.Column("callback_purpose", sa.String(500)),
        sa.Column("disconnect_reason", sa.String(100)),
        sa.Column("resumed_from_id", postgresql.UUID(as_uuid=True)),
        sa.Column("resume_consumed_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "direction IN ('inbound', 'outbound')", name="ck_call_sessions_direction"
        ),
        sa.CheckConstraint(
            "status IN ('active', 'completed', 'dropped', 'failed')",
            name="ck_call_sessions_status",
        ),
        sa.ForeignKeyConstraint(
            ["resumed_from_id"], ["call_sessions.id"], name="fk_call_sessions_resumed_from"
        ),
    )
    op.create_index("ix_call_sessions_caller_phone_e164", "call_sessions", ["caller_phone_e164"])
    op.create_table(
        "outbound_contexts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("phone_e164", sa.String(20), nullable=False),
        sa.Column("campaign", sa.String(100), nullable=False),
        sa.Column("purpose", sa.String(500), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('eligible', 'consumed', 'expired')",
            name="ck_outbound_contexts_status",
        ),
    )
    op.create_index("ix_outbound_contexts_phone_e164", "outbound_contexts", ["phone_e164"])


def downgrade() -> None:
    op.drop_index("ix_outbound_contexts_phone_e164", table_name="outbound_contexts")
    op.drop_table("outbound_contexts")
    op.drop_index("ix_call_sessions_caller_phone_e164", table_name="call_sessions")
    op.drop_table("call_sessions")

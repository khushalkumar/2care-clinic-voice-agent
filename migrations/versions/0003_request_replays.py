"""Add durable request replay claims.

Revision ID: 0003_request_replays
Revises: 0002_mock_pms
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_request_replays"
down_revision = "0002_mock_pms"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "request_replays",
        sa.Column("event_id", sa.String(200), primary_key=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("request_replays")

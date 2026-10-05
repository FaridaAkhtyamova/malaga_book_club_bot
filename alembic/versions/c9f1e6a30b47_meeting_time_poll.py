"""Meeting time polls and cycle winner_meeting_hour

Revision ID: c9f1e6a30b47
Revises: d4c7a2e18f90
Create Date: 2026-09-21 23:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "c9f1e6a30b47"
down_revision: str | Sequence[str] | None = "d4c7a2e18f90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "suggestion_cycles",
        sa.Column("winner_meeting_hour", sa.Integer(), nullable=True),
    )
    op.create_table(
        "meeting_time_polls",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("cycle_id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("telegram_poll_id", sa.String(length=255), nullable=True),
        sa.Column("option_hours", JSONB(), nullable=False),
        sa.Column("is_open", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["cycle_id"], ["suggestion_cycles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("meeting_time_polls")
    op.drop_column("suggestion_cycles", "winner_meeting_hour")

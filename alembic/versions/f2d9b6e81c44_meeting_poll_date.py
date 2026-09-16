"""Meeting date polls and cycle winner_meeting_date

Revision ID: f2d9b6e81c44
Revises: b1f8a4c90d33
Create Date: 2026-09-16 12:40:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op


revision: str = "f2d9b6e81c44"
down_revision: Union[str, Sequence[str], None] = "b1f8a4c90d33"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "suggestion_cycles",
        sa.Column("winner_meeting_date", sa.Date(), nullable=True),
    )
    op.create_table(
        "meeting_polls",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("cycle_id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("telegram_poll_id", sa.String(length=255), nullable=True),
        sa.Column("option_dates", JSONB(), nullable=False),
        sa.Column("is_open", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["cycle_id"], ["suggestion_cycles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("meeting_polls")
    op.drop_column("suggestion_cycles", "winner_meeting_date")

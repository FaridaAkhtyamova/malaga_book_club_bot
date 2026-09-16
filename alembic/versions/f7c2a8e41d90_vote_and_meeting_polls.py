"""Meeting polls and cycle meeting date

Revision ID: f7c2a8e41d90
Revises: b1f8a4c90d33
Create Date: 2026-09-16 13:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection

from alembic import op

revision: str = "f7c2a8e41d90"
down_revision: Union[str, Sequence[str], None] = "b1f8a4c90d33"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(connection: Connection, table: str) -> set[str]:
    return {column["name"] for column in inspect(connection).get_columns(table)}


def _tables(connection: Connection) -> set[str]:
    return set(inspect(connection).get_table_names())


def upgrade() -> None:
    connection = op.get_bind()
    cycle_columns = _columns(connection, "suggestion_cycles")
    if "winner_meeting_date" not in cycle_columns:
        op.add_column(
            "suggestion_cycles",
            sa.Column("winner_meeting_date", sa.Date(), nullable=True),
        )

    if "meeting_polls" not in _tables(connection):
        op.create_table(
            "meeting_polls",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("cycle_id", sa.Integer(), nullable=False),
            sa.Column("chat_id", sa.BigInteger(), nullable=False),
            sa.Column("message_id", sa.Integer(), nullable=False),
            sa.Column("telegram_poll_id", sa.String(length=255), nullable=True),
            sa.Column("option_dates", JSONB(), nullable=False),
            sa.Column("is_open", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["cycle_id"], ["suggestion_cycles.id"]),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade() -> None:
    connection = op.get_bind()
    if "meeting_polls" in _tables(connection):
        op.drop_table("meeting_polls")
    if "winner_meeting_date" in _columns(connection, "suggestion_cycles"):
        op.drop_column("suggestion_cycles", "winner_meeting_date")

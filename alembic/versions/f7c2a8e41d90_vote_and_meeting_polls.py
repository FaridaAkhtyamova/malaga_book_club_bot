"""Vote polls, meeting polls, cycle winner fields

Revision ID: f7c2a8e41d90
Revises: e4a91c7b6d20
Create Date: 2026-09-16 13:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection

from alembic import op

revision: str = "f7c2a8e41d90"
down_revision: Union[str, Sequence[str], None] = "e4a91c7b6d20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(connection: Connection, table: str) -> set[str]:
    return {column["name"] for column in inspect(connection).get_columns(table)}


def _foreign_key_names(connection: Connection, table: str, column: str) -> list[str]:
    names: list[str] = []
    for fk in inspect(connection).get_foreign_keys(table):
        if fk.get("constrained_columns") == [column] and fk.get("name"):
            names.append(str(fk["name"]))
    return names


def upgrade() -> None:
    connection = op.get_bind()
    cycle_columns = _columns(connection, "suggestion_cycles")
    if "winner_book_id" not in cycle_columns:
        op.add_column(
            "suggestion_cycles",
            sa.Column("winner_book_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "fk_suggestion_cycles_winner_book_id",
            "suggestion_cycles",
            "books",
            ["winner_book_id"],
            ["id"],
        )
    if "winner_meeting_date" not in cycle_columns:
        op.add_column(
            "suggestion_cycles",
            sa.Column("winner_meeting_date", sa.Date(), nullable=True),
        )

    existing = _tables(connection)
    if "vote_polls" not in existing:
        op.create_table(
            "vote_polls",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("cycle_id", sa.Integer(), nullable=False),
            sa.Column("chat_id", sa.BigInteger(), nullable=False),
            sa.Column("message_id", sa.Integer(), nullable=False),
            sa.Column("telegram_poll_id", sa.String(length=255), nullable=True),
            sa.Column("option_book_ids", JSONB(), nullable=False),
            sa.Column("is_open", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["cycle_id"], ["suggestion_cycles.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    if "meeting_polls" not in existing:
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
    existing = _tables(connection)
    if "meeting_polls" in existing:
        op.drop_table("meeting_polls")
    if "vote_polls" in existing:
        op.drop_table("vote_polls")

    cycle_columns = _columns(connection, "suggestion_cycles")
    if "winner_meeting_date" in cycle_columns:
        op.drop_column("suggestion_cycles", "winner_meeting_date")
    if "winner_book_id" in cycle_columns:
        for name in _foreign_key_names(connection, "suggestion_cycles", "winner_book_id"):
            op.drop_constraint(name, "suggestion_cycles", type_="foreignkey")
        op.drop_column("suggestion_cycles", "winner_book_id")

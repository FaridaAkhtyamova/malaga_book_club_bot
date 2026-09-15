"""Cycle winner and Telegram vote poll records

Revision ID: b1f8a4c90d33
Revises: e4a91c7b6d20
Create Date: 2026-09-15 14:50:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op


revision: str = "b1f8a4c90d33"
down_revision: Union[str, Sequence[str], None] = "e4a91c7b6d20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
    op.create_table(
        "vote_polls",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("cycle_id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("telegram_poll_id", sa.String(length=255), nullable=True),
        sa.Column("option_book_ids", JSONB(), nullable=False),
        sa.Column("is_open", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["cycle_id"], ["suggestion_cycles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("vote_polls")
    op.drop_constraint(
        "fk_suggestion_cycles_winner_book_id",
        "suggestion_cycles",
        type_="foreignkey",
    )
    op.drop_column("suggestion_cycles", "winner_book_id")

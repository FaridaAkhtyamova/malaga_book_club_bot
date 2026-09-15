"""Suggestion cycles, club settings, book page_count

Revision ID: c8e4f1a92b07
Revises: 3b20c6d0ab5e
Create Date: 2026-09-14 12:20:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op


revision: str = "c8e4f1a92b07"
down_revision: Union[str, Sequence[str], None] = "3b20c6d0ab5e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("books", sa.Column("page_count", sa.Integer(), nullable=True))
    op.create_table(
        "club_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("group_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("suggest_day", sa.Integer(), nullable=True),
        sa.Column("vote_day", sa.Integer(), nullable=True),
        sa.Column("announce_hour", sa.Integer(), nullable=False, server_default="10"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "suggestion_cycles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("target_year", sa.Integer(), nullable=False),
        sa.Column("target_month", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("opened_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("target_year", "target_month", name="uq_cycle_target_month"),
    )
    op.create_table(
        "suggestions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("cycle_id", sa.Integer(), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"]),
        sa.ForeignKeyConstraint(["cycle_id"], ["suggestion_cycles.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cycle_id", "book_id", name="uq_suggestion_cycle_book"),
    )


def downgrade() -> None:
    op.drop_table("suggestions")
    op.drop_table("suggestion_cycles")
    op.drop_table("club_settings")
    op.drop_column("books", "page_count")

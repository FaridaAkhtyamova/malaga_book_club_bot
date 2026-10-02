"""Link approved group cards to suggested books

Revision ID: f6a2d9c4b108
Revises: a1b8c4d27e90
Create Date: 2026-10-01 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6a2d9c4b108"
down_revision: str | Sequence[str] | None = "a1b8c4d27e90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "pending_group_cards",
        sa.Column("approved_book_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_pending_group_cards_approved_book_id_books",
        "pending_group_cards",
        "books",
        ["approved_book_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_pending_group_cards_approved_book_id_books",
        "pending_group_cards",
        type_="foreignkey",
    )
    op.drop_column("pending_group_cards", "approved_book_id")
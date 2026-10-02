"""Track Telegram messages associated with book suggestions

Revision ID: 6e2a9f7c1d43
Revises: f6a2d9c4b108
Create Date: 2026-10-02 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6e2a9f7c1d43"
down_revision: str | Sequence[str] | None = "f6a2d9c4b108"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("suggestions", sa.Column("source_chat_id", sa.BigInteger(), nullable=True))
    op.add_column("suggestions", sa.Column("source_message_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("suggestions", "source_message_id")
    op.drop_column("suggestions", "source_chat_id")
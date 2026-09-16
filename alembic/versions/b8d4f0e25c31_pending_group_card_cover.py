"""Cover file id on pending group cards

Revision ID: b8d4f0e25c31
Revises: a7c3e9d14b20
Create Date: 2026-09-16 22:55:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op


revision: str = "b8d4f0e25c31"
down_revision: Union[str, Sequence[str], None] = "a7c3e9d14b20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pending_group_cards",
        sa.Column("cover_url", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("pending_group_cards", "cover_url")

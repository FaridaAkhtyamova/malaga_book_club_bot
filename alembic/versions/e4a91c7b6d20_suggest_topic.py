"""Club settings suggest_topic_id

Revision ID: e4a91c7b6d20
Revises: c8e4f1a92b07
Create Date: 2026-09-14 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e4a91c7b6d20"
down_revision: str | Sequence[str] | None = "c8e4f1a92b07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("club_settings", sa.Column("suggest_topic_id", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("club_settings", "suggest_topic_id")

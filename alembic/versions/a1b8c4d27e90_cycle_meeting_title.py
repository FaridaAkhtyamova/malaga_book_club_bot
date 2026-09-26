"""Cycle meeting_title override for extra-book polls

Revision ID: a1b8c4d27e90
Revises: c9f1e6a30b47
Create Date: 2026-09-24 14:34:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op


revision: str = "a1b8c4d27e90"
down_revision: Union[str, Sequence[str], None] = "c9f1e6a30b47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "suggestion_cycles",
        sa.Column("meeting_title", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("suggestion_cycles", "meeting_title")

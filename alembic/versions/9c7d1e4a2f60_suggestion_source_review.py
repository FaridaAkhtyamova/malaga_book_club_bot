"""Track admin approval for unavailable suggestion source messages

Revision ID: 9c7d1e4a2f60
Revises: 6e2a9f7c1d43
Create Date: 2026-10-05 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9c7d1e4a2f60"
down_revision: str | Sequence[str] | None = "6e2a9f7c1d43"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "suggestions",
        sa.Column(
            "source_reviewed",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("suggestions", "source_reviewed")

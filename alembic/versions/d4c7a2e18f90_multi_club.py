"""One club settings row per group, cycles scoped to a club

Revision ID: d4c7a2e18f90
Revises: b8d4f0e25c31
Create Date: 2026-09-19 23:50:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op


revision: str = "d4c7a2e18f90"
down_revision: Union[str, Sequence[str], None] = "b8d4f0e25c31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("club_settings", sa.Column("title", sa.String(length=255), nullable=True))
    op.create_unique_constraint(
        "uq_club_settings_group_chat_id",
        "club_settings",
        ["group_chat_id"],
    )

    op.add_column("suggestion_cycles", sa.Column("club_id", sa.Integer(), nullable=True))
    op.execute(
        """
        INSERT INTO club_settings (announce_hour)
        SELECT 10
        WHERE NOT EXISTS (SELECT 1 FROM club_settings)
          AND EXISTS (SELECT 1 FROM suggestion_cycles)
        """
    )
    op.execute(
        """
        UPDATE suggestion_cycles
        SET club_id = (SELECT id FROM club_settings ORDER BY id LIMIT 1)
        WHERE club_id IS NULL
        """
    )
    op.alter_column("suggestion_cycles", "club_id", existing_type=sa.Integer(), nullable=False)
    op.create_foreign_key(
        "fk_suggestion_cycles_club_id",
        "suggestion_cycles",
        "club_settings",
        ["club_id"],
        ["id"],
    )
    op.drop_constraint("uq_cycle_target_month", "suggestion_cycles", type_="unique")
    op.create_unique_constraint(
        "uq_cycle_club_target_month",
        "suggestion_cycles",
        ["club_id", "target_year", "target_month"],
    )

    op.add_column("users", sa.Column("active_club_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_users_active_club_id",
        "users",
        "club_settings",
        ["active_club_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_users_active_club_id", "users", type_="foreignkey")
    op.drop_column("users", "active_club_id")

    op.drop_constraint("uq_cycle_club_target_month", "suggestion_cycles", type_="unique")
    op.create_unique_constraint(
        "uq_cycle_target_month",
        "suggestion_cycles",
        ["target_year", "target_month"],
    )
    op.drop_constraint("fk_suggestion_cycles_club_id", "suggestion_cycles", type_="foreignkey")
    op.drop_column("suggestion_cycles", "club_id")

    op.drop_constraint("uq_club_settings_group_chat_id", "club_settings", type_="unique")
    op.drop_column("club_settings", "title")

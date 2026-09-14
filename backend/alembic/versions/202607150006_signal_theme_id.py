"""signal theme id

Revision ID: 202607150006
Revises: 202607150005
Create Date: 2026-07-15
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "202607150006"
down_revision: str | None = "202607150005"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table("investment_signal") as batch_op:
        batch_op.add_column(sa.Column("theme_id", sa.String(64), nullable=True))
        batch_op.create_foreign_key(
            "fk_investment_signal_theme_id",
            "investment_theme",
            ["theme_id"],
            ["id"],
        )
    op.create_index(
        "idx_investment_signal_theme",
        "investment_signal",
        ["workspace_id", "theme_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_investment_signal_theme", table_name="investment_signal")
    with op.batch_alter_table("investment_signal") as batch_op:
        batch_op.drop_constraint("fk_investment_signal_theme_id", type_="foreignkey")
        batch_op.drop_column("theme_id")

"""investment digest snapshots

Revision ID: 202607150004
Revises: 202607150003
Create Date: 2026-07-15 11:55:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "202607150004"
down_revision: str | None = "202607150003"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "investment_digest_snapshot",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("watchlist_id", sa.String(length=64), nullable=True),
        sa.Column("digest_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("digest", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["watchlist_id"], ["investment_watchlist.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_investment_digest_snapshot_scope",
        "investment_digest_snapshot",
        ["workspace_id", "watchlist_id"],
        unique=False,
    )
    op.create_index(
        "idx_investment_digest_snapshot_date",
        "investment_digest_snapshot",
        ["workspace_id", "digest_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_investment_digest_snapshot_date", table_name="investment_digest_snapshot")
    op.drop_index("idx_investment_digest_snapshot_scope", table_name="investment_digest_snapshot")
    op.drop_table("investment_digest_snapshot")

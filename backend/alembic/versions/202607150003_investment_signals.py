"""investment signals: early signals clustered from facts

Revision ID: 202607150003
Revises: 202607150002
Create Date: 2026-07-15 11:45:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "202607150003"
down_revision: str | None = "202607150002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "investment_signal",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("watchlist_id", sa.String(length=64), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("signal_type", sa.String(length=64), server_default="other", nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("fact_ids", sa.JSON(), nullable=True),
        sa.Column("item_ids", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="tracking", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["watchlist_id"], ["investment_watchlist.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_investment_signal_watchlist",
        "investment_signal",
        ["workspace_id", "watchlist_id"],
        unique=False,
    )
    op.create_index(
        "idx_investment_signal_status",
        "investment_signal",
        ["workspace_id", "status"],
        unique=False,
    )
    op.create_index(
        "idx_investment_signal_seen",
        "investment_signal",
        ["workspace_id", "last_seen_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_investment_signal_seen", table_name="investment_signal")
    op.drop_index("idx_investment_signal_status", table_name="investment_signal")
    op.drop_index("idx_investment_signal_watchlist", table_name="investment_signal")
    op.drop_table("investment_signal")

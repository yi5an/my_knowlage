"""investment facts: extracted evidence-backed facts

Revision ID: 202607150002
Revises: 202607140001
Create Date: 2026-07-15 11:35:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "202607150002"
down_revision: str | None = "202607140001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "investment_fact",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("source_item_id", sa.String(length=64), nullable=False),
        sa.Column("watchlist_id", sa.String(length=64), nullable=True),
        sa.Column("fact_text", sa.Text(), nullable=False),
        sa.Column("fact_text_zh", sa.Text(), nullable=True),
        sa.Column("fact_type", sa.String(length=64), server_default="other", nullable=False),
        sa.Column("entities", sa.JSON(), nullable=True),
        sa.Column("evidence_url", sa.Text(), nullable=True),
        sa.Column("evidence_excerpt", sa.Text(), nullable=False),
        sa.Column("evidence_timestamp", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "verification_status",
            sa.String(length=32),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["source_item_id"], ["investment_item.id"]),
        sa.ForeignKeyConstraint(["watchlist_id"], ["investment_watchlist.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_investment_fact_item",
        "investment_fact",
        ["workspace_id", "source_item_id"],
        unique=False,
    )
    op.create_index(
        "idx_investment_fact_watchlist",
        "investment_fact",
        ["workspace_id", "watchlist_id"],
        unique=False,
    )
    op.create_index(
        "idx_investment_fact_status",
        "investment_fact",
        ["workspace_id", "verification_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_investment_fact_status", table_name="investment_fact")
    op.drop_index("idx_investment_fact_watchlist", table_name="investment_fact")
    op.drop_index("idx_investment_fact_item", table_name="investment_fact")
    op.drop_table("investment_fact")

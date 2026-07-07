"""Add workspace-level settings table.

Revision ID: 202607060001
Revises: 202607020002
Create Date: 2026-07-06 18:05:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "202607060001"
down_revision: str | None = "202607020002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "workspace_setting",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "key", name="uq_workspace_setting_key"),
    )
    op.create_index(
        "idx_workspace_setting_workspace",
        "workspace_setting",
        ["workspace_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_workspace_setting_workspace", table_name="workspace_setting")
    op.drop_table("workspace_setting")

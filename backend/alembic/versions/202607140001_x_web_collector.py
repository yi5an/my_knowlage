"""Add X Web collector heartbeat state.

Revision ID: 202607140001
Revises: 202607080001
Create Date: 2026-07-14 18:30:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "202607140001"
down_revision: str | None = "202607080001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "x_collector_state",
        sa.Column("collector_id", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("login_status", sa.String(length=32), nullable=False),
        sa.Column("queue_size", sa.Integer(), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("collector_id"),
    )
    op.create_index(
        "idx_x_collector_heartbeat",
        "x_collector_state",
        ["heartbeat_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_x_collector_heartbeat", table_name="x_collector_state")
    op.drop_table("x_collector_state")

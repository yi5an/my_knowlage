"""add managed model credentials and routes

Revision ID: 202607170003
Revises: 202607170002
Create Date: 2026-07-17
"""

import sqlalchemy as sa

from alembic import op

revision = "202607170003"
down_revision = "202607170002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("model_provider") as batch:
        batch.add_column(sa.Column("api_key_ciphertext", sa.Text(), nullable=True))
        batch.add_column(sa.Column("api_key_hint", sa.String(length=32), nullable=True))
        batch.add_column(
            sa.Column("timeout_seconds", sa.Float(), nullable=False, server_default="120")
        )
        batch.add_column(sa.Column("last_test_status", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("last_test_message", sa.Text(), nullable=True))
        batch.add_column(sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "model_route",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("capability", sa.String(length=32), nullable=False),
        sa.Column("model_config_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["model_config_id"], ["model_config.id"]),
        sa.UniqueConstraint("capability", name="uq_model_route_capability"),
    )


def downgrade() -> None:
    op.drop_table("model_route")
    with op.batch_alter_table("model_provider") as batch:
        batch.drop_column("last_tested_at")
        batch.drop_column("last_test_message")
        batch.drop_column("last_test_status")
        batch.drop_column("timeout_seconds")
        batch.drop_column("api_key_hint")
        batch.drop_column("api_key_ciphertext")

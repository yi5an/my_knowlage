"""add stable provenance keys to investment facts and signals

Revision ID: 202609030002
Revises: 202609030001
Create Date: 2026-09-03
"""

import sqlalchemy as sa

from alembic import op

revision = "202609030002"
down_revision = "202609030001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Legacy rows remain nullable until the evidence-aware backfill can derive a
    # key from a validated anchor. Guessing here would make unstable identities.
    op.add_column("investment_fact", sa.Column("canonical_key", sa.String(64)))
    op.add_column(
        "investment_fact",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "investment_fact",
        sa.Column("supersedes_id", sa.String(64)),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.create_foreign_key(
            "fk_investment_fact_supersedes",
            "investment_fact",
            "investment_fact",
            ["supersedes_id"],
            ["id"],
        )
    op.create_index(
        "uq_investment_fact_active_canonical",
        "investment_fact",
        ["workspace_id", "canonical_key"],
        unique=True,
        postgresql_where=sa.text("canonical_key IS NOT NULL AND is_active"),
        sqlite_where=sa.text("canonical_key IS NOT NULL AND is_active = 1"),
    )

    op.add_column("investment_signal", sa.Column("canonical_key", sa.String(64)))
    op.add_column(
        "investment_signal",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "investment_signal",
        sa.Column("supersedes_id", sa.String(64)),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.create_foreign_key(
            "fk_investment_signal_supersedes",
            "investment_signal",
            "investment_signal",
            ["supersedes_id"],
            ["id"],
        )
    op.create_index(
        "uq_investment_signal_active_canonical",
        "investment_signal",
        ["workspace_id", "canonical_key"],
        unique=True,
        postgresql_where=sa.text("canonical_key IS NOT NULL AND is_active"),
        sqlite_where=sa.text("canonical_key IS NOT NULL AND is_active = 1"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_investment_signal_active_canonical", table_name="investment_signal"
    )
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint(
            "fk_investment_signal_supersedes",
            "investment_signal",
            type_="foreignkey",
        )
    op.drop_column("investment_signal", "supersedes_id")
    op.drop_column("investment_signal", "is_active")
    op.drop_column("investment_signal", "canonical_key")

    op.drop_index("uq_investment_fact_active_canonical", table_name="investment_fact")
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint(
            "fk_investment_fact_supersedes",
            "investment_fact",
            type_="foreignkey",
        )
    op.drop_column("investment_fact", "supersedes_id")
    op.drop_column("investment_fact", "is_active")
    op.drop_column("investment_fact", "canonical_key")

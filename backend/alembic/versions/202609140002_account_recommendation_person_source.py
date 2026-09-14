"""link account recommendations to their person source records

Revision ID: 202609140002
Revises: 202609140001
Create Date: 2026-09-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202609140002"
down_revision: str | None = "202609140001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "investment_account_recommendation",
        sa.Column(
            "person_source_id",
            sa.String(64),
            sa.ForeignKey("investment_person_source.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_account_recommendation_person_source",
        "investment_account_recommendation",
        ["workspace_id", "person_source_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_account_recommendation_person_source",
        table_name="investment_account_recommendation",
    )
    op.drop_column("investment_account_recommendation", "person_source_id")


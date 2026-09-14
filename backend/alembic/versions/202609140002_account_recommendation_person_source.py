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


def _add_person_source_column() -> None:
    column = sa.Column(
        "person_source_id",
        sa.String(64),
        sa.ForeignKey(
            "investment_person_source.id",
            name="fk_account_recommendation_person_source",
        ),
        nullable=True,
    )
    if op.get_context().dialect.name == "sqlite":
        with op.batch_alter_table(
            "investment_account_recommendation", recreate="always"
        ) as batch_op:
            batch_op.add_column(column)
    else:
        op.add_column("investment_account_recommendation", column)


def _drop_person_source_column() -> None:
    if op.get_context().dialect.name == "sqlite":
        with op.batch_alter_table(
            "investment_account_recommendation", recreate="always"
        ) as batch_op:
            batch_op.drop_column("person_source_id")
    else:
        op.drop_column("investment_account_recommendation", "person_source_id")


def _backfill_person_source_ids() -> None:
    recommendation = sa.table(
        "investment_account_recommendation",
        sa.column("id", sa.String(64)),
        sa.column("workspace_id", sa.String(64)),
        sa.column("platform", sa.String(32)),
        sa.column("handle", sa.String(255)),
        sa.column("person_source_id", sa.String(64)),
    )
    person_source = sa.table(
        "investment_person_source",
        sa.column("id", sa.String(64)),
        sa.column("workspace_id", sa.String(64)),
        sa.column("platform", sa.String(32)),
        sa.column("handle", sa.String(255)),
    )
    match = sa.and_(
        person_source.c.workspace_id == recommendation.c.workspace_id,
        sa.func.lower(person_source.c.platform) == sa.func.lower(recommendation.c.platform),
        sa.func.lower(sa.func.replace(person_source.c.handle, "@", ""))
        == sa.func.lower(sa.func.replace(recommendation.c.handle, "@", "")),
    )
    matching_id = sa.select(person_source.c.id).where(match).limit(1).scalar_subquery()
    matching_count = sa.select(sa.func.count(person_source.c.id)).where(match).scalar_subquery()
    op.execute(
        sa.update(recommendation)
        .where(recommendation.c.person_source_id.is_(None))
        .where(matching_count == 1)
        .values(person_source_id=matching_id)
    )


def upgrade() -> None:
    _add_person_source_column()
    op.create_index(
        "idx_account_recommendation_person_source",
        "investment_account_recommendation",
        ["workspace_id", "person_source_id"],
    )
    _backfill_person_source_ids()


def downgrade() -> None:
    op.drop_index(
        "idx_account_recommendation_person_source",
        table_name="investment_account_recommendation",
    )
    _drop_person_source_column()

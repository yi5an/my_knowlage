"""investment_item: add title_zh / summary_zh for LLM translation

Revision ID: 202607020002
Revises: 202607020001
Create Date: 2026-07-02 00:02:00.000000

Adds two nullable text columns to ``investment_item`` so the async
``investment_translation`` job can store Chinese translations of the (often
English) fetched title/summary. Untranslated rows are NULL and the frontend
falls back to the original ``title``/``summary``.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202607020002"
down_revision: str | None = "202607020001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("investment_item", sa.Column("title_zh", sa.Text(), nullable=True))
    op.add_column("investment_item", sa.Column("summary_zh", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("investment_item", "summary_zh")
    op.drop_column("investment_item", "title_zh")

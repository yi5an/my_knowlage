"""document: add is_unread column for unread summary indicator

Revision ID: 202606230001
Revises: 202606180001
Create Date: 2026-06-23 00:01:00.000000

Adds a boolean ``is_unread`` to ``document`` so the UI can show a star/badge
on summaries the user hasn't opened yet. Defaults to true; flipped to false
when the card page is viewed.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202606230001"
down_revision: str | None = "202606180001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default ensures existing rows (and any created outside the ORM)
    # are treated as unread, matching the new-column default.
    op.add_column(
        "document",
        sa.Column(
            "is_unread",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )


def downgrade() -> None:
    op.drop_column("document", "is_unread")

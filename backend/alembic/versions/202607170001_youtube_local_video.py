"""add YouTube local video download fields

Revision ID: 202607170001
Revises: 202607150006
Create Date: 2026-07-17
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "202607170001"
down_revision: str | None = "202607150006"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "video",
        sa.Column(
            "local_video_status",
            sa.String(length=32),
            server_default="not_downloaded",
            nullable=False,
        ),
    )
    op.add_column("video", sa.Column("local_video_path", sa.Text()))
    op.add_column("video", sa.Column("local_video_size", sa.BigInteger()))
    op.add_column("video", sa.Column("local_video_downloaded_at", sa.DateTime(timezone=True)))
    op.add_column("video", sa.Column("local_video_error", sa.Text()))


def downgrade() -> None:
    op.drop_column("video", "local_video_error")
    op.drop_column("video", "local_video_downloaded_at")
    op.drop_column("video", "local_video_size")
    op.drop_column("video", "local_video_path")
    op.drop_column("video", "local_video_status")

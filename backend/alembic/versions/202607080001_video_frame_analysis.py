"""Add YouTube visual frame analysis table.

Revision ID: 202607080001
Revises: 202607060001
Create Date: 2026-07-08 15:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "202607080001"
down_revision: str | None = "202607060001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "video_frame_analysis",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("video_id", sa.String(length=64), nullable=False),
        sa.Column("timestamp_sec", sa.Float(), nullable=False),
        sa.Column("timestamp_str", sa.String(length=32), nullable=False),
        sa.Column("image_path", sa.Text(), nullable=False),
        sa.Column("perceptual_hash", sa.String(length=64), nullable=False),
        sa.Column("frame_type", sa.String(length=32), server_default="other"),
        sa.Column("ocr_text", sa.Text(), server_default=""),
        sa.Column("ocr_blocks", sa.JSON(), nullable=False),
        sa.Column("structured_notes", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["video_id"], ["video.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "video_id",
            "timestamp_sec",
            "perceptual_hash",
            name="uq_video_frame_analysis_frame",
        ),
    )
    op.create_index(
        "idx_video_frame_analysis_video",
        "video_frame_analysis",
        ["video_id", "timestamp_sec"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_video_frame_analysis_video", table_name="video_frame_analysis")
    op.drop_table("video_frame_analysis")

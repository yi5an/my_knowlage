"""youtube source: subscription and video tables

Revision ID: 202606180001
Revises: 202605150001
Create Date: 2026-06-18 00:01:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "202606180001"
down_revision: str | None = "202605150001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

json_obj = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")
json_arr = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def timestamp(timezone: bool = True) -> sa.DateTime:
    return sa.DateTime(timezone=timezone)


def upgrade() -> None:
    # video must exist before document.video_id FK can reference it.
    op.create_table(
        "video",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), nullable=False),
        sa.Column("subscription_id", sa.String(64)),
        sa.Column("platform", sa.String(32), server_default="youtube"),
        sa.Column("video_id", sa.String(128), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("channel_id", sa.String(128)),
        sa.Column("channel_name", sa.String(255)),
        sa.Column("duration_sec", sa.Integer()),
        sa.Column("published_at", timestamp()),
        sa.Column("thumbnail_url", sa.Text()),
        sa.Column("description", sa.Text()),
        sa.Column("chapters", json_arr, server_default=sa.text("'[]'")),
        sa.Column("fetch_status", sa.String(32), server_default="pending"),
        sa.Column("error_message", sa.Text()),
        sa.Column("metadata", json_obj, server_default=sa.text("'{}'")),
        sa.Column("created_at", timestamp(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"]),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscription.id"]),
        sa.UniqueConstraint("workspace_id", "video_id", name="uq_video_workspace_video"),
    )

    op.create_table(
        "subscription",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), nullable=False),
        sa.Column("platform", sa.String(32), server_default="youtube"),
        sa.Column("channel_id", sa.String(128), nullable=False),
        sa.Column("channel_name", sa.String(255)),
        sa.Column("thumbnail_url", sa.Text()),
        sa.Column("poll_interval", sa.Integer(), server_default="3600"),
        sa.Column("last_polled_at", timestamp()),
        sa.Column("next_poll_at", timestamp()),
        sa.Column("last_video_id", sa.String(128)),
        sa.Column("last_error", sa.Text()),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("metadata", json_obj, server_default=sa.text("'{}'")),
        sa.Column("created_at", timestamp(), server_default=sa.func.now()),
        sa.Column("updated_at", timestamp(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"]),
        sa.UniqueConstraint(
            "workspace_id",
            "platform",
            "channel_id",
            name="uq_subscription_workspace_platform_channel",
        ),
    )

    # Add the FK from subscription back to video now that both tables exist.
    # (video.subscription_id was declared nullable so table creation above did
    #  not require subscription to pre-exist.)
    op.create_index("idx_video_subscription", "video", ["subscription_id"])
    op.create_index("idx_video_fetch_status", "video", ["fetch_status"])
    op.create_index("idx_subscription_enabled", "subscription", ["enabled", "next_poll_at"])

    # Extend the document table with YouTube-specific columns.
    with op.batch_alter_table("document", schema=None) as batch_op:
        batch_op.add_column(sa.Column("video_id", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("summary_json", json_obj, nullable=True))
        batch_op.add_column(sa.Column("transcript_lang", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("mindmap_data", json_obj, nullable=True))
        batch_op.create_foreign_key(
            "fk_document_video_id",
            "video",
            ["video_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("document", schema=None) as batch_op:
        batch_op.drop_constraint("fk_document_video_id", type_="foreignkey")
        batch_op.drop_column("mindmap_data")
        batch_op.drop_column("transcript_lang")
        batch_op.drop_column("summary_json")
        batch_op.drop_column("video_id")

    op.drop_index("idx_subscription_enabled", table_name="subscription")
    op.drop_index("idx_video_fetch_status", table_name="video")
    op.drop_index("idx_video_subscription", table_name="video")
    op.drop_table("subscription")
    op.drop_table("video")

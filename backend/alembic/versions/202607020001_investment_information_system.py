"""investment information system

Revision ID: 202607020001
Revises: 202606230001
Create Date: 2026-07-02 00:01:00.000000

Adds the investment information system tables: watchlist, source, item,
thesis, claim and macro_event. Fetch jobs reuse the existing ``task_job``
table (job_type='investment_fetch'), so there is no separate
investment_fetch_job table here.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON, Text

from alembic import op

revision: str = "202607020001"
down_revision: str | None = "202606230001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# JSON column portable across SQLite (JSON) and Postgres (JSONB).
JsonType = JSON().with_variant(JSONB(astext_type=Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "investment_watchlist",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "workspace_id", sa.String(length=64), sa.ForeignKey("workspace.id"), nullable=False
        ),
        sa.Column("entity_id", sa.String(length=64)),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("watch_type", sa.String(length=32), server_default="stock"),
        sa.Column("ticker", sa.String(length=64)),
        sa.Column("exchange", sa.String(length=32)),
        sa.Column("keywords", JsonType, server_default="[]"),
        sa.Column("importance", sa.String(length=32), server_default="medium"),
        sa.Column("notes", sa.Text()),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "investment_source",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "workspace_id", sa.String(length=64), sa.ForeignKey("workspace.id"), nullable=False
        ),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("url", sa.Text()),
        sa.Column("config", JsonType, server_default="{}"),
        sa.Column("default_info_layer", sa.String(length=32), server_default="news"),
        sa.Column("default_watchlist_ids", JsonType, server_default="[]"),
        sa.Column("poll_interval_seconds", sa.Integer(), server_default="3600"),
        sa.Column("last_polled_at", sa.DateTime(timezone=True)),
        sa.Column("next_poll_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_investment_source_due", "investment_source", ["enabled", "next_poll_at"])

    op.create_table(
        "investment_item",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "workspace_id", sa.String(length=64), sa.ForeignKey("workspace.id"), nullable=False
        ),
        sa.Column("document_id", sa.String(length=64), sa.ForeignKey("document.id")),
        sa.Column("source_id", sa.String(length=64), sa.ForeignKey("investment_source.id")),
        sa.Column("dedupe_key", sa.String(length=128), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text()),
        sa.Column("source_name", sa.String(length=255)),
        sa.Column("info_layer", sa.String(length=32), server_default="news"),
        sa.Column("source_credibility", sa.String(length=32), server_default="unverified"),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("event_at", sa.DateTime(timezone=True)),
        sa.Column("summary", sa.Text()),
        sa.Column("importance", sa.String(length=32), server_default="medium"),
        sa.Column("impact_direction", sa.String(length=32), server_default="neutral"),
        sa.Column("impact_horizon", sa.String(length=32), server_default="unknown"),
        sa.Column("thesis_impact", sa.String(length=32), server_default="unknown"),
        sa.Column("action_status", sa.String(length=32), server_default="pending_review"),
        sa.Column("review_at", sa.DateTime(timezone=True)),
        sa.Column("raw_payload", JsonType, server_default="{}"),
        sa.Column("suggested_importance", sa.String(length=32)),
        sa.Column("suggested_impact_direction", sa.String(length=32)),
        sa.Column("suggested_impact_horizon", sa.String(length=32)),
        sa.Column("suggested_thesis_impact", sa.String(length=32)),
        sa.Column("classification_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "dedupe_key", name="uq_investment_item_dedupe"),
    )
    op.create_index(
        "idx_investment_item_workspace_layer_status",
        "investment_item",
        ["workspace_id", "info_layer", "action_status"],
    )
    op.create_index(
        "idx_investment_item_published", "investment_item", ["workspace_id", "published_at"]
    )

    op.create_table(
        "investment_thesis",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "workspace_id", sa.String(length=64), sa.ForeignKey("workspace.id"), nullable=False
        ),
        sa.Column(
            "watchlist_id", sa.String(length=64), sa.ForeignKey("investment_watchlist.id")
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text()),
        sa.Column("status", sa.String(length=32), server_default="open"),
        sa.Column("confidence", sa.String(length=32), server_default="medium"),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "idx_investment_thesis_watchlist", "investment_thesis", ["workspace_id", "watchlist_id"]
    )

    op.create_table(
        "investment_claim",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "workspace_id", sa.String(length=64), sa.ForeignKey("workspace.id"), nullable=False
        ),
        sa.Column("source_item_id", sa.String(length=64), sa.ForeignKey("investment_item.id")),
        sa.Column(
            "watchlist_id", sa.String(length=64), sa.ForeignKey("investment_watchlist.id")
        ),
        sa.Column("thesis_id", sa.String(length=64), sa.ForeignKey("investment_thesis.id")),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("required_evidence", JsonType, server_default="[]"),
        sa.Column("verification_status", sa.String(length=32), server_default="pending"),
        sa.Column("verification_summary", sa.Text()),
        sa.Column("evidence_doc_ids", JsonType, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "idx_investment_claim_status", "investment_claim", ["workspace_id", "verification_status"]
    )

    op.create_table(
        "macro_event",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "workspace_id", sa.String(length=64), sa.ForeignKey("workspace.id"), nullable=False
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("source_name", sa.String(length=255)),
        sa.Column("source_url", sa.Text()),
        sa.Column("importance", sa.String(length=32), server_default="medium"),
        sa.Column("impact_horizon", sa.String(length=32), server_default="mid"),
        sa.Column("event_at", sa.DateTime(timezone=True)),
        sa.Column("value", sa.String(length=128)),
        sa.Column("unit", sa.String(length=64)),
        sa.Column("raw_payload", JsonType, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_macro_event_workspace", "macro_event", ["workspace_id", "event_at"])


def downgrade() -> None:
    op.drop_index("idx_macro_event_workspace", table_name="macro_event")
    op.drop_table("macro_event")
    op.drop_index("idx_investment_claim_status", table_name="investment_claim")
    op.drop_table("investment_claim")
    op.drop_index("idx_investment_thesis_watchlist", table_name="investment_thesis")
    op.drop_table("investment_thesis")
    op.drop_index("idx_investment_item_published", table_name="investment_item")
    op.drop_index("idx_investment_item_workspace_layer_status", table_name="investment_item")
    op.drop_table("investment_item")
    op.drop_index("idx_investment_source_due", table_name="investment_source")
    op.drop_table("investment_source")
    op.drop_table("investment_watchlist")

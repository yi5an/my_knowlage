"""information edge system

Revision ID: 202607150005
Revises: 202607150004
Create Date: 2026-07-15
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "202607150005"
down_revision: str | None = "202607150004"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "investment_theme",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("theme_type", sa.String(32), server_default="custom", nullable=False),
        sa.Column("keywords", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("entities", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("tickers", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("priority", sa.String(32), server_default="medium", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "idx_investment_theme_workspace",
        "investment_theme",
        ["workspace_id", "enabled"],
    )

    op.create_table(
        "investment_theme_source",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("theme_id", sa.String(64), sa.ForeignKey("investment_theme.id"), nullable=False),
        sa.Column(
            "source_id",
            sa.String(64),
            sa.ForeignKey("investment_source.id"),
            nullable=False,
        ),
        sa.Column("source_layer", sa.String(32), nullable=False),
        sa.Column("priority", sa.Integer(), server_default="50", nullable=False),
        sa.Column("collector_type", sa.String(64)),
        sa.Column("coverage_notes", sa.Text()),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("theme_id", "source_id", name="uq_investment_theme_source"),
    )
    op.create_index(
        "idx_investment_theme_source_theme",
        "investment_theme_source",
        ["workspace_id", "theme_id"],
    )

    op.create_table(
        "investment_person_source",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("theme_ids", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("handle", sa.String(128), nullable=False),
        sa.Column("display_name", sa.String(255)),
        sa.Column("role_type", sa.String(64), server_default="other", nullable=False),
        sa.Column("credibility", sa.Float(), server_default="0.5", nullable=False),
        sa.Column("noise_level", sa.Float(), server_default="0.5", nullable=False),
        sa.Column("known_bias", sa.Text()),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "idx_investment_person_source_platform",
        "investment_person_source",
        ["workspace_id", "platform", "handle"],
    )

    op.add_column("investment_item", sa.Column("theme_id", sa.String(64)))
    op.create_foreign_key(
        "fk_investment_item_theme_id",
        "investment_item",
        "investment_theme",
        ["theme_id"],
        ["id"],
    )
    op.add_column(
        "investment_item",
        sa.Column(
            "source_layer",
            sa.String(32),
            server_default="news_confirmation",
            nullable=False,
        ),
    )
    op.add_column("investment_item", sa.Column("collected_at", sa.DateTime(timezone=True)))
    op.create_index(
        "idx_investment_item_theme",
        "investment_item",
        ["workspace_id", "theme_id", "published_at"],
    )

    op.add_column(
        "investment_signal",
        sa.Column("signal_stage", sa.String(32), server_default="new", nullable=False),
    )
    op.add_column(
        "investment_signal",
        sa.Column("source_layers", sa.JSON(), server_default="[]", nullable=False),
    )
    op.add_column("investment_signal", sa.Column("first_source_layer", sa.String(32)))
    op.add_column("investment_signal", sa.Column("first_source_id", sa.String(64)))
    op.add_column(
        "investment_signal",
        sa.Column("validation_state", sa.String(32), server_default="pending", nullable=False),
    )
    op.add_column(
        "investment_signal",
        sa.Column("validation_sources", sa.JSON(), server_default="[]", nullable=False),
    )
    op.add_column(
        "investment_signal",
        sa.Column("market_feedback", sa.JSON(), server_default="{}", nullable=False),
    )
    op.add_column("investment_signal", sa.Column("lead_time_hours", sa.Float()))
    op.add_column(
        "investment_signal",
        sa.Column("information_edge_score", sa.Float(), server_default="0", nullable=False),
    )
    op.add_column(
        "investment_signal",
        sa.Column("actionability", sa.String(32), server_default="weak_signal", nullable=False),
    )
    op.add_column(
        "investment_signal",
        sa.Column("score_breakdown", sa.JSON(), server_default="{}", nullable=False),
    )

    op.create_table(
        "investment_source_trace",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("theme_id", sa.String(64), sa.ForeignKey("investment_theme.id")),
        sa.Column(
            "target_item_id",
            sa.String(64),
            sa.ForeignKey("investment_item.id"),
            nullable=False,
        ),
        sa.Column("source_item_id", sa.String(64), sa.ForeignKey("investment_item.id")),
        sa.Column("trace_type", sa.String(32), server_default="same_topic", nullable=False),
        sa.Column("match_reason", sa.Text(), nullable=False),
        sa.Column("matched_fact", sa.Text()),
        sa.Column("lead_time_hours", sa.Float()),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "idx_investment_source_trace_target",
        "investment_source_trace",
        ["workspace_id", "target_item_id"],
    )
    op.create_index(
        "idx_investment_source_trace_theme",
        "investment_source_trace",
        ["workspace_id", "theme_id"],
    )

    op.create_table(
        "investment_market_feedback",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("theme_id", sa.String(64), sa.ForeignKey("investment_theme.id")),
        sa.Column("symbol", sa.String(64), nullable=False),
        sa.Column("metric_type", sa.String(64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(32)),
        sa.Column("source_name", sa.String(255)),
        sa.Column("raw_payload", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "idx_investment_market_feedback_theme",
        "investment_market_feedback",
        ["workspace_id", "theme_id", "observed_at"],
    )
    op.create_index(
        "idx_investment_market_feedback_symbol",
        "investment_market_feedback",
        ["workspace_id", "symbol", "observed_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_investment_market_feedback_symbol", table_name="investment_market_feedback")
    op.drop_index("idx_investment_market_feedback_theme", table_name="investment_market_feedback")
    op.drop_table("investment_market_feedback")
    op.drop_index("idx_investment_source_trace_theme", table_name="investment_source_trace")
    op.drop_index("idx_investment_source_trace_target", table_name="investment_source_trace")
    op.drop_table("investment_source_trace")
    for column in [
        "score_breakdown",
        "actionability",
        "information_edge_score",
        "lead_time_hours",
        "market_feedback",
        "validation_sources",
        "validation_state",
        "first_source_id",
        "first_source_layer",
        "source_layers",
        "signal_stage",
    ]:
        op.drop_column("investment_signal", column)
    op.drop_index("idx_investment_item_theme", table_name="investment_item")
    op.drop_column("investment_item", "collected_at")
    op.drop_column("investment_item", "source_layer")
    op.drop_constraint("fk_investment_item_theme_id", "investment_item", type_="foreignkey")
    op.drop_column("investment_item", "theme_id")
    op.drop_index("idx_investment_person_source_platform", table_name="investment_person_source")
    op.drop_table("investment_person_source")
    op.drop_index("idx_investment_theme_source_theme", table_name="investment_theme_source")
    op.drop_table("investment_theme_source")
    op.drop_index("idx_investment_theme_workspace", table_name="investment_theme")
    op.drop_table("investment_theme")

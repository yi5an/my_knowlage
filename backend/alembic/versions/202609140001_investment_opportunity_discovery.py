"""persist opportunity discovery, person impact, and recommendation outcomes

Revision ID: 202609140001
Revises: 202609030002
Create Date: 2026-09-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON, Text

from alembic import op

revision: str = "202609140001"
down_revision: str | None = "202609030002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JsonType = JSON().with_variant(JSONB(astext_type=Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "investment_opportunity_candidate",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("signal_id", sa.String(64), sa.ForeignKey("investment_signal.id")),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("asset_symbols", JsonType, server_default="[]", nullable=False),
        sa.Column("theme_id", sa.String(64), sa.ForeignKey("investment_theme.id")),
        sa.Column("watchlist_id", sa.String(64), sa.ForeignKey("investment_watchlist.id")),
        sa.Column("opportunity_type", sa.String(64), nullable=False),
        sa.Column("change_summary", sa.Text(), nullable=False),
        sa.Column("expected_case", sa.Text(), nullable=False),
        sa.Column("market_case", sa.Text(), nullable=False),
        sa.Column("impact_path", sa.Text(), nullable=False),
        sa.Column("catalyst", sa.Text(), nullable=False),
        sa.Column("time_window_start", sa.DateTime(timezone=True)),
        sa.Column("time_window_end", sa.DateTime(timezone=True)),
        sa.Column("risk_flags", JsonType, server_default="[]", nullable=False),
        sa.Column("invalidation_conditions", JsonType, server_default="[]", nullable=False),
        sa.Column("evidence_refs", JsonType, server_default="[]", nullable=False),
        sa.Column("status", sa.String(32), server_default="new", nullable=False),
        sa.Column("priority", sa.String(32), server_default="research", nullable=False),
        sa.Column(
            "market_reaction_state",
            sa.String(32),
            server_default="unknown",
            nullable=False,
        ),
        sa.Column("score_breakdown", JsonType, server_default="{}", nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("outcome", JsonType, server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "idx_investment_opportunity_workspace_status",
        "investment_opportunity_candidate",
        ["workspace_id", "status"],
    )
    op.create_index(
        "idx_investment_opportunity_priority",
        "investment_opportunity_candidate",
        ["workspace_id", "priority"],
    )

    op.create_table(
        "investment_person_impact_event",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column(
            "person_source_id",
            sa.String(64),
            sa.ForeignKey("investment_person_source.id"),
            nullable=False,
        ),
        sa.Column(
            "source_item_id",
            sa.String(64),
            sa.ForeignKey("investment_item.id"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("benchmark_symbol", sa.String(32), nullable=False),
        sa.Column("event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_cluster_id", sa.String(64), nullable=False),
        sa.Column("window_overlap", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("event_status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("data_quality", sa.String(32), server_default="missing", nullable=False),
        sa.Column("windows", JsonType, server_default="{}", nullable=False),
        sa.Column("concurrent_events", JsonType, server_default="[]", nullable=False),
        sa.Column("exclusion_reason", sa.Text()),
        sa.Column("confidence", sa.Float(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "idx_person_impact_person_time",
        "investment_person_impact_event",
        ["workspace_id", "person_source_id", "event_at"],
    )
    op.create_index(
        "idx_person_impact_symbol_time",
        "investment_person_impact_event",
        ["workspace_id", "symbol", "event_at"],
    )

    op.create_table(
        "investment_person_impact_profile",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column(
            "person_source_id",
            sa.String(64),
            sa.ForeignKey("investment_person_source.id"),
            nullable=False,
        ),
        sa.Column("sample_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("valid_sample_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("excluded_sample_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("positive_event_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("negative_event_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("neutral_event_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("hit_rate", sa.Float()),
        sa.Column("average_lead_time_hours", sa.Float()),
        sa.Column("average_excess_return_1d", sa.Float()),
        sa.Column("stability_score", sa.Float()),
        sa.Column(
            "uncertainty",
            sa.Text(),
            server_default=sa.text("'样本不足'"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "workspace_id",
            "person_source_id",
            name="uq_person_impact_profile",
        ),
    )

    op.create_table(
        "investment_account_recommendation",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("handle", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255)),
        sa.Column("role_type", sa.String(64), server_default="other", nullable=False),
        sa.Column("theme_ids", JsonType, server_default="[]", nullable=False),
        sa.Column("recommendation_label", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("score_breakdown", JsonType, server_default="{}", nullable=False),
        sa.Column("sample_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("evidence_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(32), server_default="new", nullable=False),
        sa.Column("source_id", sa.String(64), sa.ForeignKey("investment_source.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "idx_account_recommendation_workspace_status",
        "investment_account_recommendation",
        ["workspace_id", "status"],
    )

    op.create_table(
        "investment_recommendation_outcome",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column(
            "recommendation_id",
            sa.String(64),
            sa.ForeignKey("investment_account_recommendation.id"),
        ),
        sa.Column(
            "opportunity_id",
            sa.String(64),
            sa.ForeignKey("investment_opportunity_candidate.id"),
        ),
        sa.Column("adopted", sa.Boolean(), nullable=False),
        sa.Column("outcome_status", sa.String(64), nullable=False),
        sa.Column("outcome_note", sa.Text()),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "idx_recommendation_outcome_workspace_time",
        "investment_recommendation_outcome",
        ["workspace_id", "observed_at"],
    )

    op.create_table(
        "investment_user_context",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("markets", JsonType, server_default="[]", nullable=False),
        sa.Column("horizons", JsonType, server_default="[]", nullable=False),
        sa.Column("focus_theme_ids", JsonType, server_default="[]", nullable=False),
        sa.Column("excluded_watchlist_ids", JsonType, server_default="[]", nullable=False),
        sa.Column("min_liquidity", sa.String(32), server_default="any", nullable=False),
        sa.Column("exposure_notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", name="uq_investment_user_context_workspace"),
    )


def downgrade() -> None:
    op.drop_table("investment_user_context")
    op.drop_index(
        "idx_recommendation_outcome_workspace_time",
        table_name="investment_recommendation_outcome",
    )
    op.drop_table("investment_recommendation_outcome")
    op.drop_index(
        "idx_account_recommendation_workspace_status",
        table_name="investment_account_recommendation",
    )
    op.drop_table("investment_account_recommendation")
    op.drop_table("investment_person_impact_profile")
    op.drop_index(
        "idx_person_impact_symbol_time",
        table_name="investment_person_impact_event",
    )
    op.drop_index(
        "idx_person_impact_person_time",
        table_name="investment_person_impact_event",
    )
    op.drop_table("investment_person_impact_event")
    op.drop_index(
        "idx_investment_opportunity_priority",
        table_name="investment_opportunity_candidate",
    )
    op.drop_index(
        "idx_investment_opportunity_workspace_status",
        table_name="investment_opportunity_candidate",
    )
    op.drop_table("investment_opportunity_candidate")

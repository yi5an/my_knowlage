"""add reading companion persistence

Revision ID: 202607170002
Revises: 202607170001
Create Date: 2026-07-17
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "202607170002"
down_revision: str | None = "202607170001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "reading_analysis",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("document_id", sa.String(64), sa.ForeignKey("document.id"), nullable=False),
        sa.Column(
            "version_id",
            sa.String(64),
            sa.ForeignKey("document_version.id"),
            nullable=False,
        ),
        sa.Column("task_job_id", sa.String(64), sa.ForeignKey("task_job.id")),
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("model_name", sa.String(128)),
        sa.Column("prompt_version", sa.String(64)),
        sa.Column("error_message", sa.Text()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("document_id", "version_id", name="uq_reading_analysis_version"),
    )
    op.create_index(
        "idx_reading_analysis_workspace_status", "reading_analysis", ["workspace_id", "status"]
    )
    op.create_table(
        "reading_insight",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "analysis_id",
            sa.String(64),
            sa.ForeignKey("reading_analysis.id"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("why_it_matters", sa.Text(), nullable=False),
        sa.Column("chunk_id", sa.String(64), sa.ForeignKey("document_chunk.id"), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("evidence_text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("evidence_state", sa.String(32), server_default="insufficient", nullable=False),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("user_note", sa.Text()),
        sa.Column("theme_ids", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("macro_event_ids", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("entity_ids", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "idx_reading_insight_analysis_priority", "reading_insight", ["analysis_id", "priority"]
    )
    op.create_table(
        "reading_corroboration",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("insight_id", sa.String(64), sa.ForeignKey("reading_insight.id"), nullable=False),
        sa.Column("source_kind", sa.String(64), nullable=False),
        sa.Column("source_id", sa.String(64), nullable=False),
        sa.Column("document_id", sa.String(64), sa.ForeignKey("document.id")),
        sa.Column("chunk_id", sa.String(64), sa.ForeignKey("document_chunk.id")),
        sa.Column("stance", sa.String(32), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("source_title", sa.Text(), nullable=False),
        sa.Column("source_published_at", sa.DateTime(timezone=True)),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("retrieval_score", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_reading_corroboration_insight", "reading_corroboration", ["insight_id"])


def downgrade() -> None:
    op.drop_index("idx_reading_corroboration_insight", table_name="reading_corroboration")
    op.drop_table("reading_corroboration")
    op.drop_index("idx_reading_insight_analysis_priority", table_name="reading_insight")
    op.drop_table("reading_insight")
    op.drop_index("idx_reading_analysis_workspace_status", table_name="reading_analysis")
    op.drop_table("reading_analysis")

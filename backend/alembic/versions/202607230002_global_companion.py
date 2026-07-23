"""add global AI companion persistence

Revision ID: 202607230002
Revises: 202607230001
Create Date: 2026-07-23
"""

import sqlalchemy as sa

from alembic import op

revision = "202607230002"
down_revision = "202607230001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "companion_session",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("subject_type", sa.String(32), nullable=False),
        sa.Column("subject_id", sa.String(64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "workspace_id", "subject_type", "subject_id", name="uq_companion_session_subject"
        ),
    )
    op.create_table(
        "companion_message",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "session_id", sa.String(64), sa.ForeignKey("companion_session.id"), nullable=False
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "companion_insight",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "session_id", sa.String(64), sa.ForeignKey("companion_session.id"), nullable=False
        ),
        sa.Column("task_job_id", sa.String(64), sa.ForeignKey("task_job.id")),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("companion_insight")
    op.drop_table("companion_message")
    op.drop_table("companion_session")

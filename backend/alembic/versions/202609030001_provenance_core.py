"""add event-conclusion provenance core

Revision ID: 202609030001
Revises: 202607230002
Create Date: 2026-09-03
"""

import sqlalchemy as sa

from alembic import op

revision = "202609030001"
down_revision = "202607230002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evidence_anchor",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("document_id", sa.String(64), sa.ForeignKey("document.id")),
        sa.Column("version_id", sa.String(64), sa.ForeignKey("document_version.id")),
        sa.Column("chunk_id", sa.String(64), sa.ForeignKey("document_chunk.id")),
        sa.Column("source_item_id", sa.String(64), sa.ForeignKey("investment_item.id")),
        sa.Column("anchor_type", sa.String(32), nullable=False),
        sa.Column("locator_json", sa.JSON(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("source_uri_snapshot", sa.Text()),
        sa.Column("source_quality", sa.Float()),
        sa.Column("validation_state", sa.String(32), nullable=False, server_default="valid"),
        sa.Column("created_by_type", sa.String(32), nullable=False),
        sa.Column("created_by_id", sa.String(64)),
        sa.Column("supersedes_anchor_id", sa.String(64), sa.ForeignKey("evidence_anchor.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "idx_evidence_anchor_workspace_type", "evidence_anchor", ["workspace_id", "anchor_type"]
    )
    op.create_index(
        "idx_evidence_anchor_document", "evidence_anchor", ["document_id", "version_id"]
    )
    op.create_index("idx_evidence_anchor_source_item", "evidence_anchor", ["source_item_id"])

    op.create_table(
        "knowledge_event",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text()),
        sa.Column("subject_entity_ids", sa.JSON(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("object_entity_ids", sa.JSON(), nullable=False),
        sa.Column("occurred_from", sa.DateTime(timezone=True)),
        sa.Column("occurred_to", sa.DateTime(timezone=True)),
        sa.Column("location", sa.Text()),
        sa.Column("canonical_key", sa.String(64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("review_status", sa.String(32), nullable=False),
        sa.Column("validation_status", sa.String(32), nullable=False),
        sa.Column("origin_type", sa.String(32), nullable=False),
        sa.Column("model_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "idx_knowledge_event_workspace_time", "knowledge_event", ["workspace_id", "occurred_from"]
    )
    op.create_index(
        "idx_knowledge_event_canonical", "knowledge_event", ["workspace_id", "canonical_key"]
    )

    op.create_table(
        "conclusion",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("conclusion_type", sa.String(32), nullable=False),
        sa.Column("conclusion_subtype", sa.String(64)),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("stance", sa.String(64)),
        sa.Column("scope_json", sa.JSON(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True)),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.Column("as_of", sa.DateTime(timezone=True)),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("review_status", sa.String(32), nullable=False),
        sa.Column("validation_status", sa.String(32), nullable=False),
        sa.Column("origin_type", sa.String(32), nullable=False),
        sa.Column("model_metadata", sa.JSON(), nullable=False),
        sa.Column("source_object_type", sa.String(64)),
        sa.Column("source_object_id", sa.String(64)),
        sa.Column("version_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("supersedes_id", sa.String(64), sa.ForeignKey("conclusion.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "idx_conclusion_workspace_type", "conclusion", ["workspace_id", "conclusion_type"]
    )
    op.create_index(
        "idx_conclusion_source",
        "conclusion",
        ["workspace_id", "source_object_type", "source_object_id"],
    )

    op.create_table(
        "trace_node",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("layer", sa.String(32), nullable=False),
        sa.Column("node_type", sa.String(64), nullable=False),
        sa.Column("backing_type", sa.String(64), nullable=False),
        sa.Column("backing_id", sa.String(64), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True)),
        sa.Column("confidence", sa.Float()),
        sa.Column("display_status", sa.String(32), nullable=False),
        sa.Column("properties_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "workspace_id", "backing_type", "backing_id", name="uq_trace_node_backing"
        ),
        sa.UniqueConstraint("id", "workspace_id", name="uq_trace_node_id_workspace"),
    )
    op.create_index(
        "idx_trace_node_workspace_layer", "trace_node", ["workspace_id", "layer"]
    )

    op.create_table(
        "trace_edge",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("source_node_id", sa.String(64), sa.ForeignKey("trace_node.id"), nullable=False),
        sa.Column("target_node_id", sa.String(64), sa.ForeignKey("trace_node.id"), nullable=False),
        sa.Column("relation_type", sa.String(32), nullable=False),
        sa.Column("rationale", sa.Text()),
        sa.Column("confidence", sa.Float()),
        sa.Column("review_status", sa.String(32), nullable=False),
        sa.Column("validation_status", sa.String(32), nullable=False),
        sa.Column("origin_type", sa.String(32), nullable=False),
        sa.Column("model_metadata", sa.JSON(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("supersedes_id", sa.String(64), sa.ForeignKey("trace_edge.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["source_node_id", "workspace_id"],
            ["trace_node.id", "trace_node.workspace_id"],
            name="fk_trace_edge_source_workspace",
        ),
        sa.ForeignKeyConstraint(
            ["target_node_id", "workspace_id"],
            ["trace_node.id", "trace_node.workspace_id"],
            name="fk_trace_edge_target_workspace",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "source_node_id",
            "target_node_id",
            "relation_type",
            "version_no",
            name="uq_trace_edge_version",
        ),
    )
    op.create_index(
        "idx_trace_edge_workspace_source", "trace_edge", ["workspace_id", "source_node_id"]
    )
    op.create_index(
        "idx_trace_edge_workspace_target", "trace_edge", ["workspace_id", "target_node_id"]
    )

    op.create_table(
        "trace_edge_evidence",
        sa.Column("edge_id", sa.String(64), sa.ForeignKey("trace_edge.id"), primary_key=True),
        sa.Column(
            "evidence_anchor_id",
            sa.String(64),
            sa.ForeignKey("evidence_anchor.id"),
            primary_key=True,
        ),
    )
    op.create_table(
        "trace_edge_review",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("edge_id", sa.String(64), sa.ForeignKey("trace_edge.id"), nullable=False),
        sa.Column("workspace_id", sa.String(64), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("reviewer_id", sa.String(64), nullable=False),
        sa.Column("previous_status", sa.String(32), nullable=False),
        sa.Column("new_status", sa.String(32), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "idx_trace_edge_review_edge", "trace_edge_review", ["edge_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("idx_trace_edge_review_edge", table_name="trace_edge_review")
    op.drop_table("trace_edge_review")
    op.drop_table("trace_edge_evidence")
    op.drop_index("idx_trace_edge_workspace_target", table_name="trace_edge")
    op.drop_index("idx_trace_edge_workspace_source", table_name="trace_edge")
    op.drop_table("trace_edge")
    op.drop_index("idx_trace_node_workspace_layer", table_name="trace_node")
    op.drop_table("trace_node")
    op.drop_index("idx_conclusion_source", table_name="conclusion")
    op.drop_index("idx_conclusion_workspace_type", table_name="conclusion")
    op.drop_table("conclusion")
    op.drop_index("idx_knowledge_event_canonical", table_name="knowledge_event")
    op.drop_index("idx_knowledge_event_workspace_time", table_name="knowledge_event")
    op.drop_table("knowledge_event")
    op.drop_index("idx_evidence_anchor_source_item", table_name="evidence_anchor")
    op.drop_index("idx_evidence_anchor_document", table_name="evidence_anchor")
    op.drop_index("idx_evidence_anchor_workspace_type", table_name="evidence_anchor")
    op.drop_table("evidence_anchor")

"""initial database models

Revision ID: 202605150001
Revises:
Create Date: 2026-05-15 00:01:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "202605150001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

json_obj = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")
json_arr = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def timestamp(timezone: bool = True) -> sa.DateTime:
    return sa.DateTime(timezone=timezone)


def upgrade() -> None:
    op.create_table(
        "workspace",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("storage_mode", sa.String(32), server_default="local"),
        sa.Column("created_at", timestamp(), server_default=sa.func.now()),
        sa.Column("updated_at", timestamp(), server_default=sa.func.now()),
    )
    op.create_table(
        "user_profile",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("username", sa.String(128)),
        sa.Column("display_name", sa.String(128)),
        sa.Column("email", sa.String(255)),
        sa.Column("role", sa.String(64), server_default="owner"),
        sa.Column("created_at", timestamp(), server_default=sa.func.now()),
    )
    op.create_table(
        "category",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), nullable=False),
        sa.Column("parent_id", sa.String(64)),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0"),
        sa.Column("created_at", timestamp(), server_default=sa.func.now()),
        sa.Column("updated_at", timestamp(), server_default=sa.func.now()),
        sa.CheckConstraint("level BETWEEN 1 AND 3", name="ck_category_level"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"]),
        sa.ForeignKeyConstraint(["parent_id"], ["category.id"]),
    )
    op.create_index("idx_category_workspace_parent", "category", ["workspace_id", "parent_id"])
    op.create_table(
        "tag",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("color", sa.String(32)),
        sa.Column("created_at", timestamp(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"]),
        sa.UniqueConstraint("workspace_id", "name", name="uq_tag_workspace_name"),
    )
    op.create_table(
        "document_file",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), nullable=False),
        sa.Column("original_name", sa.Text(), nullable=False),
        sa.Column("storage_backend", sa.String(32), server_default="local"),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(128)),
        sa.Column("file_size", sa.BigInteger()),
        sa.Column("sha256", sa.String(128)),
        sa.Column("created_at", timestamp(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"]),
    )
    op.create_index(
        "idx_document_file_sha",
        "document_file",
        ["workspace_id", "sha256"],
        unique=True,
    )
    op.create_table(
        "document",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("source_uri", sa.Text()),
        sa.Column("file_id", sa.String(64)),
        sa.Column("category_id", sa.String(64)),
        sa.Column("content_type", sa.String(128)),
        sa.Column("language", sa.String(32)),
        sa.Column("summary", sa.Text()),
        sa.Column("ai_summary", sa.Text()),
        sa.Column("status", sa.String(32), server_default="created"),
        sa.Column("parse_status", sa.String(32), server_default="pending"),
        sa.Column("index_status", sa.String(32), server_default="pending"),
        sa.Column("entity_status", sa.String(32), server_default="pending"),
        sa.Column("relation_status", sa.String(32), server_default="pending"),
        sa.Column("content_hash", sa.String(128)),
        sa.Column("sensitive_level", sa.String(32), server_default="normal"),
        sa.Column("metadata", json_obj, server_default=sa.text("'{}'")),
        sa.Column("created_at", timestamp(), server_default=sa.func.now()),
        sa.Column("updated_at", timestamp(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"]),
        sa.ForeignKeyConstraint(["file_id"], ["document_file.id"]),
        sa.ForeignKeyConstraint(["category_id"], ["category.id"]),
    )
    op.create_index("idx_document_workspace", "document", ["workspace_id"])
    op.create_index("idx_document_category", "document", ["category_id"])
    op.create_index("idx_document_status", "document", ["status", "parse_status"])
    op.create_table(
        "document_tag",
        sa.Column("doc_id", sa.String(64), nullable=False),
        sa.Column("tag_id", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["doc_id"], ["document.id"]),
        sa.ForeignKeyConstraint(["tag_id"], ["tag.id"]),
        sa.PrimaryKeyConstraint("doc_id", "tag_id"),
    )
    op.create_table(
        "document_version",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("doc_id", sa.String(64), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text()),
        sa.Column("content_md", sa.Text(), nullable=False),
        sa.Column("content_text", sa.Text()),
        sa.Column("change_summary", sa.Text()),
        sa.Column("content_hash", sa.String(128)),
        sa.Column("created_by", sa.String(64)),
        sa.Column("created_at", timestamp(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["doc_id"], ["document.id"]),
        sa.UniqueConstraint("doc_id", "version_no", name="uq_document_version_doc_version"),
    )
    op.create_index("idx_document_version_doc", "document_version", ["doc_id", "version_no"])
    op.create_table(
        "document_chunk",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("doc_id", sa.String(64), nullable=False),
        sa.Column("version_id", sa.String(64), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("heading", sa.Text()),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(128)),
        sa.Column("page_no", sa.Integer()),
        sa.Column("start_offset", sa.Integer()),
        sa.Column("end_offset", sa.Integer()),
        sa.Column("token_count", sa.Integer()),
        sa.Column("vector_id", sa.String(128)),
        sa.Column("metadata", json_obj, server_default=sa.text("'{}'")),
        sa.Column("created_at", timestamp(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["doc_id"], ["document.id"]),
        sa.ForeignKeyConstraint(["version_id"], ["document_version.id"]),
        sa.UniqueConstraint("version_id", "chunk_index", name="uq_document_chunk_version_index"),
    )
    op.create_index("idx_chunk_doc", "document_chunk", ["doc_id"])
    op.create_index("idx_chunk_version", "document_chunk", ["version_id"])
    op.create_table(
        "annotation",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), nullable=False),
        sa.Column("doc_id", sa.String(64), nullable=False),
        sa.Column("version_id", sa.String(64)),
        sa.Column("chunk_id", sa.String(64)),
        sa.Column("annotation_type", sa.String(32), nullable=False),
        sa.Column("selected_text", sa.Text()),
        sa.Column("note", sa.Text()),
        sa.Column("color", sa.String(32)),
        sa.Column("start_offset", sa.Integer()),
        sa.Column("end_offset", sa.Integer()),
        sa.Column("page_no", sa.Integer()),
        sa.Column("metadata", json_obj, server_default=sa.text("'{}'")),
        sa.Column("created_by", sa.String(64)),
        sa.Column("created_at", timestamp(), server_default=sa.func.now()),
        sa.Column("updated_at", timestamp(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"]),
        sa.ForeignKeyConstraint(["doc_id"], ["document.id"]),
        sa.ForeignKeyConstraint(["version_id"], ["document_version.id"]),
        sa.ForeignKeyConstraint(["chunk_id"], ["document_chunk.id"]),
    )
    op.create_index("idx_annotation_doc", "annotation", ["doc_id"])
    op.create_index("idx_annotation_type", "annotation", ["annotation_type"])
    op.create_table(
        "entity_type",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("domain", sa.String(128)),
        sa.Column("description", sa.Text()),
        sa.Column("examples", json_arr, server_default=sa.text("'[]'")),
        sa.Column("aliases", json_arr, server_default=sa.text("'[]'")),
        sa.Column("rules", json_arr, server_default=sa.text("'[]'")),
        sa.Column("source", sa.String(32), server_default="system"),
        sa.Column("status", sa.String(32), server_default="active"),
        sa.Column("confidence", sa.Float()),
        sa.Column("created_at", timestamp(), server_default=sa.func.now()),
        sa.Column("updated_at", timestamp(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"]),
        sa.UniqueConstraint("workspace_id", "name", name="uq_entity_type_workspace_name"),
    )
    op.create_table(
        "entity",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), nullable=False),
        sa.Column("entity_type_id", sa.String(64), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=False),
        sa.Column("aliases", json_arr, server_default=sa.text("'[]'")),
        sa.Column("description", sa.Text()),
        sa.Column("properties", json_obj, server_default=sa.text("'{}'")),
        sa.Column("confidence", sa.Float(), server_default="0"),
        sa.Column("verified", sa.Boolean(), server_default=sa.false()),
        sa.Column("created_at", timestamp(), server_default=sa.func.now()),
        sa.Column("updated_at", timestamp(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"]),
        sa.ForeignKeyConstraint(["entity_type_id"], ["entity_type.id"]),
    )
    op.create_index("idx_entity_workspace_type", "entity", ["workspace_id", "entity_type_id"])
    op.create_index("idx_entity_normalized_name", "entity", ["workspace_id", "normalized_name"])
    op.create_table(
        "entity_mention",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("doc_id", sa.String(64), nullable=False),
        sa.Column("chunk_id", sa.String(64)),
        sa.Column("mention_text", sa.Text(), nullable=False),
        sa.Column("start_offset", sa.Integer()),
        sa.Column("end_offset", sa.Integer()),
        sa.Column("page_no", sa.Integer()),
        sa.Column("confidence", sa.Float(), server_default="0"),
        sa.Column("extractor", sa.String(64)),
        sa.Column("created_at", timestamp(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"]),
        sa.ForeignKeyConstraint(["entity_id"], ["entity.id"]),
        sa.ForeignKeyConstraint(["doc_id"], ["document.id"]),
        sa.ForeignKeyConstraint(["chunk_id"], ["document_chunk.id"]),
    )
    op.create_index("idx_entity_mention_entity", "entity_mention", ["entity_id"])
    op.create_index("idx_entity_mention_doc", "entity_mention", ["doc_id"])
    op.create_table(
        "relation_type",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("domain", sa.String(128)),
        sa.Column("source_entity_types", json_arr, server_default=sa.text("'[]'")),
        sa.Column("target_entity_types", json_arr, server_default=sa.text("'[]'")),
        sa.Column("examples", json_arr, server_default=sa.text("'[]'")),
        sa.Column("created_at", timestamp(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"]),
        sa.UniqueConstraint("workspace_id", "name", name="uq_relation_type_workspace_name"),
    )
    op.create_table(
        "entity_relation",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), nullable=False),
        sa.Column("source_entity_id", sa.String(64), nullable=False),
        sa.Column("target_entity_id", sa.String(64), nullable=False),
        sa.Column("relation_type_id", sa.String(64), nullable=False),
        sa.Column("evidence_doc_id", sa.String(64)),
        sa.Column("evidence_chunk_id", sa.String(64)),
        sa.Column("evidence_text", sa.Text()),
        sa.Column("confidence", sa.Float(), server_default="0"),
        sa.Column("verified", sa.Boolean(), server_default=sa.false()),
        sa.Column("properties", json_obj, server_default=sa.text("'{}'")),
        sa.Column("created_at", timestamp(), server_default=sa.func.now()),
        sa.Column("updated_at", timestamp(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"]),
        sa.ForeignKeyConstraint(["source_entity_id"], ["entity.id"]),
        sa.ForeignKeyConstraint(["target_entity_id"], ["entity.id"]),
        sa.ForeignKeyConstraint(["relation_type_id"], ["relation_type.id"]),
        sa.ForeignKeyConstraint(["evidence_doc_id"], ["document.id"]),
        sa.ForeignKeyConstraint(["evidence_chunk_id"], ["document_chunk.id"]),
    )
    op.create_index("idx_relation_source", "entity_relation", ["source_entity_id"])
    op.create_index("idx_relation_target", "entity_relation", ["target_entity_id"])
    op.create_index("idx_relation_type", "entity_relation", ["relation_type_id"])
    op.create_index("idx_relation_workspace", "entity_relation", ["workspace_id"])
    op.create_table(
        "stock_profile",
        sa.Column("entity_id", sa.String(64), primary_key=True),
        sa.Column("ticker", sa.String(32), nullable=False),
        sa.Column("exchange", sa.String(64)),
        sa.Column("currency", sa.String(16)),
        sa.Column("company_name", sa.Text()),
        sa.Column("company_short_name", sa.Text()),
        sa.Column("country", sa.String(64)),
        sa.Column("industry", sa.String(128)),
        sa.Column("sector", sa.String(128)),
        sa.Column("listing_status", sa.String(32)),
        sa.Column("metadata", json_obj, server_default=sa.text("'{}'")),
        sa.Column("updated_at", timestamp(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["entity_id"], ["entity.id"]),
    )
    op.create_index("idx_stock_ticker", "stock_profile", ["ticker", "exchange"])
    op.create_index("idx_stock_industry", "stock_profile", ["industry", "sector"])
    op.create_table(
        "industry_chain",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("domain", sa.String(128)),
        sa.Column("metadata", json_obj, server_default=sa.text("'{}'")),
        sa.Column("created_at", timestamp(), server_default=sa.func.now()),
        sa.Column("updated_at", timestamp(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"]),
    )
    op.create_table(
        "industry_chain_node",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("chain_id", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(64)),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("stage", sa.String(64), nullable=False),
        sa.Column("node_type", sa.String(64)),
        sa.Column("description", sa.Text()),
        sa.Column("sort_order", sa.Integer(), server_default="0"),
        sa.Column("metadata", json_obj, server_default=sa.text("'{}'")),
        sa.ForeignKeyConstraint(["chain_id"], ["industry_chain.id"]),
        sa.ForeignKeyConstraint(["entity_id"], ["entity.id"]),
    )
    op.create_index("idx_chain_node_chain_stage", "industry_chain_node", ["chain_id", "stage"])
    op.create_table(
        "industry_chain_edge",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("chain_id", sa.String(64), nullable=False),
        sa.Column("source_node_id", sa.String(64), nullable=False),
        sa.Column("target_node_id", sa.String(64), nullable=False),
        sa.Column("relation_type", sa.String(64)),
        sa.Column("description", sa.Text()),
        sa.Column("evidence_doc_id", sa.String(64)),
        sa.Column("confidence", sa.Float(), server_default="0"),
        sa.Column("metadata", json_obj, server_default=sa.text("'{}'")),
        sa.ForeignKeyConstraint(["chain_id"], ["industry_chain.id"]),
        sa.ForeignKeyConstraint(["source_node_id"], ["industry_chain_node.id"]),
        sa.ForeignKeyConstraint(["target_node_id"], ["industry_chain_node.id"]),
        sa.ForeignKeyConstraint(["evidence_doc_id"], ["document.id"]),
    )
    op.create_table(
        "task_job",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), nullable=False),
        sa.Column("job_type", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(64)),
        sa.Column("target_id", sa.String(64)),
        sa.Column("status", sa.String(32), server_default="pending"),
        sa.Column("progress", sa.Integer(), server_default="0"),
        sa.Column("input", json_obj, server_default=sa.text("'{}'")),
        sa.Column("output", json_obj, server_default=sa.text("'{}'")),
        sa.Column("error_message", sa.Text()),
        sa.Column("started_at", timestamp()),
        sa.Column("finished_at", timestamp()),
        sa.Column("created_at", timestamp(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"]),
    )
    op.create_index("idx_task_status", "task_job", ["status", "job_type"])
    op.create_index("idx_task_target", "task_job", ["target_type", "target_id"])
    op.create_table(
        "research_task",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), server_default="pending"),
        sa.Column("plan", json_obj, server_default=sa.text("'{}'")),
        sa.Column("report_doc_id", sa.String(64)),
        sa.Column("metadata", json_obj, server_default=sa.text("'{}'")),
        sa.Column("created_at", timestamp(), server_default=sa.func.now()),
        sa.Column("updated_at", timestamp(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"]),
        sa.ForeignKeyConstraint(["report_doc_id"], ["document.id"]),
    )
    op.create_table(
        "research_source",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("research_task_id", sa.String(64), nullable=False),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("title", sa.Text()),
        sa.Column("url", sa.Text()),
        sa.Column("doc_id", sa.String(64)),
        sa.Column("snippet", sa.Text()),
        sa.Column("credibility_score", sa.Float()),
        sa.Column("used_in_report", sa.Boolean(), server_default=sa.false()),
        sa.Column("metadata", json_obj, server_default=sa.text("'{}'")),
        sa.Column("created_at", timestamp(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["research_task_id"], ["research_task.id"]),
        sa.ForeignKeyConstraint(["doc_id"], ["document.id"]),
    )
    op.create_table(
        "model_provider",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("provider_type", sa.String(64), nullable=False),
        sa.Column("base_url", sa.Text()),
        sa.Column("api_key_ref", sa.Text()),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true()),
        sa.Column("metadata", json_obj, server_default=sa.text("'{}'")),
        sa.Column("created_at", timestamp(), server_default=sa.func.now()),
    )
    op.create_table(
        "model_config",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("provider_id", sa.String(64), nullable=False),
        sa.Column("model_name", sa.String(128), nullable=False),
        sa.Column("model_type", sa.String(64), nullable=False),
        sa.Column("context_window", sa.Integer()),
        sa.Column("max_output_tokens", sa.Integer()),
        sa.Column("supports_vision", sa.Boolean(), server_default=sa.false()),
        sa.Column("supports_tools", sa.Boolean(), server_default=sa.false()),
        sa.Column("supports_json_schema", sa.Boolean(), server_default=sa.false()),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true()),
        sa.Column("metadata", json_obj, server_default=sa.text("'{}'")),
        sa.Column("created_at", timestamp(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["provider_id"], ["model_provider.id"]),
    )

    if op.get_bind().dialect.name == "postgresql":
        op.create_index(
            "idx_document_metadata_gin",
            "document",
            ["metadata"],
            postgresql_using="gin",
        )
        op.create_index(
            "idx_chunk_metadata_gin",
            "document_chunk",
            ["metadata"],
            postgresql_using="gin",
        )
        op.create_index(
            "idx_entity_properties_gin",
            "entity",
            ["properties"],
            postgresql_using="gin",
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.drop_index("idx_entity_properties_gin", table_name="entity")
        op.drop_index("idx_chunk_metadata_gin", table_name="document_chunk")
        op.drop_index("idx_document_metadata_gin", table_name="document")

    for table_name in (
        "model_config",
        "model_provider",
        "research_source",
        "research_task",
        "task_job",
        "industry_chain_edge",
        "industry_chain_node",
        "industry_chain",
        "stock_profile",
        "entity_relation",
        "relation_type",
        "entity_mention",
        "entity",
        "entity_type",
        "annotation",
        "document_chunk",
        "document_version",
        "document_tag",
        "document",
        "document_file",
        "tag",
        "category",
        "user_profile",
        "workspace",
    ):
        op.drop_table(table_name)

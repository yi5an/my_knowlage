from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.infrastructure.database import Base

JsonObject = dict[str, Any]
JsonArray = list[Any]
JsonValue = JsonObject | JsonArray
JsonType = JSON().with_variant(JSONB(astext_type=Text()), "postgresql")


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UpdatedTimestampMixin(TimestampMixin):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class Workspace(UpdatedTimestampMixin, Base):
    __tablename__ = "workspace"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text())
    storage_mode: Mapped[str] = mapped_column(String(32), default="local", server_default="local")


class UserProfile(TimestampMixin, Base):
    __tablename__ = "user_profile"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str | None] = mapped_column(String(128))
    display_name: Mapped[str | None] = mapped_column(String(128))
    email: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(64), default="owner", server_default="owner")


class Category(UpdatedTimestampMixin, Base):
    __tablename__ = "category"
    __table_args__ = (
        CheckConstraint("level BETWEEN 1 AND 3", name="ck_category_level"),
        Index("idx_category_workspace_parent", "workspace_id", "parent_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("category.id"))
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    path: Mapped[str] = mapped_column(Text(), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class Tag(TimestampMixin, Base):
    __tablename__ = "tag"
    __table_args__ = (UniqueConstraint("workspace_id", "name", name="uq_tag_workspace_name"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    color: Mapped[str | None] = mapped_column(String(32))


class DocumentFile(TimestampMixin, Base):
    __tablename__ = "document_file"
    __table_args__ = (
        Index("idx_document_file_sha", "workspace_id", "sha256", unique=True),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), nullable=False)
    original_name: Mapped[str] = mapped_column(Text(), nullable=False)
    storage_backend: Mapped[str] = mapped_column(
        String(32),
        default="local",
        server_default="local",
    )
    storage_path: Mapped[str] = mapped_column(Text(), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(128))
    file_size: Mapped[int | None] = mapped_column(BigInteger())
    sha256: Mapped[str | None] = mapped_column(String(128))


class Document(UpdatedTimestampMixin, Base):
    __tablename__ = "document"
    __table_args__ = (
        Index("idx_document_workspace", "workspace_id"),
        Index("idx_document_category", "category_id"),
        Index("idx_document_status", "status", "parse_status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), nullable=False)
    title: Mapped[str] = mapped_column(Text(), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_uri: Mapped[str | None] = mapped_column(Text())
    file_id: Mapped[str | None] = mapped_column(ForeignKey("document_file.id"))
    category_id: Mapped[str | None] = mapped_column(ForeignKey("category.id"))
    content_type: Mapped[str | None] = mapped_column(String(128))
    language: Mapped[str | None] = mapped_column(String(32))
    summary: Mapped[str | None] = mapped_column(Text())
    ai_summary: Mapped[str | None] = mapped_column(Text())
    status: Mapped[str] = mapped_column(String(32), default="created", server_default="created")
    parse_status: Mapped[str] = mapped_column(
        String(32),
        default="pending",
        server_default="pending",
    )
    index_status: Mapped[str] = mapped_column(
        String(32),
        default="pending",
        server_default="pending",
    )
    entity_status: Mapped[str] = mapped_column(
        String(32),
        default="pending",
        server_default="pending",
    )
    relation_status: Mapped[str] = mapped_column(
        String(32),
        default="pending",
        server_default="pending",
    )
    content_hash: Mapped[str | None] = mapped_column(String(128))
    sensitive_level: Mapped[str] = mapped_column(
        String(32),
        default="normal",
        server_default="normal",
    )
    metadata_: Mapped[JsonObject] = mapped_column("metadata", JsonType, default=dict)
    # YouTube source extension (nullable; only set for source_type == "youtube")
    video_id: Mapped[str | None] = mapped_column(ForeignKey("video.id"))
    summary_json: Mapped[JsonObject | None] = mapped_column("summary_json", JsonType, default=None)
    transcript_lang: Mapped[str | None] = mapped_column(String(32))
    mindmap_data: Mapped[JsonObject | None] = mapped_column("mindmap_data", JsonType, default=None)

    # Unread indicator: a summary is "unread" (shows a star/badge) until the
    # user opens its card. Set to True when a summary is first produced, and
    # flipped to False by the mark-read endpoint when the card page loads.
    is_unread: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1"
    )


class DocumentTag(Base):
    __tablename__ = "document_tag"

    doc_id: Mapped[str] = mapped_column(ForeignKey("document.id"), primary_key=True)
    tag_id: Mapped[str] = mapped_column(ForeignKey("tag.id"), primary_key=True)


class DocumentVersion(TimestampMixin, Base):
    __tablename__ = "document_version"
    __table_args__ = (
        UniqueConstraint("doc_id", "version_no", name="uq_document_version_doc_version"),
        Index("idx_document_version_doc", "doc_id", "version_no"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    doc_id: Mapped[str] = mapped_column(ForeignKey("document.id"), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(Text())
    content_md: Mapped[str] = mapped_column(Text(), nullable=False)
    content_text: Mapped[str | None] = mapped_column(Text())
    change_summary: Mapped[str | None] = mapped_column(Text())
    content_hash: Mapped[str | None] = mapped_column(String(128))
    created_by: Mapped[str | None] = mapped_column(String(64))


class DocumentChunk(TimestampMixin, Base):
    __tablename__ = "document_chunk"
    __table_args__ = (
        UniqueConstraint("version_id", "chunk_index", name="uq_document_chunk_version_index"),
        Index("idx_chunk_doc", "doc_id"),
        Index("idx_chunk_version", "version_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    doc_id: Mapped[str] = mapped_column(ForeignKey("document.id"), nullable=False)
    version_id: Mapped[str] = mapped_column(ForeignKey("document_version.id"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    heading: Mapped[str | None] = mapped_column(Text())
    content: Mapped[str] = mapped_column(Text(), nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(128))
    page_no: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    token_count: Mapped[int | None] = mapped_column(Integer)
    vector_id: Mapped[str | None] = mapped_column(String(128))
    metadata_: Mapped[JsonObject] = mapped_column("metadata", JsonType, default=dict)


class Annotation(UpdatedTimestampMixin, Base):
    __tablename__ = "annotation"
    __table_args__ = (
        Index("idx_annotation_doc", "doc_id"),
        Index("idx_annotation_type", "annotation_type"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), nullable=False)
    doc_id: Mapped[str] = mapped_column(ForeignKey("document.id"), nullable=False)
    version_id: Mapped[str | None] = mapped_column(ForeignKey("document_version.id"))
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("document_chunk.id"))
    annotation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    selected_text: Mapped[str | None] = mapped_column(Text())
    note: Mapped[str | None] = mapped_column(Text())
    color: Mapped[str | None] = mapped_column(String(32))
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    page_no: Mapped[int | None] = mapped_column(Integer)
    metadata_: Mapped[JsonObject] = mapped_column("metadata", JsonType, default=dict)
    created_by: Mapped[str | None] = mapped_column(String(64))


class EntityType(UpdatedTimestampMixin, Base):
    __tablename__ = "entity_type"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_entity_type_workspace_name"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text())
    examples: Mapped[JsonArray] = mapped_column(JsonType, default=list)
    aliases: Mapped[JsonArray] = mapped_column(JsonType, default=list)
    rules: Mapped[JsonArray] = mapped_column(JsonType, default=list)
    source: Mapped[str] = mapped_column(String(32), default="system", server_default="system")
    status: Mapped[str] = mapped_column(String(32), default="active", server_default="active")
    confidence: Mapped[float | None] = mapped_column(Float())


class Entity(UpdatedTimestampMixin, Base):
    __tablename__ = "entity"
    __table_args__ = (
        Index("idx_entity_workspace_type", "workspace_id", "entity_type_id"),
        Index("idx_entity_normalized_name", "workspace_id", "normalized_name"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), nullable=False)
    entity_type_id: Mapped[str] = mapped_column(ForeignKey("entity_type.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text(), nullable=False)
    normalized_name: Mapped[str] = mapped_column(Text(), nullable=False)
    aliases: Mapped[JsonArray] = mapped_column(JsonType, default=list)
    description: Mapped[str | None] = mapped_column(Text())
    properties: Mapped[JsonObject] = mapped_column(JsonType, default=dict)
    confidence: Mapped[float] = mapped_column(Float(), default=0, server_default="0")
    verified: Mapped[bool] = mapped_column(Boolean(), default=False, server_default="false")


class EntityMention(TimestampMixin, Base):
    __tablename__ = "entity_mention"
    __table_args__ = (
        Index("idx_entity_mention_entity", "entity_id"),
        Index("idx_entity_mention_doc", "doc_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), nullable=False)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entity.id"), nullable=False)
    doc_id: Mapped[str] = mapped_column(ForeignKey("document.id"), nullable=False)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("document_chunk.id"))
    mention_text: Mapped[str] = mapped_column(Text(), nullable=False)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    page_no: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[float] = mapped_column(Float(), default=0, server_default="0")
    extractor: Mapped[str | None] = mapped_column(String(64))


class RelationType(TimestampMixin, Base):
    __tablename__ = "relation_type"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_relation_type_workspace_name"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text())
    domain: Mapped[str | None] = mapped_column(String(128))
    source_entity_types: Mapped[JsonArray] = mapped_column(JsonType, default=list)
    target_entity_types: Mapped[JsonArray] = mapped_column(JsonType, default=list)
    examples: Mapped[JsonArray] = mapped_column(JsonType, default=list)


class EntityRelation(UpdatedTimestampMixin, Base):
    __tablename__ = "entity_relation"
    __table_args__ = (
        Index("idx_relation_source", "source_entity_id"),
        Index("idx_relation_target", "target_entity_id"),
        Index("idx_relation_type", "relation_type_id"),
        Index("idx_relation_workspace", "workspace_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), nullable=False)
    source_entity_id: Mapped[str] = mapped_column(ForeignKey("entity.id"), nullable=False)
    target_entity_id: Mapped[str] = mapped_column(ForeignKey("entity.id"), nullable=False)
    relation_type_id: Mapped[str] = mapped_column(ForeignKey("relation_type.id"), nullable=False)
    evidence_doc_id: Mapped[str | None] = mapped_column(ForeignKey("document.id"))
    evidence_chunk_id: Mapped[str | None] = mapped_column(ForeignKey("document_chunk.id"))
    evidence_text: Mapped[str | None] = mapped_column(Text())
    confidence: Mapped[float] = mapped_column(Float(), default=0, server_default="0")
    verified: Mapped[bool] = mapped_column(Boolean(), default=False, server_default="false")
    properties: Mapped[JsonObject] = mapped_column(JsonType, default=dict)


class StockProfile(Base):
    __tablename__ = "stock_profile"
    __table_args__ = (
        Index("idx_stock_ticker", "ticker", "exchange"),
        Index("idx_stock_industry", "industry", "sector"),
    )

    entity_id: Mapped[str] = mapped_column(ForeignKey("entity.id"), primary_key=True)
    ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    exchange: Mapped[str | None] = mapped_column(String(64))
    currency: Mapped[str | None] = mapped_column(String(16))
    company_name: Mapped[str | None] = mapped_column(Text())
    company_short_name: Mapped[str | None] = mapped_column(Text())
    country: Mapped[str | None] = mapped_column(String(64))
    industry: Mapped[str | None] = mapped_column(String(128))
    sector: Mapped[str | None] = mapped_column(String(128))
    listing_status: Mapped[str | None] = mapped_column(String(32))
    metadata_: Mapped[JsonObject] = mapped_column("metadata", JsonType, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IndustryChain(UpdatedTimestampMixin, Base):
    __tablename__ = "industry_chain"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text())
    domain: Mapped[str | None] = mapped_column(String(128))
    metadata_: Mapped[JsonObject] = mapped_column("metadata", JsonType, default=dict)


class IndustryChainNode(Base):
    __tablename__ = "industry_chain_node"
    __table_args__ = (Index("idx_chain_node_chain_stage", "chain_id", "stage"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    chain_id: Mapped[str] = mapped_column(ForeignKey("industry_chain.id"), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(ForeignKey("entity.id"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    node_type: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text())
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    metadata_: Mapped[JsonObject] = mapped_column("metadata", JsonType, default=dict)


class IndustryChainEdge(Base):
    __tablename__ = "industry_chain_edge"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    chain_id: Mapped[str] = mapped_column(ForeignKey("industry_chain.id"), nullable=False)
    source_node_id: Mapped[str] = mapped_column(
        ForeignKey("industry_chain_node.id"),
        nullable=False,
    )
    target_node_id: Mapped[str] = mapped_column(
        ForeignKey("industry_chain_node.id"),
        nullable=False,
    )
    relation_type: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text())
    evidence_doc_id: Mapped[str | None] = mapped_column(ForeignKey("document.id"))
    confidence: Mapped[float] = mapped_column(Float(), default=0, server_default="0")
    metadata_: Mapped[JsonObject] = mapped_column("metadata", JsonType, default=dict)


class TaskJob(TimestampMixin, Base):
    __tablename__ = "task_job"
    __table_args__ = (
        Index("idx_task_status", "status", "job_type"),
        Index("idx_task_target", "target_type", "target_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), nullable=False)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(64))
    target_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="pending", server_default="pending")
    progress: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    input: Mapped[JsonObject] = mapped_column(JsonType, default=dict)
    output: Mapped[JsonObject] = mapped_column(JsonType, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResearchTask(UpdatedTimestampMixin, Base):
    __tablename__ = "research_task"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), nullable=False)
    title: Mapped[str] = mapped_column(Text(), nullable=False)
    question: Mapped[str] = mapped_column(Text(), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", server_default="pending")
    plan: Mapped[JsonObject] = mapped_column(JsonType, default=dict)
    report_doc_id: Mapped[str | None] = mapped_column(ForeignKey("document.id"))
    metadata_: Mapped[JsonObject] = mapped_column("metadata", JsonType, default=dict)


class ResearchSource(TimestampMixin, Base):
    __tablename__ = "research_source"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    research_task_id: Mapped[str] = mapped_column(ForeignKey("research_task.id"), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str | None] = mapped_column(Text())
    url: Mapped[str | None] = mapped_column(Text())
    doc_id: Mapped[str | None] = mapped_column(ForeignKey("document.id"))
    snippet: Mapped[str | None] = mapped_column(Text())
    credibility_score: Mapped[float | None] = mapped_column(Float())
    used_in_report: Mapped[bool] = mapped_column(Boolean(), default=False, server_default="false")
    metadata_: Mapped[JsonObject] = mapped_column("metadata", JsonType, default=dict)


class ModelProvider(TimestampMixin, Base):
    __tablename__ = "model_provider"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(64), nullable=False)
    base_url: Mapped[str | None] = mapped_column(Text())
    api_key_ref: Mapped[str | None] = mapped_column(Text())
    enabled: Mapped[bool] = mapped_column(Boolean(), default=True, server_default="true")
    metadata_: Mapped[JsonObject] = mapped_column("metadata", JsonType, default=dict)


class ModelConfig(TimestampMixin, Base):
    __tablename__ = "model_config"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider_id: Mapped[str] = mapped_column(ForeignKey("model_provider.id"), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_type: Mapped[str] = mapped_column(String(64), nullable=False)
    context_window: Mapped[int | None] = mapped_column(Integer)
    max_output_tokens: Mapped[int | None] = mapped_column(Integer)
    supports_vision: Mapped[bool] = mapped_column(Boolean(), default=False, server_default="false")
    supports_tools: Mapped[bool] = mapped_column(Boolean(), default=False, server_default="false")
    supports_json_schema: Mapped[bool] = mapped_column(
        Boolean(),
        default=False,
        server_default="false",
    )
    enabled: Mapped[bool] = mapped_column(Boolean(), default=True, server_default="true")
    metadata_: Mapped[JsonObject] = mapped_column("metadata", JsonType, default=dict)

    provider: Mapped[ModelProvider] = relationship()


# --- YouTube source extension (subscription + video metadata) ---


class Subscription(UpdatedTimestampMixin, Base):
    """A subscribed content source (e.g. a YouTube channel).

    Drives the polling scheduler. A manual single-URL summary has no subscription;
    only scheduled channel subscriptions live here.
    """

    __tablename__ = "subscription"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "platform",
            "channel_id",
            name="uq_subscription_workspace_platform_channel",
        ),
        Index("idx_subscription_enabled", "enabled", "next_poll_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), default="youtube", server_default="youtube")
    channel_id: Mapped[str] = mapped_column(String(128), nullable=False)
    channel_name: Mapped[str | None] = mapped_column(String(255))
    thumbnail_url: Mapped[str | None] = mapped_column(Text())
    poll_interval: Mapped[int] = mapped_column(Integer, default=3600, server_default="3600")
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_video_id: Mapped[str | None] = mapped_column(String(128))
    last_error: Mapped[str | None] = mapped_column(Text())
    enabled: Mapped[bool] = mapped_column(Boolean(), default=True, server_default="true")
    metadata_: Mapped[JsonObject] = mapped_column("metadata", JsonType, default=dict)


class Video(TimestampMixin, Base):
    """Metadata for a single fetched video. The transcript itself is stored as a
    Document (source_type='youtube') linked back here via document.video_id.
    """

    __tablename__ = "video"
    __table_args__ = (
        UniqueConstraint("workspace_id", "video_id", name="uq_video_workspace_video"),
        Index("idx_video_subscription", "subscription_id"),
        Index("idx_video_fetch_status", "fetch_status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), nullable=False)
    subscription_id: Mapped[str | None] = mapped_column(ForeignKey("subscription.id"))
    platform: Mapped[str] = mapped_column(String(32), default="youtube", server_default="youtube")
    video_id: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(Text(), nullable=False)
    channel_id: Mapped[str | None] = mapped_column(String(128))
    channel_name: Mapped[str | None] = mapped_column(String(255))
    duration_sec: Mapped[int | None] = mapped_column(Integer)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    thumbnail_url: Mapped[str | None] = mapped_column(Text())
    description: Mapped[str | None] = mapped_column(Text())
    chapters: Mapped[JsonArray] = mapped_column(JsonType, default=list)
    fetch_status: Mapped[str] = mapped_column(
        String(32),
        default="pending",
        server_default="pending",
    )
    error_message: Mapped[str | None] = mapped_column(Text())
    metadata_: Mapped[JsonObject] = mapped_column("metadata", JsonType, default=dict)


# ---------------------------------------------------------------------------
# Investment information system
# ---------------------------------------------------------------------------


class InvestmentWatchlist(UpdatedTimestampMixin, Base):
    """A subject under observation (stock / macro theme / company)."""

    __tablename__ = "investment_watchlist"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    watch_type: Mapped[str] = mapped_column(String(32), default="stock", server_default="stock")
    ticker: Mapped[str | None] = mapped_column(String(64))
    exchange: Mapped[str | None] = mapped_column(String(32))
    keywords: Mapped[JsonArray] = mapped_column(JsonType, default=list)
    importance: Mapped[str] = mapped_column(String(32), default="medium", server_default="medium")
    notes: Mapped[str | None] = mapped_column(Text())
    enabled: Mapped[bool] = mapped_column(Boolean(), default=True, server_default="true")


class InvestmentSource(UpdatedTimestampMixin, Base):
    """Configuration for a real data source (RSS / SEC / Fed / BLS / FRED / HKEX / CNINFO)."""

    __tablename__ = "investment_source"
    __table_args__ = (Index("idx_investment_source_due", "enabled", "next_poll_at"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str | None] = mapped_column(Text())
    config: Mapped[JsonObject] = mapped_column(JsonType, default=dict)
    default_info_layer: Mapped[str] = mapped_column(
        String(32), default="news", server_default="news"
    )
    default_watchlist_ids: Mapped[JsonArray] = mapped_column(JsonType, default=list)
    poll_interval_seconds: Mapped[int] = mapped_column(Integer, default=3600, server_default="3600")
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text())
    enabled: Mapped[bool] = mapped_column(Boolean(), default=True, server_default="true")


class InvestmentItem(UpdatedTimestampMixin, Base):
    """A single investment information entry — the main feed table.

    The ``importance`` / ``impact_direction`` / ``impact_horizon`` / ``thesis_impact``
    fields are the user-confirmed values. Auto-classification only ever writes the
    ``suggested_*`` shadow fields plus ``classification_reason``; it never overwrites
    the confirmed fields (spec §6.1 / doc §17.3).
    """

    __tablename__ = "investment_item"
    __table_args__ = (
        Index(
            "idx_investment_item_workspace_layer_status",
            "workspace_id",
            "info_layer",
            "action_status",
        ),
        UniqueConstraint("workspace_id", "dedupe_key", name="uq_investment_item_dedupe"),
        Index("idx_investment_item_published", "workspace_id", "published_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), nullable=False)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("document.id"))
    source_id: Mapped[str | None] = mapped_column(ForeignKey("investment_source.id"))
    dedupe_key: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(Text(), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text())
    source_name: Mapped[str | None] = mapped_column(String(255))
    info_layer: Mapped[str] = mapped_column(String(32), default="news", server_default="news")
    source_credibility: Mapped[str] = mapped_column(
        String(32), default="unverified", server_default="unverified"
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[str | None] = mapped_column(Text())
    # Chinese translations of title/summary (filled asynchronously by the
    # investment_translation job). Nullable: untranslated items show the
    # original-language title/summary (frontend falls back to title/summary).
    title_zh: Mapped[str | None] = mapped_column(Text())
    summary_zh: Mapped[str | None] = mapped_column(Text())
    importance: Mapped[str] = mapped_column(String(32), default="medium", server_default="medium")
    impact_direction: Mapped[str] = mapped_column(
        String(32), default="neutral", server_default="neutral"
    )
    impact_horizon: Mapped[str] = mapped_column(
        String(32), default="unknown", server_default="unknown"
    )
    thesis_impact: Mapped[str] = mapped_column(
        String(32), default="unknown", server_default="unknown"
    )
    action_status: Mapped[str] = mapped_column(
        String(32), default="pending_review", server_default="pending_review"
    )
    review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_payload: Mapped[JsonObject] = mapped_column(JsonType, default=dict)
    # Auto-classified suggestions (never overwrite the confirmed fields above).
    suggested_importance: Mapped[str | None] = mapped_column(String(32))
    suggested_impact_direction: Mapped[str | None] = mapped_column(String(32))
    suggested_impact_horizon: Mapped[str | None] = mapped_column(String(32))
    suggested_thesis_impact: Mapped[str | None] = mapped_column(String(32))
    classification_reason: Mapped[str | None] = mapped_column(Text())


class InvestmentThesis(UpdatedTimestampMixin, Base):
    """An investment hypothesis tied to a watchlist."""

    __tablename__ = "investment_thesis"
    __table_args__ = (Index("idx_investment_thesis_watchlist", "workspace_id", "watchlist_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), nullable=False)
    watchlist_id: Mapped[str | None] = mapped_column(ForeignKey("investment_watchlist.id"))
    title: Mapped[str] = mapped_column(Text(), nullable=False)
    body: Mapped[str | None] = mapped_column(Text())
    status: Mapped[str] = mapped_column(String(32), default="open", server_default="open")
    confidence: Mapped[str] = mapped_column(String(32), default="medium", server_default="medium")
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InvestmentClaim(UpdatedTimestampMixin, Base):
    """A claim/claim-to-verify, possibly sourced from an opinion-layer item."""

    __tablename__ = "investment_claim"
    __table_args__ = (
        Index("idx_investment_claim_status", "workspace_id", "verification_status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), nullable=False)
    source_item_id: Mapped[str | None] = mapped_column(ForeignKey("investment_item.id"))
    watchlist_id: Mapped[str | None] = mapped_column(ForeignKey("investment_watchlist.id"))
    thesis_id: Mapped[str | None] = mapped_column(ForeignKey("investment_thesis.id"))
    claim_text: Mapped[str] = mapped_column(Text(), nullable=False)
    required_evidence: Mapped[JsonArray] = mapped_column(JsonType, default=list)
    verification_status: Mapped[str] = mapped_column(
        String(32), default="pending", server_default="pending"
    )
    verification_summary: Mapped[str | None] = mapped_column(Text())
    evidence_doc_ids: Mapped[JsonArray] = mapped_column(JsonType, default=list)


class MacroEvent(UpdatedTimestampMixin, Base):
    """A macro data point (CPI / rate / employment ...) for the calendar view."""

    __tablename__ = "macro_event"
    __table_args__ = (Index("idx_macro_event_workspace", "workspace_id", "event_at"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), nullable=False)
    title: Mapped[str] = mapped_column(Text(), nullable=False)
    source_name: Mapped[str | None] = mapped_column(String(255))
    source_url: Mapped[str | None] = mapped_column(Text())
    importance: Mapped[str] = mapped_column(String(32), default="medium", server_default="medium")
    impact_horizon: Mapped[str] = mapped_column(String(32), default="mid", server_default="mid")
    event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    value: Mapped[str | None] = mapped_column(String(128))
    unit: Mapped[str | None] = mapped_column(String(64))
    raw_payload: Mapped[JsonObject] = mapped_column(JsonType, default=dict)

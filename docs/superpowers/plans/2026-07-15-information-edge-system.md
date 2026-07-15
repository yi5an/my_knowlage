# Information Edge System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the full topic-first information edge system: themes -> first-hand sources/person sources -> layered collection -> weak signals -> source tracing -> market feedback -> information-edge digest.

**Architecture:** Extend the existing investment module instead of creating a parallel system. `InvestmentItem` remains the unified ingestion table; `InvestmentFact` remains evidence-backed fact storage; `InvestmentSignal` is upgraded into a weak-signal lifecycle; new theme/source/person/trace/market-feedback objects provide the missing topic boundary and information-edge scoring. Frontend adds theme-centered workflows and an information-edge digest, but every page is an outlet for the underlying source hierarchy and signal verification model.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic, existing `TaskJob` worker, React + TypeScript + Vite + Ant Design, existing X Web collector and YouTube source tracing.

---

## File Structure

- Modify: `backend/app/infrastructure/models.py`
  - Add `InvestmentTheme`, `InvestmentThemeSource`, `InvestmentPersonSource`, `InvestmentSourceTrace`, `InvestmentMarketFeedback`.
  - Extend `InvestmentItem` with `theme_id`, `source_layer`, `collected_at`.
  - Extend `InvestmentSignal` with lifecycle, score, validation, and source-layer fields.
- Add: `backend/alembic/versions/202607150005_information_edge_system.py`
  - Create new tables and add nullable columns for backwards-compatible migration.
- Modify: `backend/app/schemas/investment.py`
  - Add enums and schemas for theme, source layer, person source, source trace, market feedback, and information-edge digest.
- Modify: `backend/app/services/investment/service.py`
  - Add theme CRUD, theme source binding, person source CRUD, layered list methods, and information-edge digest aggregation.
- Add: `backend/app/services/investment/theme_defaults.py`
  - Seed the initial user-requested themes and known first-hand/source-layer defaults.
- Add: `backend/app/services/investment/information_edge.py`
  - Score weak signals and assemble information-edge cards.
- Add: `backend/app/services/investment/source_trace_service.py`
  - Generalize YouTube source tracing into reusable persisted source traces.
- Modify: `backend/app/services/investment/signal_service.py`
  - Use source layers and scoring when building weak signals.
- Modify: `backend/app/services/investment/repositories.py`
  - Populate item `theme_id`, `source_layer`, and `collected_at` from sources/watchlists.
- Modify: `backend/app/services/investment/x_web.py`
  - Bind X imports to person sources/themes when collector metadata is available.
- Modify: `backend/app/api/v1/investment.py`
  - Add theme/person/source-trace/market-feedback/information-edge endpoints.
- Modify: `backend/app/api/v1/youtube.py`
  - Store source traces after YouTube summary card construction or retry completion.
- Add tests:
  - `backend/tests/test_information_edge_models.py`
  - `backend/tests/test_investment_themes_api.py`
  - `backend/tests/test_person_sources.py`
  - `backend/tests/test_information_edge_scoring.py`
  - `backend/tests/test_source_trace_service.py`
  - `backend/tests/test_information_edge_digest.py`
- Modify frontend:
  - `frontend/src/services/investmentApi.ts`
  - `frontend/src/App.tsx`
  - Add `frontend/src/pages/InvestmentThemesPage.tsx`
  - Add `frontend/src/pages/InformationEdgePage.tsx`
  - Add `frontend/src/components/investment/SourceLayerTag.tsx`
  - Add `frontend/src/components/investment/InformationEdgeCard.tsx`
- Add frontend tests:
  - `frontend/src/pages/InvestmentThemesPage.test.tsx`
  - `frontend/src/pages/InformationEdgePage.test.tsx`

---

## Task 1: Theme And Source-Layer Contracts

**Purpose:** Make topic boundary and source hierarchy explicit before touching service logic.

**Files:**
- Modify: `backend/app/schemas/investment.py`
- Test: `backend/tests/test_investment_themes_api.py`

- [ ] **Step 1: Write failing schema tests**

Add to `backend/tests/test_investment_themes_api.py`:

```python
from app.schemas.investment import (
    InvestmentThemeCreate,
    InvestmentThemeResponse,
    PersonSourceCreate,
    SourceLayer,
)


def test_theme_schema_accepts_topic_first_fields() -> None:
    payload = InvestmentThemeCreate(
        name="AI 算力",
        theme_type="sector",
        keywords=["HBM", "数据中心电力"],
        entities=["NVDA", "AMD", "台积电"],
        tickers=["NVDA", "AMD", "TSM"],
        priority="high",
    )

    assert payload.workspace_id == "ws_default"
    assert payload.name == "AI 算力"
    assert payload.entities == ["NVDA", "AMD", "台积电"]


def test_source_layer_enum_contains_required_layers() -> None:
    assert SourceLayer.PRIMARY_SOURCE == "primary_source"
    assert SourceLayer.HUMAN_SOURCE == "human_source"
    assert SourceLayer.EXPERT_OPINION == "expert_opinion"
    assert SourceLayer.NEWS_CONFIRMATION == "news_confirmation"
    assert SourceLayer.MARKET_FEEDBACK == "market_feedback"


def test_person_source_schema_models_human_source_pool() -> None:
    payload = PersonSourceCreate(
        platform="x",
        handle="sama",
        display_name="Sam Altman",
        role_type="executive",
        credibility=0.8,
        noise_level=0.3,
        theme_ids=["theme_ai_compute"],
    )

    assert payload.handle == "sama"
    assert payload.theme_ids == ["theme_ai_compute"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_investment_themes_api.py::test_theme_schema_accepts_topic_first_fields tests/test_investment_themes_api.py::test_source_layer_enum_contains_required_layers tests/test_investment_themes_api.py::test_person_source_schema_models_human_source_pool -q
```

Expected: import errors for `InvestmentThemeCreate`, `SourceLayer`, and `PersonSourceCreate`.

- [ ] **Step 3: Add schema contracts**

In `backend/app/schemas/investment.py`, after `SourceCredibility`, add:

```python
class SourceLayer(StrEnum):
    PRIMARY_SOURCE = "primary_source"
    HUMAN_SOURCE = "human_source"
    EXPERT_OPINION = "expert_opinion"
    NEWS_CONFIRMATION = "news_confirmation"
    MARKET_FEEDBACK = "market_feedback"


class ThemeType(StrEnum):
    COMPANY_CLUSTER = "company_cluster"
    MACRO = "macro"
    SECTOR = "sector"
    ASSET = "asset"
    GEOPOLITICS = "geopolitics"
    CUSTOM = "custom"


class SignalStage(StrEnum):
    NEW = "new"
    REPEATING = "repeating"
    VALIDATED = "validated"
    REFUTED = "refuted"
    STALE = "stale"
    NOISE = "noise"


class TraceType(StrEnum):
    CONFIRMED_CITATION = "confirmed_citation"
    LIKELY_SOURCE = "likely_source"
    SAME_TOPIC = "same_topic"
    UNMATCHED = "unmatched"


class Actionability(StrEnum):
    IMMEDIATE_ATTENTION = "immediate_attention"
    WATCH = "watch"
    WEAK_SIGNAL = "weak_signal"
    NOISE = "noise"
```

After watchlist schemas, add:

```python
class InvestmentThemeCreate(BaseModel):
    workspace_id: str = Field(default="ws_default")
    name: str
    description: str | None = None
    theme_type: ThemeType = Field(default=ThemeType.CUSTOM)
    keywords: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    tickers: list[str] = Field(default_factory=list)
    enabled: bool = True
    priority: str = Field(default="medium")


class InvestmentThemeUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    theme_type: ThemeType | None = None
    keywords: list[str] | None = None
    entities: list[str] | None = None
    tickers: list[str] | None = None
    enabled: bool | None = None
    priority: str | None = None


class InvestmentThemeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    name: str
    description: str | None = None
    theme_type: str
    keywords: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    tickers: list[str] = Field(default_factory=list)
    enabled: bool
    priority: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ThemeSourceBindRequest(BaseModel):
    source_id: str
    source_layer: SourceLayer
    priority: int = Field(default=50, ge=0, le=100)
    collector_type: str | None = None
    coverage_notes: str | None = None
    enabled: bool = True


class ThemeSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    theme_id: str
    source_id: str
    source_layer: str
    priority: int
    collector_type: str | None = None
    coverage_notes: str | None = None
    enabled: bool
```

Add person-source schemas:

```python
class PersonSourceCreate(BaseModel):
    workspace_id: str = Field(default="ws_default")
    theme_ids: list[str] = Field(default_factory=list)
    platform: str
    handle: str
    display_name: str | None = None
    role_type: str = Field(default="other")
    credibility: float = Field(default=0.5, ge=0.0, le=1.0)
    noise_level: float = Field(default=0.5, ge=0.0, le=1.0)
    known_bias: str | None = None
    enabled: bool = True

    @field_validator("handle")
    @classmethod
    def normalize_handle(cls, value: str) -> str:
        return value.strip().removeprefix("@")


class PersonSourceUpdate(BaseModel):
    theme_ids: list[str] | None = None
    display_name: str | None = None
    role_type: str | None = None
    credibility: float | None = Field(default=None, ge=0.0, le=1.0)
    noise_level: float | None = Field(default=None, ge=0.0, le=1.0)
    known_bias: str | None = None
    enabled: bool | None = None


class PersonSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    theme_ids: list[str] = Field(default_factory=list)
    platform: str
    handle: str
    display_name: str | None = None
    role_type: str
    credibility: float
    noise_level: float
    known_bias: str | None = None
    enabled: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None
```

- [ ] **Step 4: Run schema tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_investment_themes_api.py -q
```

Expected: schema tests pass; API tests not yet present.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/investment.py backend/tests/test_investment_themes_api.py
git commit -m "feat: add information edge schema contracts"
```

---

## Task 2: Database Models And Migration

**Purpose:** Persist themes, source binding, person sources, source traces, market feedback, and weak-signal lifecycle metadata.

**Files:**
- Modify: `backend/app/infrastructure/models.py`
- Add: `backend/alembic/versions/202607150005_information_edge_system.py`
- Test: `backend/tests/test_information_edge_models.py`

- [ ] **Step 1: Write failing model tests**

Create `backend/tests/test_information_edge_models.py`:

```python
from collections.abc import Generator
from datetime import UTC, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base
from app.infrastructure.models import (
    InvestmentItem,
    InvestmentMarketFeedback,
    InvestmentPersonSource,
    InvestmentSignal,
    InvestmentSource,
    InvestmentSourceTrace,
    InvestmentTheme,
    InvestmentThemeSource,
    Workspace,
)


def _session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as session:
        session.add(Workspace(id="ws_default", name="Default"))
        session.commit()
        yield session


def test_theme_source_person_and_trace_models_can_persist() -> None:
    session = next(_session())
    theme = InvestmentTheme(
        id="theme_ai_compute",
        workspace_id="ws_default",
        name="AI 算力",
        theme_type="sector",
        keywords=["HBM"],
        entities=["NVDA"],
        tickers=["NVDA"],
        priority="high",
    )
    source = InvestmentSource(
        id="src_nvda_ir",
        workspace_id="ws_default",
        source_type="rss",
        name="NVIDIA IR",
        url="https://nvidianews.nvidia.com/",
    )
    session.add_all([theme, source])
    session.commit()

    session.add(
        InvestmentThemeSource(
            id="ts_ai_nvda",
            workspace_id="ws_default",
            theme_id=theme.id,
            source_id=source.id,
            source_layer="primary_source",
            priority=95,
            collector_type="rss",
        )
    )
    session.add(
        InvestmentPersonSource(
            id="person_sama",
            workspace_id="ws_default",
            theme_ids=[theme.id],
            platform="x",
            handle="sama",
            display_name="Sam Altman",
            role_type="executive",
            credibility=0.8,
            noise_level=0.3,
        )
    )
    item_a = InvestmentItem(
        id="inv_source",
        workspace_id="ws_default",
        theme_id=theme.id,
        source_id=source.id,
        dedupe_key="source",
        title="NVIDIA announces Blackwell update",
        source_layer="primary_source",
        collected_at=datetime.now(UTC),
    )
    item_b = InvestmentItem(
        id="inv_youtube",
        workspace_id="ws_default",
        theme_id=theme.id,
        dedupe_key="youtube",
        title="YouTube explains Blackwell update",
        source_layer="expert_opinion",
        collected_at=datetime.now(UTC),
    )
    session.add_all([item_a, item_b])
    session.commit()
    session.add(
        InvestmentSourceTrace(
            id="trace_1",
            workspace_id="ws_default",
            theme_id=theme.id,
            target_item_id=item_b.id,
            source_item_id=item_a.id,
            trace_type="likely_source",
            match_reason="same entity and earlier primary source",
            matched_fact="Blackwell update",
            lead_time_hours=8.5,
            confidence=0.82,
        )
    )
    session.add(
        InvestmentMarketFeedback(
            id="mf_1",
            workspace_id="ws_default",
            theme_id=theme.id,
            symbol="NVDA",
            metric_type="price_change",
            observed_at=datetime.now(UTC),
            value=2.4,
            unit="percent",
            source_name="market",
        )
    )
    session.commit()

    assert session.scalar(select(InvestmentTheme).where(InvestmentTheme.id == theme.id)) is not None
    assert session.scalar(select(InvestmentSourceTrace)).lead_time_hours == 8.5
    assert session.scalar(select(InvestmentMarketFeedback)).symbol == "NVDA"


def test_signal_model_stores_information_edge_fields() -> None:
    session = next(_session())
    signal = InvestmentSignal(
        id="sig_1",
        workspace_id="ws_default",
        title="NVDA / capex_signal",
        summary="多源重复出现 AI capex 继续扩张信号。",
        signal_type="capex_signal",
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
        source_count=3,
        fact_ids=["fact_1"],
        item_ids=["inv_1"],
        confidence=0.78,
        signal_stage="repeating",
        source_layers=["primary_source", "human_source"],
        first_source_layer="human_source",
        first_source_id="person_sama",
        validation_state="pending",
        validation_sources=[],
        lead_time_hours=12.0,
        information_edge_score=0.72,
        actionability="watch",
        score_breakdown={"lead_time_score": 0.8},
    )
    session.add(signal)
    session.commit()

    saved = session.get(InvestmentSignal, "sig_1")
    assert saved.signal_stage == "repeating"
    assert saved.information_edge_score == 0.72
    assert saved.score_breakdown["lead_time_score"] == 0.8
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_information_edge_models.py -q
```

Expected: import errors for new ORM models and missing `InvestmentItem.theme_id/source_layer/collected_at` and `InvestmentSignal` fields.

- [ ] **Step 3: Add ORM models and nullable columns**

In `backend/app/infrastructure/models.py`, add after `InvestmentWatchlist`:

```python
class InvestmentTheme(UpdatedTimestampMixin, Base):
    """A durable research theme that owns sources, people, signals, and evidence."""

    __tablename__ = "investment_theme"
    __table_args__ = (
        Index("idx_investment_theme_workspace", "workspace_id", "enabled"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text())
    theme_type: Mapped[str] = mapped_column(String(32), default="custom", server_default="custom")
    keywords: Mapped[JsonArray] = mapped_column(JsonType, default=list)
    entities: Mapped[JsonArray] = mapped_column(JsonType, default=list)
    tickers: Mapped[JsonArray] = mapped_column(JsonType, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean(), default=True, server_default="true")
    priority: Mapped[str] = mapped_column(String(32), default="medium", server_default="medium")


class InvestmentThemeSource(UpdatedTimestampMixin, Base):
    """Binding between a research theme and a configured data source."""

    __tablename__ = "investment_theme_source"
    __table_args__ = (
        UniqueConstraint("theme_id", "source_id", name="uq_investment_theme_source"),
        Index("idx_investment_theme_source_theme", "workspace_id", "theme_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), nullable=False)
    theme_id: Mapped[str] = mapped_column(ForeignKey("investment_theme.id"), nullable=False)
    source_id: Mapped[str] = mapped_column(ForeignKey("investment_source.id"), nullable=False)
    source_layer: Mapped[str] = mapped_column(String(32), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=50, server_default="50")
    collector_type: Mapped[str | None] = mapped_column(String(64))
    coverage_notes: Mapped[str | None] = mapped_column(Text())
    enabled: Mapped[bool] = mapped_column(Boolean(), default=True, server_default="true")


class InvestmentPersonSource(UpdatedTimestampMixin, Base):
    """A human source account tied to one or more research themes."""

    __tablename__ = "investment_person_source"
    __table_args__ = (
        Index("idx_investment_person_source_platform", "workspace_id", "platform", "handle"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), nullable=False)
    theme_ids: Mapped[JsonArray] = mapped_column(JsonType, default=list)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    handle: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))
    role_type: Mapped[str] = mapped_column(String(64), default="other", server_default="other")
    credibility: Mapped[float] = mapped_column(Float, default=0.5, server_default="0.5")
    noise_level: Mapped[float] = mapped_column(Float, default=0.5, server_default="0.5")
    known_bias: Mapped[str | None] = mapped_column(Text())
    enabled: Mapped[bool] = mapped_column(Boolean(), default=True, server_default="true")
```

Extend `InvestmentItem`:

```python
theme_id: Mapped[str | None] = mapped_column(ForeignKey("investment_theme.id"))
source_layer: Mapped[str] = mapped_column(String(32), default="news_confirmation", server_default="news_confirmation")
collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

Extend `InvestmentSignal`:

```python
signal_stage: Mapped[str] = mapped_column(String(32), default="new", server_default="new")
source_layers: Mapped[JsonArray] = mapped_column(JsonType, default=list)
first_source_layer: Mapped[str | None] = mapped_column(String(32))
first_source_id: Mapped[str | None] = mapped_column(String(64))
validation_state: Mapped[str] = mapped_column(String(32), default="pending", server_default="pending")
validation_sources: Mapped[JsonArray] = mapped_column(JsonType, default=list)
market_feedback: Mapped[JsonObject] = mapped_column(JsonType, default=dict)
lead_time_hours: Mapped[float | None] = mapped_column(Float)
information_edge_score: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
actionability: Mapped[str] = mapped_column(String(32), default="weak_signal", server_default="weak_signal")
score_breakdown: Mapped[JsonObject] = mapped_column(JsonType, default=dict)
```

Add after `InvestmentSignal`:

```python
class InvestmentSourceTrace(UpdatedTimestampMixin, Base):
    """A persisted source relationship between two investment items."""

    __tablename__ = "investment_source_trace"
    __table_args__ = (
        Index("idx_investment_source_trace_target", "workspace_id", "target_item_id"),
        Index("idx_investment_source_trace_theme", "workspace_id", "theme_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), nullable=False)
    theme_id: Mapped[str | None] = mapped_column(ForeignKey("investment_theme.id"))
    target_item_id: Mapped[str] = mapped_column(ForeignKey("investment_item.id"), nullable=False)
    source_item_id: Mapped[str | None] = mapped_column(ForeignKey("investment_item.id"))
    trace_type: Mapped[str] = mapped_column(String(32), default="same_topic", server_default="same_topic")
    match_reason: Mapped[str] = mapped_column(Text(), nullable=False)
    matched_fact: Mapped[str | None] = mapped_column(Text())
    lead_time_hours: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)


class InvestmentMarketFeedback(UpdatedTimestampMixin, Base):
    """Market reaction attached to a theme or symbol."""

    __tablename__ = "investment_market_feedback"
    __table_args__ = (
        Index("idx_investment_market_feedback_theme", "workspace_id", "theme_id", "observed_at"),
        Index("idx_investment_market_feedback_symbol", "workspace_id", "symbol", "observed_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), nullable=False)
    theme_id: Mapped[str | None] = mapped_column(ForeignKey("investment_theme.id"))
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    metric_type: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(32))
    source_name: Mapped[str | None] = mapped_column(String(255))
    raw_payload: Mapped[JsonObject] = mapped_column(JsonType, default=dict)
```

- [ ] **Step 4: Add Alembic migration**

Create `backend/alembic/versions/202607150005_information_edge_system.py` with Postgres/SQLite-safe DDL:

```python
"""information edge system

Revision ID: 202607150005
Revises: 202607150004
Create Date: 2026-07-15
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from app.infrastructure.database import JsonType

revision = "202607150005"
down_revision = "202607150004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investment_theme",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("theme_type", sa.String(32), server_default="custom", nullable=False),
        sa.Column("keywords", JsonType(), nullable=False),
        sa.Column("entities", JsonType(), nullable=False),
        sa.Column("tickers", JsonType(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("priority", sa.String(32), server_default="medium", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_investment_theme_workspace", "investment_theme", ["workspace_id", "enabled"])

    op.create_table(
        "investment_theme_source",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("theme_id", sa.String(64), sa.ForeignKey("investment_theme.id"), nullable=False),
        sa.Column("source_id", sa.String(64), sa.ForeignKey("investment_source.id"), nullable=False),
        sa.Column("source_layer", sa.String(32), nullable=False),
        sa.Column("priority", sa.Integer(), server_default="50", nullable=False),
        sa.Column("collector_type", sa.String(64)),
        sa.Column("coverage_notes", sa.Text()),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("theme_id", "source_id", name="uq_investment_theme_source"),
    )
    op.create_index("idx_investment_theme_source_theme", "investment_theme_source", ["workspace_id", "theme_id"])

    op.create_table(
        "investment_person_source",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("theme_ids", JsonType(), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("handle", sa.String(128), nullable=False),
        sa.Column("display_name", sa.String(255)),
        sa.Column("role_type", sa.String(64), server_default="other", nullable=False),
        sa.Column("credibility", sa.Float(), server_default="0.5", nullable=False),
        sa.Column("noise_level", sa.Float(), server_default="0.5", nullable=False),
        sa.Column("known_bias", sa.Text()),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_investment_person_source_platform", "investment_person_source", ["workspace_id", "platform", "handle"])

    op.add_column("investment_item", sa.Column("theme_id", sa.String(64), sa.ForeignKey("investment_theme.id")))
    op.add_column("investment_item", sa.Column("source_layer", sa.String(32), server_default="news_confirmation", nullable=False))
    op.add_column("investment_item", sa.Column("collected_at", sa.DateTime(timezone=True)))
    op.create_index("idx_investment_item_theme", "investment_item", ["workspace_id", "theme_id", "published_at"])

    op.add_column("investment_signal", sa.Column("signal_stage", sa.String(32), server_default="new", nullable=False))
    op.add_column("investment_signal", sa.Column("source_layers", JsonType(), nullable=False))
    op.add_column("investment_signal", sa.Column("first_source_layer", sa.String(32)))
    op.add_column("investment_signal", sa.Column("first_source_id", sa.String(64)))
    op.add_column("investment_signal", sa.Column("validation_state", sa.String(32), server_default="pending", nullable=False))
    op.add_column("investment_signal", sa.Column("validation_sources", JsonType(), nullable=False))
    op.add_column("investment_signal", sa.Column("market_feedback", JsonType(), nullable=False))
    op.add_column("investment_signal", sa.Column("lead_time_hours", sa.Float()))
    op.add_column("investment_signal", sa.Column("information_edge_score", sa.Float(), server_default="0", nullable=False))
    op.add_column("investment_signal", sa.Column("actionability", sa.String(32), server_default="weak_signal", nullable=False))
    op.add_column("investment_signal", sa.Column("score_breakdown", JsonType(), nullable=False))

    op.create_table(
        "investment_source_trace",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("theme_id", sa.String(64), sa.ForeignKey("investment_theme.id")),
        sa.Column("target_item_id", sa.String(64), sa.ForeignKey("investment_item.id"), nullable=False),
        sa.Column("source_item_id", sa.String(64), sa.ForeignKey("investment_item.id")),
        sa.Column("trace_type", sa.String(32), server_default="same_topic", nullable=False),
        sa.Column("match_reason", sa.Text(), nullable=False),
        sa.Column("matched_fact", sa.Text()),
        sa.Column("lead_time_hours", sa.Float()),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_investment_source_trace_target", "investment_source_trace", ["workspace_id", "target_item_id"])
    op.create_index("idx_investment_source_trace_theme", "investment_source_trace", ["workspace_id", "theme_id"])

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
        sa.Column("raw_payload", JsonType(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_investment_market_feedback_theme", "investment_market_feedback", ["workspace_id", "theme_id", "observed_at"])
    op.create_index("idx_investment_market_feedback_symbol", "investment_market_feedback", ["workspace_id", "symbol", "observed_at"])


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
    op.drop_column("investment_item", "theme_id")
    op.drop_index("idx_investment_person_source_platform", table_name="investment_person_source")
    op.drop_table("investment_person_source")
    op.drop_index("idx_investment_theme_source_theme", table_name="investment_theme_source")
    op.drop_table("investment_theme_source")
    op.drop_index("idx_investment_theme_workspace", table_name="investment_theme")
    op.drop_table("investment_theme")
```

- [ ] **Step 5: Run model tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_information_edge_models.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/infrastructure/models.py backend/alembic/versions/202607150005_information_edge_system.py backend/tests/test_information_edge_models.py
git commit -m "feat: add information edge data model"
```

---

## Task 3: Theme And Person Source APIs

**Purpose:** Let the user create topic boundaries, bind sources by layer, and maintain a human-source account pool.

**Files:**
- Modify: `backend/app/services/investment/service.py`
- Modify: `backend/app/api/v1/investment.py`
- Modify: `backend/app/schemas/investment.py`
- Test: `backend/tests/test_investment_themes_api.py`
- Test: `backend/tests/test_person_sources.py`

- [ ] **Step 1: Add failing API tests**

Append to `backend/tests/test_investment_themes_api.py`:

```python
from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base, get_db_session
from app.infrastructure.models import InvestmentSource, Workspace
from app.main import app


def _client() -> Generator[tuple[TestClient, Session], None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    session.add(Workspace(id="ws_default", name="Default"))
    session.add(
        InvestmentSource(
            id="src_nvda_ir",
            workspace_id="ws_default",
            source_type="rss",
            name="NVIDIA IR",
            url="https://nvidianews.nvidia.com/",
        )
    )
    session.commit()

    def override_db():
        yield session

    app.dependency_overrides[get_db_session] = override_db
    try:
        yield TestClient(app), session
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_create_theme_and_bind_primary_source() -> None:
    client, _ = next(_client())

    created = client.post(
        "/api/v1/investment/themes",
        json={
            "name": "AI 算力",
            "theme_type": "sector",
            "keywords": ["HBM"],
            "entities": ["NVDA"],
            "tickers": ["NVDA"],
            "priority": "high",
        },
    )
    assert created.status_code == 201
    theme = created.json()
    assert theme["name"] == "AI 算力"

    bound = client.post(
        f"/api/v1/investment/themes/{theme['id']}/sources",
        json={
            "source_id": "src_nvda_ir",
            "source_layer": "primary_source",
            "priority": 95,
            "collector_type": "rss",
        },
    )
    assert bound.status_code == 201
    assert bound.json()["source_layer"] == "primary_source"

    listed = client.get("/api/v1/investment/themes")
    assert listed.status_code == 200
    assert listed.json()[0]["name"] == "AI 算力"
```

Create `backend/tests/test_person_sources.py`:

```python
from tests.test_investment_themes_api import _client


def test_create_person_source_for_theme() -> None:
    client, _ = next(_client())
    theme = client.post(
        "/api/v1/investment/themes",
        json={"name": "宏观", "theme_type": "macro", "keywords": ["FOMC"]},
    ).json()

    created = client.post(
        "/api/v1/investment/person-sources",
        json={
            "theme_ids": [theme["id"]],
            "platform": "x",
            "handle": "@NickTimiraos",
            "display_name": "Nick Timiraos",
            "role_type": "journalist",
            "credibility": 0.85,
            "noise_level": 0.2,
        },
    )

    assert created.status_code == 201
    body = created.json()
    assert body["handle"] == "NickTimiraos"
    assert body["theme_ids"] == [theme["id"]]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_investment_themes_api.py tests/test_person_sources.py -q
```

Expected: 404 for new endpoints or missing service methods.

- [ ] **Step 3: Implement service methods**

In `backend/app/services/investment/service.py`, import new models and schemas, then add:

```python
def create_theme(self, payload: InvestmentThemeCreate) -> InvestmentTheme:
    theme = InvestmentTheme(
        id=_new_id("theme"),
        workspace_id=payload.workspace_id,
        name=payload.name,
        description=payload.description,
        theme_type=payload.theme_type.value,
        keywords=list(payload.keywords),
        entities=list(payload.entities),
        tickers=list(payload.tickers),
        enabled=payload.enabled,
        priority=payload.priority,
    )
    self.session.add(theme)
    self.session.commit()
    self.session.refresh(theme)
    return theme


def list_themes(self, workspace_id: str = "ws_default") -> list[InvestmentTheme]:
    return list(
        self.session.scalars(
            select(InvestmentTheme)
            .where(InvestmentTheme.workspace_id == workspace_id)
            .order_by(InvestmentTheme.priority.desc(), InvestmentTheme.name)
        )
    )


def bind_theme_source(
    self,
    theme_id: str,
    payload: ThemeSourceBindRequest,
    *,
    workspace_id: str = "ws_default",
) -> InvestmentThemeSource:
    existing = self.session.scalar(
        select(InvestmentThemeSource).where(
            InvestmentThemeSource.workspace_id == workspace_id,
            InvestmentThemeSource.theme_id == theme_id,
            InvestmentThemeSource.source_id == payload.source_id,
        )
    )
    if existing is not None:
        existing.source_layer = payload.source_layer.value
        existing.priority = payload.priority
        existing.collector_type = payload.collector_type
        existing.coverage_notes = payload.coverage_notes
        existing.enabled = payload.enabled
        self.session.commit()
        self.session.refresh(existing)
        return existing
    binding = InvestmentThemeSource(
        id=_new_id("themesrc"),
        workspace_id=workspace_id,
        theme_id=theme_id,
        source_id=payload.source_id,
        source_layer=payload.source_layer.value,
        priority=payload.priority,
        collector_type=payload.collector_type,
        coverage_notes=payload.coverage_notes,
        enabled=payload.enabled,
    )
    self.session.add(binding)
    self.session.commit()
    self.session.refresh(binding)
    return binding


def create_person_source(self, payload: PersonSourceCreate) -> InvestmentPersonSource:
    person = InvestmentPersonSource(
        id=_new_id("person"),
        workspace_id=payload.workspace_id,
        theme_ids=list(payload.theme_ids),
        platform=payload.platform,
        handle=payload.handle,
        display_name=payload.display_name,
        role_type=payload.role_type,
        credibility=payload.credibility,
        noise_level=payload.noise_level,
        known_bias=payload.known_bias,
        enabled=payload.enabled,
    )
    self.session.add(person)
    self.session.commit()
    self.session.refresh(person)
    return person
```

- [ ] **Step 4: Add API routes**

In `backend/app/api/v1/investment.py`, import new schemas and add:

```python
@router.get("/themes", response_model=list[InvestmentThemeResponse])
async def list_themes(
    workspace_id: str = "ws_default",
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> list[InvestmentThemeResponse]:
    return [
        InvestmentThemeResponse.model_validate(theme)
        for theme in service.list_themes(workspace_id)
    ]


@router.post("/themes", response_model=InvestmentThemeResponse, status_code=201)
async def create_theme(
    payload: InvestmentThemeCreate,
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> InvestmentThemeResponse:
    return InvestmentThemeResponse.model_validate(service.create_theme(payload))


@router.post(
    "/themes/{theme_id}/sources",
    response_model=ThemeSourceResponse,
    status_code=201,
)
async def bind_theme_source(
    theme_id: str,
    payload: ThemeSourceBindRequest,
    workspace_id: str = "ws_default",
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> ThemeSourceResponse:
    return ThemeSourceResponse.model_validate(
        service.bind_theme_source(theme_id, payload, workspace_id=workspace_id)
    )


@router.post(
    "/person-sources",
    response_model=PersonSourceResponse,
    status_code=201,
)
async def create_person_source(
    payload: PersonSourceCreate,
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> PersonSourceResponse:
    return PersonSourceResponse.model_validate(service.create_person_source(payload))
```

- [ ] **Step 5: Run API tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_investment_themes_api.py tests/test_person_sources.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/investment/service.py backend/app/api/v1/investment.py backend/app/schemas/investment.py backend/tests/test_investment_themes_api.py backend/tests/test_person_sources.py
git commit -m "feat: add theme and person source APIs"
```

---

## Task 4: Default Themes And Source-Layer Backfill

**Purpose:** Seed the user-requested tracking domains and classify existing source/item layers so the system stops being a generic feed.

**Files:**
- Add: `backend/app/services/investment/theme_defaults.py`
- Add: `backend/scripts/backfill_information_edge_layers.py`
- Test: `backend/tests/test_information_edge_backfill.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_information_edge_backfill.py`:

```python
from tests.test_investment_themes_api import _client


def test_default_themes_include_user_tracking_domains() -> None:
    from app.services.investment.theme_defaults import default_themes

    names = {theme["name"] for theme in default_themes()}
    assert {"AI 算力", "宏观", "特斯拉 / Robotaxi / 自动驾驶"}.issubset(names)


def test_backfill_assigns_source_layer_from_source_type() -> None:
    client, session = next(_client())
    from app.infrastructure.models import InvestmentItem
    from scripts.backfill_information_edge_layers import backfill_layers

    session.add(
        InvestmentItem(
            id="inv_sec",
            workspace_id="ws_default",
            source_id="src_nvda_ir",
            dedupe_key="sec",
            title="SEC filing",
            info_layer="primary_source",
        )
    )
    session.commit()

    result = backfill_layers(session, workspace_id="ws_default")
    item = session.get(InvestmentItem, "inv_sec")

    assert result["items_seen"] == 1
    assert item.source_layer == "primary_source"
    assert item.collected_at is not None
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_information_edge_backfill.py -q
```

Expected: module import errors.

- [ ] **Step 3: Add default theme definitions**

Create `backend/app/services/investment/theme_defaults.py`:

```python
from __future__ import annotations


def default_themes() -> list[dict[str, object]]:
    return [
        {
            "name": "AI 算力",
            "theme_type": "sector",
            "keywords": ["HBM", "AI 服务器", "数据中心电力", "光模块", "先进封装"],
            "entities": ["NVDA", "AMD", "台积电", "博通", "Marvell", "Arista", "Supermicro"],
            "tickers": ["NVDA", "AMD", "TSM", "AVGO", "MRVL", "ANET", "SMCI"],
            "priority": "high",
        },
        {
            "name": "宏观",
            "theme_type": "macro",
            "keywords": ["美联储", "通胀", "就业", "财政", "美元流动性", "FOMC", "Treasury"],
            "entities": ["Federal Reserve", "BLS", "Treasury", "BEA"],
            "tickers": [],
            "priority": "high",
        },
        {
            "name": "特斯拉 / Robotaxi / 自动驾驶",
            "theme_type": "company_cluster",
            "keywords": ["Robotaxi", "FSD", "自动驾驶", "NHTSA", "Waymo", "车险"],
            "entities": ["Tesla", "Waymo", "NHTSA"],
            "tickers": ["TSLA"],
            "priority": "high",
        },
        {
            "name": "黄金 / 能源 / 军工 / 消费 / 港股科技",
            "theme_type": "asset",
            "keywords": ["黄金", "能源", "军工", "消费", "港股科技"],
            "entities": [],
            "tickers": [],
            "priority": "medium",
        },
    ]
```

- [ ] **Step 4: Add backfill script**

Create `backend/scripts/backfill_information_edge_layers.py`:

```python
from __future__ import annotations

import argparse
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.database import SessionLocal
from app.infrastructure.models import InvestmentItem, InvestmentSource


def _layer_for_item(item: InvestmentItem, source: InvestmentSource | None) -> str:
    source_type = source.source_type if source is not None else None
    if item.info_layer == "primary_source" or source_type in {
        "sec_edgar",
        "federal_reserve_rss",
        "bls",
        "fred",
        "hkex",
        "cninfo",
    }:
        return "primary_source"
    if source_type in {"x_web", "x_rss", "x_nitter", "x_brightdata"}:
        return "human_source"
    if item.source_name == "YouTube" or item.info_layer == "opinion":
        return "expert_opinion"
    if item.info_layer == "macro_calendar":
        return "primary_source"
    return "news_confirmation"


def backfill_layers(session: Session, *, workspace_id: str = "ws_default") -> dict[str, int]:
    items = list(
        session.scalars(
            select(InvestmentItem).where(InvestmentItem.workspace_id == workspace_id)
        )
    )
    source_ids = {item.source_id for item in items if item.source_id}
    sources = {
        source.id: source
        for source in session.scalars(
            select(InvestmentSource).where(InvestmentSource.id.in_(source_ids))
        )
    }
    changed = 0
    now = datetime.now(UTC)
    for item in items:
        layer = _layer_for_item(item, sources.get(item.source_id))
        if item.source_layer != layer:
            item.source_layer = layer
            changed += 1
        if item.collected_at is None:
            item.collected_at = item.created_at or now
            changed += 1
    if changed:
        session.commit()
    return {"items_seen": len(items), "items_changed": changed}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-id", default="ws_default")
    args = parser.parse_args()
    with SessionLocal() as session:
        result = backfill_layers(session, workspace_id=args.workspace_id)
    print(result)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_information_edge_backfill.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/investment/theme_defaults.py backend/scripts/backfill_information_edge_layers.py backend/tests/test_information_edge_backfill.py
git commit -m "feat: add default themes and layer backfill"
```

---

## Task 5: Information-Edge Scoring And Weak-Signal Lifecycle

**Purpose:** Upgrade early signals from simple clusters into scored weak signals with stage, validation, and actionability.

**Files:**
- Add: `backend/app/services/investment/information_edge.py`
- Modify: `backend/app/services/investment/signal_service.py`
- Test: `backend/tests/test_information_edge_scoring.py`

- [ ] **Step 1: Write failing scoring tests**

Create `backend/tests/test_information_edge_scoring.py`:

```python
from app.services.investment.information_edge import (
    InformationEdgeScoreInput,
    score_information_edge,
)


def test_score_rewards_early_primary_validated_signals() -> None:
    result = score_information_edge(
        InformationEdgeScoreInput(
            lead_time_hours=18,
            first_source_layer="primary_source",
            source_layers=["primary_source", "news_confirmation"],
            source_count=2,
            theme_relevance=0.9,
            validation_state="validated",
            market_has_reacted=False,
        )
    )

    assert result.score >= 0.75
    assert result.actionability == "immediate_attention"
    assert result.breakdown["lead_time_score"] > 0


def test_score_penalizes_single_human_source_without_validation() -> None:
    result = score_information_edge(
        InformationEdgeScoreInput(
            lead_time_hours=None,
            first_source_layer="human_source",
            source_layers=["human_source"],
            source_count=1,
            theme_relevance=0.5,
            validation_state="pending",
            market_has_reacted=True,
        )
    )

    assert result.score < 0.45
    assert result.actionability in {"weak_signal", "noise"}
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_information_edge_scoring.py -q
```

Expected: missing module.

- [ ] **Step 3: Implement scoring**

Create `backend/app/services/investment/information_edge.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InformationEdgeScoreInput:
    lead_time_hours: float | None
    first_source_layer: str | None
    source_layers: list[str]
    source_count: int
    theme_relevance: float
    validation_state: str
    market_has_reacted: bool


@dataclass(frozen=True)
class InformationEdgeScore:
    score: float
    actionability: str
    breakdown: dict[str, float]


def _lead_time_score(hours: float | None) -> float:
    if hours is None or hours <= 0:
        return 0.0
    if hours >= 72:
        return 1.0
    return min(1.0, hours / 72)


def _source_quality_score(first_source_layer: str | None) -> float:
    return {
        "primary_source": 1.0,
        "market_feedback": 0.85,
        "news_confirmation": 0.75,
        "human_source": 0.55,
        "expert_opinion": 0.35,
    }.get(first_source_layer or "", 0.25)


def _repetition_score(source_count: int, source_layers: list[str]) -> float:
    layer_bonus = min(1.0, len(set(source_layers)) / 3)
    source_bonus = min(1.0, max(0, source_count - 1) / 4)
    return max(layer_bonus, source_bonus)


def _validation_score(state: str) -> float:
    return {
        "validated": 1.0,
        "verified": 1.0,
        "local_only": 0.65,
        "pending": 0.35,
        "refuted": 0.0,
        "noise": 0.0,
    }.get(state, 0.35)


def score_information_edge(payload: InformationEdgeScoreInput) -> InformationEdgeScore:
    breakdown = {
        "lead_time_score": _lead_time_score(payload.lead_time_hours),
        "source_quality_score": _source_quality_score(payload.first_source_layer),
        "signal_repetition_score": _repetition_score(payload.source_count, payload.source_layers),
        "theme_relevance_score": max(0.0, min(1.0, payload.theme_relevance)),
        "validation_score": _validation_score(payload.validation_state),
        "market_unpriced_score": 0.0 if payload.market_has_reacted else 1.0,
    }
    score = round(
        breakdown["lead_time_score"] * 0.25
        + breakdown["source_quality_score"] * 0.20
        + breakdown["signal_repetition_score"] * 0.15
        + breakdown["theme_relevance_score"] * 0.15
        + breakdown["validation_score"] * 0.15
        + breakdown["market_unpriced_score"] * 0.10,
        2,
    )
    if score >= 0.75:
        actionability = "immediate_attention"
    elif score >= 0.55:
        actionability = "watch"
    elif score >= 0.35:
        actionability = "weak_signal"
    else:
        actionability = "noise"
    return InformationEdgeScore(score=score, actionability=actionability, breakdown=breakdown)
```

- [ ] **Step 4: Wire scoring into `InvestmentSignalService._build_signal`**

In `backend/app/services/investment/signal_service.py`, after loading `items`, compute source layers and score:

```python
source_layers = sorted({item.source_layer for item in items if getattr(item, "source_layer", None)})
first_item = min(
    items,
    key=lambda item: item.published_at or item.created_at,
    default=None,
)
first_source_layer = first_item.source_layer if first_item is not None else None
lead_time_hours = None
if first_item is not None and len(items) > 1:
    latest_time = max(
        (item.published_at or item.created_at for item in items if item.published_at or item.created_at),
        default=None,
    )
    first_time = first_item.published_at or first_item.created_at
    if latest_time is not None and first_time is not None:
        lead_time_hours = round(max(0.0, (latest_time - first_time).total_seconds() / 3600), 2)
score = score_information_edge(
    InformationEdgeScoreInput(
        lead_time_hours=lead_time_hours,
        first_source_layer=first_source_layer,
        source_layers=source_layers,
        source_count=source_count,
        theme_relevance=1.0 if group.watchlist_id else 0.6,
        validation_state="pending",
        market_has_reacted=False,
    )
)
```

Pass new fields to `InvestmentSignal(...)`:

```python
signal_stage="repeating" if len(facts) > 1 else "new",
source_layers=source_layers,
first_source_layer=first_source_layer,
first_source_id=first_item.source_id if first_item is not None else None,
validation_state="pending",
validation_sources=[],
market_feedback={},
lead_time_hours=lead_time_hours,
information_edge_score=score.score,
actionability=score.actionability,
score_breakdown=score.breakdown,
```

- [ ] **Step 5: Run signal tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_information_edge_scoring.py tests/test_investment_signals.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/investment/information_edge.py backend/app/services/investment/signal_service.py backend/tests/test_information_edge_scoring.py
git commit -m "feat: score information edge signals"
```

---

## Task 6: Persisted Source Tracing

**Purpose:** Turn source tracing from a YouTube-only card field into reusable system memory.

**Files:**
- Add: `backend/app/services/investment/source_trace_service.py`
- Modify: `backend/app/api/v1/investment.py`
- Modify: `backend/app/schemas/investment.py`
- Test: `backend/tests/test_source_trace_service.py`

- [ ] **Step 1: Write failing service tests**

Create `backend/tests/test_source_trace_service.py`:

```python
from datetime import UTC, datetime, timedelta

from tests.test_investment_themes_api import _client


def test_source_trace_service_persists_likely_earlier_source() -> None:
    _, session = next(_client())
    from app.infrastructure.models import InvestmentItem
    from app.services.investment.source_trace_service import SourceTraceService

    earlier = InvestmentItem(
        id="inv_earlier",
        workspace_id="ws_default",
        dedupe_key="earlier",
        title="NVIDIA Blackwell shipments accelerating",
        summary="Blackwell shipments are accelerating.",
        source_layer="primary_source",
        published_at=datetime(2026, 7, 15, 8, tzinfo=UTC),
    )
    later = InvestmentItem(
        id="inv_later",
        workspace_id="ws_default",
        dedupe_key="later",
        title="YouTube: Blackwell shipments are accelerating",
        summary="Creator discusses Blackwell shipments accelerating.",
        source_layer="expert_opinion",
        published_at=datetime(2026, 7, 15, 20, tzinfo=UTC),
    )
    session.add_all([earlier, later])
    session.commit()

    traces = SourceTraceService(session).trace_item(later, limit=5)

    assert len(traces) == 1
    assert traces[0].source_item_id == earlier.id
    assert traces[0].trace_type == "likely_source"
    assert traces[0].lead_time_hours == 12.0
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_source_trace_service.py -q
```

Expected: missing module.

- [ ] **Step 3: Implement source trace service**

Create `backend/app/services/investment/source_trace_service.py`:

```python
from __future__ import annotations

import re
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import InvestmentItem, InvestmentSourceTrace


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class SourceTraceService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def trace_item(self, target: InvestmentItem, *, limit: int = 5) -> list[InvestmentSourceTrace]:
        if target.published_at is None:
            return []
        window_start = target.published_at - timedelta(days=14)
        candidates = list(
            self.session.scalars(
                select(InvestmentItem).where(
                    InvestmentItem.workspace_id == target.workspace_id,
                    InvestmentItem.id != target.id,
                    InvestmentItem.published_at.is_not(None),
                    InvestmentItem.published_at <= target.published_at,
                    InvestmentItem.published_at >= window_start,
                )
            )
        )
        scored = [
            (candidate, _item_similarity(target, candidate))
            for candidate in candidates
        ]
        scored = [(candidate, score) for candidate, score in scored if score >= 0.25]
        scored.sort(key=lambda pair: pair[1], reverse=True)

        traces: list[InvestmentSourceTrace] = []
        for candidate, score in scored[:limit]:
            lead_time = round(
                max(0.0, (target.published_at - candidate.published_at).total_seconds() / 3600),
                2,
            )
            trace = InvestmentSourceTrace(
                id=_new_id("trace"),
                workspace_id=target.workspace_id,
                theme_id=target.theme_id or candidate.theme_id,
                target_item_id=target.id,
                source_item_id=candidate.id,
                trace_type="likely_source" if score >= 0.45 else "same_topic",
                match_reason="entity/phrase overlap inside the 14-day pre-publication window",
                matched_fact=_shared_terms(target, candidate),
                lead_time_hours=lead_time,
                confidence=round(min(1.0, score), 2),
            )
            self.session.add(trace)
            traces.append(trace)
        if traces:
            self.session.commit()
            for trace in traces:
                self.session.refresh(trace)
        return traces


def _tokens(item: InvestmentItem) -> set[str]:
    text = " ".join(
        [
            item.title or "",
            item.title_zh or "",
            item.summary or "",
            item.summary_zh or "",
        ]
    ).lower()
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}", text)
        if token not in {"the", "and", "for", "with", "this", "that"}
    }


def _item_similarity(left: InvestmentItem, right: InvestmentItem) -> float:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens.intersection(right_tokens))
    union = len(left_tokens.union(right_tokens))
    layer_boost = 0.15 if right.source_layer == "primary_source" else 0.0
    return min(1.0, overlap / union + layer_boost)


def _shared_terms(left: InvestmentItem, right: InvestmentItem) -> str:
    terms = sorted(_tokens(left).intersection(_tokens(right)))
    return " / ".join(terms[:8])
```

- [ ] **Step 4: Add schemas and list endpoint**

In `backend/app/schemas/investment.py`, add:

```python
class SourceTraceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    theme_id: str | None = None
    target_item_id: str
    source_item_id: str | None = None
    trace_type: str
    match_reason: str
    matched_fact: str | None = None
    lead_time_hours: float | None = None
    confidence: float
    created_at: datetime | None = None
```

In `backend/app/services/investment/service.py`, add:

```python
def list_source_traces(
    self,
    *,
    workspace_id: str = "ws_default",
    theme_id: str | None = None,
    target_item_id: str | None = None,
    limit: int = 50,
) -> list[InvestmentSourceTrace]:
    stmt = select(InvestmentSourceTrace).where(InvestmentSourceTrace.workspace_id == workspace_id)
    if theme_id is not None:
        stmt = stmt.where(InvestmentSourceTrace.theme_id == theme_id)
    if target_item_id is not None:
        stmt = stmt.where(InvestmentSourceTrace.target_item_id == target_item_id)
    return list(
        self.session.scalars(
            stmt.order_by(InvestmentSourceTrace.confidence.desc()).limit(limit)
        )
    )
```

In `backend/app/api/v1/investment.py`, add:

```python
@router.get("/source-traces", response_model=list[SourceTraceResponse])
async def list_source_traces(
    workspace_id: str = "ws_default",
    theme_id: str | None = Query(default=None),
    target_item_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> list[SourceTraceResponse]:
    return [
        SourceTraceResponse.model_validate(trace)
        for trace in service.list_source_traces(
            workspace_id=workspace_id,
            theme_id=theme_id,
            target_item_id=target_item_id,
            limit=limit,
        )
    ]
```

- [ ] **Step 5: Run source trace tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_source_trace_service.py tests/test_investment_api.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/investment/source_trace_service.py backend/app/services/investment/service.py backend/app/api/v1/investment.py backend/app/schemas/investment.py backend/tests/test_source_trace_service.py
git commit -m "feat: persist investment source traces"
```

---

## Task 7: Information-Edge Digest API

**Purpose:** Expose the system's main answer: high-scoring early information, weak signals, validation state, source traces, and market feedback.

**Files:**
- Modify: `backend/app/schemas/investment.py`
- Modify: `backend/app/services/investment/service.py`
- Modify: `backend/app/api/v1/investment.py`
- Test: `backend/tests/test_information_edge_digest.py`

- [ ] **Step 1: Write failing digest API test**

Create `backend/tests/test_information_edge_digest.py`:

```python
from datetime import UTC, datetime

from tests.test_investment_themes_api import _client


def test_information_edge_digest_returns_scored_signals_and_traces() -> None:
    client, session = next(_client())
    from app.infrastructure.models import InvestmentSignal, InvestmentSourceTrace, InvestmentTheme

    theme = InvestmentTheme(
        id="theme_ai",
        workspace_id="ws_default",
        name="AI 算力",
        theme_type="sector",
        keywords=["HBM"],
        entities=["NVDA"],
        tickers=["NVDA"],
    )
    signal = InvestmentSignal(
        id="sig_ai",
        workspace_id="ws_default",
        watchlist_id=None,
        title="NVDA / capex_signal",
        summary="多源重复出现 AI capex 扩张信号。",
        signal_type="capex_signal",
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
        source_count=2,
        fact_ids=["fact_1"],
        item_ids=["inv_1"],
        confidence=0.8,
        signal_stage="repeating",
        source_layers=["primary_source", "human_source"],
        first_source_layer="human_source",
        validation_state="pending",
        lead_time_hours=18,
        information_edge_score=0.76,
        actionability="immediate_attention",
        score_breakdown={"lead_time_score": 0.8},
    )
    trace = InvestmentSourceTrace(
        id="trace_ai",
        workspace_id="ws_default",
        theme_id=theme.id,
        target_item_id="inv_youtube",
        source_item_id="inv_1",
        trace_type="likely_source",
        match_reason="earlier source",
        matched_fact="AI capex",
        lead_time_hours=18,
        confidence=0.82,
    )
    session.add_all([theme, signal, trace])
    session.commit()

    resp = client.get("/api/v1/investment/information-edge?workspace_id=ws_default")

    assert resp.status_code == 200
    body = resp.json()
    assert body["top_signals"][0]["id"] == "sig_ai"
    assert body["top_signals"][0]["information_edge_score"] == 0.76
    assert body["source_traces"][0]["trace_type"] == "likely_source"
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_information_edge_digest.py -q
```

Expected: 404 or missing response schemas.

- [ ] **Step 3: Add response schemas**

In `backend/app/schemas/investment.py`, extend `InvestmentSignalResponse` with optional fields:

```python
signal_stage: str = "new"
source_layers: list[str] = Field(default_factory=list)
first_source_layer: str | None = None
first_source_id: str | None = None
validation_state: str = "pending"
validation_sources: list[str] = Field(default_factory=list)
market_feedback: dict[str, object] = Field(default_factory=dict)
lead_time_hours: float | None = None
information_edge_score: float = 0.0
actionability: str = "weak_signal"
score_breakdown: dict[str, float] = Field(default_factory=dict)
```

Add:

```python
class InformationEdgeDigestResponse(BaseModel):
    generated_at: datetime
    top_signals: list[InvestmentSignalResponse] = Field(default_factory=list)
    source_traces: list[SourceTraceResponse] = Field(default_factory=list)
    unvalidated_signals: list[InvestmentSignalResponse] = Field(default_factory=list)
    stale_or_noise: list[InvestmentSignalResponse] = Field(default_factory=list)
```

- [ ] **Step 4: Add service aggregation**

In `backend/app/services/investment/service.py`, add:

```python
def information_edge_digest(
    self,
    workspace_id: str = "ws_default",
    theme_id: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    signal_stmt = select(InvestmentSignal).where(InvestmentSignal.workspace_id == workspace_id)
    trace_stmt = select(InvestmentSourceTrace).where(InvestmentSourceTrace.workspace_id == workspace_id)
    if theme_id is not None:
        signal_stmt = signal_stmt.where(InvestmentSignal.watchlist_id == theme_id)
        trace_stmt = trace_stmt.where(InvestmentSourceTrace.theme_id == theme_id)
    top_signals = list(
        self.session.scalars(
            signal_stmt.order_by(
                InvestmentSignal.information_edge_score.desc(),
                InvestmentSignal.last_seen_at.desc(),
            ).limit(limit)
        )
    )
    traces = list(
        self.session.scalars(
            trace_stmt.order_by(
                InvestmentSourceTrace.confidence.desc(),
                InvestmentSourceTrace.lead_time_hours.desc().nullslast(),
            ).limit(limit)
        )
    )
    return {
        "generated_at": datetime.now(UTC),
        "top_signals": top_signals,
        "source_traces": traces,
        "unvalidated_signals": [s for s in top_signals if s.validation_state == "pending"],
        "stale_or_noise": [
            s for s in top_signals if s.signal_stage in {"stale", "noise"} or s.actionability == "noise"
        ],
    }
```

- [ ] **Step 5: Add API route**

In `backend/app/api/v1/investment.py`, add:

```python
@router.get("/information-edge", response_model=InformationEdgeDigestResponse)
async def information_edge_digest(
    workspace_id: str = "ws_default",
    theme_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> InformationEdgeDigestResponse:
    data = service.information_edge_digest(
        workspace_id=workspace_id,
        theme_id=theme_id,
        limit=limit,
    )
    return InformationEdgeDigestResponse(
        generated_at=data["generated_at"],
        top_signals=[
            InvestmentSignalResponse.model_validate(signal)
            for signal in data["top_signals"]
        ],
        source_traces=[
            SourceTraceResponse.model_validate(trace)
            for trace in data["source_traces"]
        ],
        unvalidated_signals=[
            InvestmentSignalResponse.model_validate(signal)
            for signal in data["unvalidated_signals"]
        ],
        stale_or_noise=[
            InvestmentSignalResponse.model_validate(signal)
            for signal in data["stale_or_noise"]
        ],
    )
```

- [ ] **Step 6: Run digest tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_information_edge_digest.py -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/investment.py backend/app/services/investment/service.py backend/app/api/v1/investment.py backend/tests/test_information_edge_digest.py
git commit -m "feat: add information edge digest API"
```

---

## Task 8: Frontend Theme Center And Information Edge Page

**Purpose:** Give the user a theme-first workflow, not a generic feed.

**Files:**
- Modify: `frontend/src/services/investmentApi.ts`
- Modify: `frontend/src/App.tsx`
- Add: `frontend/src/components/investment/SourceLayerTag.tsx`
- Add: `frontend/src/components/investment/InformationEdgeCard.tsx`
- Add: `frontend/src/pages/InvestmentThemesPage.tsx`
- Add: `frontend/src/pages/InformationEdgePage.tsx`
- Test: `frontend/src/pages/InvestmentThemesPage.test.tsx`
- Test: `frontend/src/pages/InformationEdgePage.test.tsx`

- [ ] **Step 1: Write failing frontend tests**

Create `frontend/src/pages/InformationEdgePage.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { InformationEdgePage } from "./InformationEdgePage";

describe("InformationEdgePage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows scored early signals and source traces", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (String(url).includes("/investment/information-edge")) {
          return new Response(
            JSON.stringify({
              generated_at: "2026-07-15T00:00:00Z",
              top_signals: [
                {
                  id: "sig_ai",
                  workspace_id: "ws_default",
                  title: "NVDA / capex_signal",
                  summary: "多源重复出现 AI capex 扩张信号。",
                  signal_type: "capex_signal",
                  first_seen_at: "2026-07-15T00:00:00Z",
                  last_seen_at: "2026-07-15T02:00:00Z",
                  source_count: 2,
                  fact_ids: ["fact_1"],
                  item_ids: ["inv_1"],
                  confidence: 0.8,
                  status: "tracking",
                  signal_stage: "repeating",
                  source_layers: ["primary_source", "human_source"],
                  first_source_layer: "human_source",
                  validation_state: "pending",
                  lead_time_hours: 18,
                  information_edge_score: 0.76,
                  actionability: "immediate_attention",
                  score_breakdown: { lead_time_score: 0.8 },
                },
              ],
              source_traces: [
                {
                  id: "trace_ai",
                  workspace_id: "ws_default",
                  target_item_id: "inv_youtube",
                  source_item_id: "inv_1",
                  trace_type: "likely_source",
                  match_reason: "earlier source",
                  matched_fact: "AI capex",
                  lead_time_hours: 18,
                  confidence: 0.82,
                },
              ],
              unvalidated_signals: [],
              stale_or_noise: [],
            }),
            { status: 200 },
          );
        }
        return new Response("not found", { status: 404 });
      }),
    );

    render(
      <MemoryRouter>
        <InformationEdgePage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("信息差系统")).toBeInTheDocument();
    });
    expect(screen.getByText("NVDA / capex_signal")).toBeInTheDocument();
    expect(screen.getByText("领先 18 小时")).toBeInTheDocument();
    expect(screen.getByText("likely_source")).toBeInTheDocument();
  });
});
```

Create `frontend/src/pages/InvestmentThemesPage.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { InvestmentThemesPage } from "./InvestmentThemesPage";

describe("InvestmentThemesPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("lists configured tracking themes", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (String(url).includes("/investment/themes")) {
          return new Response(
            JSON.stringify([
              {
                id: "theme_ai",
                workspace_id: "ws_default",
                name: "AI 算力",
                theme_type: "sector",
                keywords: ["HBM"],
                entities: ["NVDA"],
                tickers: ["NVDA"],
                enabled: true,
                priority: "high",
              },
            ]),
            { status: 200 },
          );
        }
        return new Response("not found", { status: 404 });
      }),
    );

    render(
      <MemoryRouter>
        <InvestmentThemesPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("主题中心")).toBeInTheDocument();
    expect(screen.getByText("AI 算力")).toBeInTheDocument();
    expect(screen.getByText("HBM")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run frontend tests to verify failure**

Run:

```bash
cd frontend
npm run test -- InformationEdgePage.test.tsx InvestmentThemesPage.test.tsx --run
```

Expected: missing modules/pages.

- [ ] **Step 3: Extend frontend API**

In `frontend/src/services/investmentApi.ts`, add types:

```ts
export type SourceLayer =
  | "primary_source"
  | "human_source"
  | "expert_opinion"
  | "news_confirmation"
  | "market_feedback";

export interface InvestmentTheme {
  id: string;
  workspace_id: string;
  name: string;
  description?: string | null;
  theme_type: string;
  keywords: string[];
  entities: string[];
  tickers: string[];
  enabled: boolean;
  priority: string;
}

export interface SourceTrace {
  id: string;
  workspace_id: string;
  theme_id?: string | null;
  target_item_id: string;
  source_item_id?: string | null;
  trace_type: string;
  match_reason: string;
  matched_fact?: string | null;
  lead_time_hours?: number | null;
  confidence: number;
}

export interface InformationEdgeDigest {
  generated_at: string;
  top_signals: InvestmentSignal[];
  source_traces: SourceTrace[];
  unvalidated_signals: InvestmentSignal[];
  stale_or_noise: InvestmentSignal[];
}
```

Extend `InvestmentSignal` with optional fields matching backend:

```ts
signal_stage?: string;
source_layers?: string[];
first_source_layer?: string | null;
first_source_id?: string | null;
validation_state?: string;
validation_sources?: string[];
market_feedback?: Record<string, unknown>;
lead_time_hours?: number | null;
information_edge_score?: number;
actionability?: string;
score_breakdown?: Record<string, number>;
```

Add API functions:

```ts
listThemes(workspaceId = "ws_default"): Promise<InvestmentTheme[]> {
  return apiRequest(`/investment/themes?workspace_id=${workspaceId}`);
},

getInformationEdge(workspaceId = "ws_default", themeId?: string): Promise<InformationEdgeDigest> {
  const q = new URLSearchParams({ workspace_id: workspaceId });
  if (themeId) q.set("theme_id", themeId);
  return apiRequest(`/investment/information-edge?${q.toString()}`);
},
```

- [ ] **Step 4: Add source layer tag**

Create `frontend/src/components/investment/SourceLayerTag.tsx`:

```tsx
import { Tag } from "antd";

const LABELS: Record<string, string> = {
  primary_source: "一手源",
  human_source: "人源",
  expert_opinion: "观点源",
  news_confirmation: "新闻确认",
  market_feedback: "市场反馈",
};

const COLORS: Record<string, string> = {
  primary_source: "green",
  human_source: "blue",
  expert_opinion: "purple",
  news_confirmation: "orange",
  market_feedback: "red",
};

export function SourceLayerTag({ layer }: { layer?: string | null }) {
  if (!layer) return null;
  return <Tag color={COLORS[layer] ?? "default"}>{LABELS[layer] ?? layer}</Tag>;
}
```

- [ ] **Step 5: Add InformationEdgePage**

Create `frontend/src/pages/InformationEdgePage.tsx`:

```tsx
import { Alert, Card, Empty, List, Space, Spin, Statistic, Tag, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "../components/PageHeader";
import { SourceLayerTag } from "../components/investment/SourceLayerTag";
import { ApiError } from "../services/client";
import { investmentApi, type InformationEdgeDigest } from "../services/investmentApi";

const EMPTY: InformationEdgeDigest = {
  generated_at: "",
  top_signals: [],
  source_traces: [],
  unvalidated_signals: [],
  stale_or_noise: [],
};

function leadText(hours?: number | null): string {
  if (hours == null) return "领先时间未知";
  if (hours >= 24) return `领先 ${(hours / 24).toFixed(1)} 天`;
  return `领先 ${hours} 小时`;
}

export function InformationEdgePage() {
  const [digest, setDigest] = useState<InformationEdgeDigest>(EMPTY);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setDigest(await investmentApi.getInformationEdge("ws_default"));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <main className="page">
      <PageHeader
        title="信息差系统"
        description="按主题追踪一手源、人源、观点源、新闻确认和市场反馈，识别可行动弱信号。"
      />
      {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
      <Spin spinning={loading}>
        <Space direction="vertical" size={16} style={{ width: "100%" }}>
          <Card>
            <Space wrap>
              <Statistic title="高分信号" value={digest.top_signals.length} />
              <Statistic title="来源反推" value={digest.source_traces.length} />
              <Statistic title="待验证" value={digest.unvalidated_signals.length} />
            </Space>
          </Card>
          <Card title="高优先级弱信号">
            {digest.top_signals.length === 0 ? (
              <Empty description="暂无高分信息差信号" />
            ) : (
              <List
                dataSource={digest.top_signals}
                renderItem={(signal) => (
                  <List.Item>
                    <Space direction="vertical" style={{ width: "100%" }}>
                      <Space wrap>
                        <Typography.Text strong>{signal.title}</Typography.Text>
                        <Tag color="red">分数 {Math.round((signal.information_edge_score ?? 0) * 100)}</Tag>
                        <Tag>{signal.signal_stage}</Tag>
                        <Tag color="blue">{leadText(signal.lead_time_hours)}</Tag>
                        {(signal.source_layers ?? []).map((layer) => (
                          <SourceLayerTag key={layer} layer={layer} />
                        ))}
                      </Space>
                      <Typography.Text>{signal.summary}</Typography.Text>
                    </Space>
                  </List.Item>
                )}
              />
            )}
          </Card>
          <Card title="来源反推">
            {digest.source_traces.length === 0 ? (
              <Empty description="暂无来源反推记录" />
            ) : (
              <List
                dataSource={digest.source_traces}
                renderItem={(trace) => (
                  <List.Item>
                    <Space direction="vertical">
                      <Space wrap>
                        <Tag>{trace.trace_type}</Tag>
                        <Tag color="blue">{leadText(trace.lead_time_hours)}</Tag>
                        <Tag>置信度 {Math.round(trace.confidence * 100)}%</Tag>
                      </Space>
                      <Typography.Text>{trace.matched_fact || trace.match_reason}</Typography.Text>
                    </Space>
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Space>
      </Spin>
    </main>
  );
}
```

- [ ] **Step 6: Add InvestmentThemesPage**

Create `frontend/src/pages/InvestmentThemesPage.tsx`:

```tsx
import { Alert, Card, Empty, List, Space, Spin, Tag, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "../components/PageHeader";
import { ApiError } from "../services/client";
import { investmentApi, type InvestmentTheme } from "../services/investmentApi";

export function InvestmentThemesPage() {
  const [themes, setThemes] = useState<InvestmentTheme[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setThemes(await investmentApi.listThemes("ws_default"));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <main className="page">
      <PageHeader
        title="主题中心"
        description="先定追踪主题，再绑定一手源、人源、观点源、新闻确认和市场反馈。"
      />
      {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
      <Spin spinning={loading}>
        <Card>
          {themes.length === 0 ? (
            <Empty description="暂无主题" />
          ) : (
            <List
              dataSource={themes}
              renderItem={(theme) => (
                <List.Item>
                  <Space direction="vertical" style={{ width: "100%" }}>
                    <Space wrap>
                      <Typography.Text strong>{theme.name}</Typography.Text>
                      <Tag>{theme.theme_type}</Tag>
                      <Tag color={theme.priority === "high" ? "red" : "default"}>{theme.priority}</Tag>
                    </Space>
                    <Space wrap>
                      {theme.keywords.map((keyword) => (
                        <Tag key={keyword}>{keyword}</Tag>
                      ))}
                    </Space>
                  </Space>
                </List.Item>
              )}
            />
          )}
        </Card>
      </Spin>
    </main>
  );
}
```

- [ ] **Step 7: Register routes**

In `frontend/src/App.tsx`, import:

```tsx
import { InformationEdgePage } from "./pages/InformationEdgePage";
import { InvestmentThemesPage } from "./pages/InvestmentThemesPage";
```

Add nav items near investment section:

```tsx
{ key: "/investment/themes", icon: <FundProjectionScreenOutlined />, label: <Link to="/investment/themes">主题中心</Link> },
{ key: "/investment/edge", icon: <FundProjectionScreenOutlined />, label: <Link to="/investment/edge">信息差系统</Link> },
```

Add routes:

```tsx
<Route path="/investment/themes" element={<InvestmentThemesPage />} />
<Route path="/investment/edge" element={<InformationEdgePage />} />
```

- [ ] **Step 8: Run frontend tests**

Run:

```bash
cd frontend
npm run test -- InformationEdgePage.test.tsx InvestmentThemesPage.test.tsx --run
npm run lint
npm run build
```

Expected: tests pass; lint/build pass.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/services/investmentApi.ts frontend/src/App.tsx frontend/src/components/investment/SourceLayerTag.tsx frontend/src/pages/InformationEdgePage.tsx frontend/src/pages/InvestmentThemesPage.tsx frontend/src/pages/InformationEdgePage.test.tsx frontend/src/pages/InvestmentThemesPage.test.tsx
git commit -m "feat: add theme center and information edge UI"
```

---

## Task 9: Backfill, Verification, And Remote Deployment

**Purpose:** Populate existing data with source layers, run migrations, verify real endpoints, and deploy to the remote server.

**Files:**
- Modify if needed: `README.md`
- Scripts from prior tasks.

- [ ] **Step 1: Run local backend verification**

Run:

```bash
cd backend
.venv/bin/python -m ruff check app tests
.venv/bin/python -m pytest \
  tests/test_information_edge_models.py \
  tests/test_investment_themes_api.py \
  tests/test_person_sources.py \
  tests/test_information_edge_backfill.py \
  tests/test_information_edge_scoring.py \
  tests/test_source_trace_service.py \
  tests/test_information_edge_digest.py \
  tests/test_investment_signals.py \
  tests/test_investment_api.py \
  -q
```

Expected: all pass.

- [ ] **Step 2: Run frontend verification**

Run:

```bash
cd frontend
npm run test -- InformationEdgePage.test.tsx InvestmentThemesPage.test.tsx InvestmentDashboardPage.test.tsx InvestmentDigestPage.test.tsx --run
npm run lint
npm run build
```

Expected: tests/lint/build pass.

- [ ] **Step 3: Sync code to remote**

Run from local:

```bash
SSHPASS='1235' sshpass -e rsync -az --stats \
  --exclude='.git/' \
  --exclude='.env' \
  --exclude='.env.*' \
  --exclude='.DS_Store' \
  --exclude='node_modules/' \
  --exclude='frontend/node_modules/' \
  --exclude='frontend/dist/' \
  --exclude='backend/.venv/' \
  --exclude='backend/.pytest_cache/' \
  --exclude='backend/.ruff_cache/' \
  --exclude='backend/.mypy_cache/' \
  --exclude='backend/knowpilot.db' \
  --exclude='backend/knowpilot.db-*' \
  --exclude='backend/storage/' \
  --exclude='tools/x-collector/node_modules/' \
  -e 'ssh -o StrictHostKeyChecking=no -p 12222' \
  /Users/domi/ZCodeProject/my_knowlage/ \
  yi5an@123.57.165.38:/home/yi5an/knowpilot/
```

Build and sync frontend dist:

```bash
cd frontend
npm run build
cd ..
SSHPASS='1235' sshpass -e rsync -az --delete \
  -e 'ssh -o StrictHostKeyChecking=no -p 12222' \
  /Users/domi/ZCodeProject/my_knowlage/frontend/dist/ \
  yi5an@123.57.165.38:/home/yi5an/knowpilot/frontend/dist/
```

- [ ] **Step 4: Rebuild/restart remote hotfix images**

Run:

```bash
SSHPASS='1235' sshpass -e ssh -o StrictHostKeyChecking=no -p 12222 yi5an@123.57.165.38 '
cd ~/knowpilot &&
docker build -f backend/Dockerfile.hotfix -t knowpilot-backend:latest ./backend &&
docker build -f frontend/Dockerfile.hotfix -t knowpilot-frontend:latest ./frontend &&
docker compose -f docker-compose.prod.yml up -d --no-build --force-recreate backend frontend
'
```

- [ ] **Step 5: Run remote migration and backfill**

Run:

```bash
SSHPASS='1235' sshpass -e ssh -o StrictHostKeyChecking=no -p 12222 yi5an@123.57.165.38 '
cd ~/knowpilot &&
docker exec knowpilot-backend alembic upgrade head &&
docker exec knowpilot-backend python -m scripts.backfill_information_edge_layers --workspace-id ws_default
'
```

Expected: migration succeeds; backfill prints `items_seen` and `items_changed`.

- [ ] **Step 6: Verify remote endpoints**

Run:

```bash
curl -fsS http://123.57.165.38:13080/api/v1/health
curl -fsS "http://123.57.165.38:13080/api/v1/investment/themes?workspace_id=ws_default"
curl -fsS "http://123.57.165.38:13080/api/v1/investment/information-edge?workspace_id=ws_default"
curl -fsSI http://123.57.165.38:13080/investment/edge
```

Expected:
- health returns `{"status":"ok"}`;
- themes endpoint returns JSON array;
- information-edge endpoint returns `generated_at`, `top_signals`, `source_traces`;
- frontend route returns HTTP 200.

- [ ] **Step 7: Commit deployment docs if changed**

If `README.md` or docs changed:

```bash
git add README.md docs/development/local-dev-guide.md
git commit -m "docs: document information edge operations"
```

---

## Self-Review

- Spec coverage: This plan implements topic boundaries, first-hand source hierarchy, human source pool, layered ingestion, weak-signal lifecycle, source tracing, information-edge scoring, and digest/UI outlets.
- Placeholder scan: No `TBD`, `TODO`, or vague "implement later" steps remain.
- Type consistency: Backend enums map to frontend string unions; `InvestmentSignal` lifecycle fields are added in model, schema, service, and UI; source trace fields match ORM and API response.
- Scope check: Market feedback is modeled and exposed as storage, but automated market-data ingestion is intentionally left to the next connector task because the user has not selected a market data provider. The scoring field `market_has_reacted` defaults false until market feedback rows exist.

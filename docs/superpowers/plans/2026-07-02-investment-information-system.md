# 投资信息系统 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 KnowPilot 内新增 `investment` 模块，覆盖真实数据源接入（SEC/Fed/RSS/BLS/FRED/HKEX/CNINFO）、投资语义数据模型、异步抓取去重入库、YouTube 观点层集成、GLM-5.2 分类与观点验证、以及投资工作台前端，实现 spec（`docs/superpowers/specs/2026-07-02-investment-information-system-design.md`）的全部能力。

**Architecture:** 后端新增 `services/investment/` 子包（对齐 `services/youtube/` 模式）；ORM 模型集中进 `infrastructure/models.py`；**抓取任务复用现有 `TaskJob` worker**（`job_type="investment_fetch"` + handler），不新建调度子系统；`investment_fetch_job` 是 `TaskJob` 的视图。LLM 分类/验证复用 `StructuredOutputClient` + `WebSearchClient`。前端 `services/investmentApi.ts`（对象字面量风格）+ 8 个页面 + 5 个组件，数据获取用 `useEffect`+`useState`，抓取通过 `POST /sources/{id}/poll`（异步 enqueue）+ 前端轮询 `GET /jobs/{id}`。

**Tech Stack:** FastAPI, SQLAlchemy 2 (Mapped), Alembic, Pydantic v2, httpx, feedparser, React 18, Vite, TypeScript, Ant Design 5, react-router-dom v7, Vitest.

**Branch:** `feat/investment-information-system`（单分支，按 10 个 Task 分阶段 commit）

---

## File Structure

**新建（后端）：**
- `backend/app/services/investment/__init__.py` — 子包入口
- `backend/app/services/investment/fetchers.py` — `InvestmentFetcher` Protocol、`InvestmentRawItem`、`SourceConfigError`、各 fetcher（Rss/SecEdgar/FederalReserveRss/Bls/Fred/Hkex/Cninfo）
- `backend/app/services/investment/normalizers.py` — dedupe_key 计算
- `backend/app/services/investment/repositories.py` — source/item/job upsert + dedupe
- `backend/app/services/investment/service.py` — `InvestmentService`（API 层调用）
- `backend/app/services/investment/fetch_job_handler.py` — `InvestmentFetchJobHandler`（注册到 task_worker）
- `backend/app/services/investment/scheduler.py` — 到期 source 入队的 `IntervalScheduler` 构建
- `backend/app/services/investment/classifier.py` — GLM-5.2 分类（写 suggested_*）
- `backend/app/services/investment/claim_verifier.py` — 观点验证（本地 RAG + 可选 Tavily）
- `backend/app/services/investment/investment_dependencies.py` — FastAPI Depends 工厂
- `backend/app/schemas/investment.py` — Pydantic schemas
- `backend/app/api/v1/investment.py` — API router
- `backend/alembic/versions/202607020001_investment_information_system.py` — 迁移
- `backend/tests/test_investment_models.py`
- `backend/tests/test_investment_api.py`
- `backend/tests/test_investment_fetchers_rss.py`
- `backend/tests/test_investment_fetchers_sec.py`
- `backend/tests/test_investment_fetchers_macro.py`
- `backend/tests/test_investment_fetchers_hk_cn.py`
- `backend/tests/test_investment_fetch_service.py`
- `backend/tests/test_investment_classifier.py`
- `backend/tests/test_investment_claim_verifier.py`

**修改（后端）：**
- `backend/app/infrastructure/models.py` — 追加 6 个 investment 模型
- `backend/app/core/config.py` — 追加 investment 配置字段
- `backend/app/api/v1/router.py` — 注册 investment router
- `backend/app/services/task_worker.py` — 注册 `investment_fetch` handler
- `backend/app/main.py` — 启动 investment scheduler
- `backend/app/services/youtube/orchestrator.py` — 成功后创建 opinion investment_item
- `backend/pyproject.toml` — 加 httpx（上移到生产）、feedparser（生产）

**新建（前端）：**
- `frontend/src/services/investmentApi.ts`
- `frontend/src/pages/InvestmentDashboardPage.tsx`
- `frontend/src/pages/InvestmentWatchlistPage.tsx`
- `frontend/src/pages/InvestmentItemsPage.tsx`
- `frontend/src/pages/InvestmentClaimsPage.tsx`
- `frontend/src/pages/InvestmentThesesPage.tsx`
- `frontend/src/pages/InvestmentSourcesPage.tsx`
- `frontend/src/pages/InvestmentCalendarPage.tsx`（stub）
- `frontend/src/pages/InvestmentDigestPage.tsx`（stub）
- `frontend/src/components/investment/InfoLayerTag.tsx`
- `frontend/src/components/investment/ImpactTag.tsx`
- `frontend/src/components/investment/ReviewStatusTag.tsx`
- `frontend/src/components/investment/InvestmentItemDrawer.tsx`
- `frontend/src/components/investment/WatchlistSelector.tsx`
- `frontend/src/pages/InvestmentDashboardPage.test.tsx`
- `frontend/src/pages/InvestmentItemsPage.test.tsx`
- `frontend/src/pages/InvestmentSourcesPage.test.tsx`

**修改（前端）：**
- `frontend/src/App.tsx` — nav + routes

**配置：**
- `.env.example` — 追加 investment 配置项（引用不赋值）

---

## Task 1: 后端 ORM 模型 + Alembic 迁移 + 模型测试

**Files:**
- Modify: `backend/app/infrastructure/models.py`（追加 6 个模型，紧跟 `Video` 之后）
- Create: `backend/alembic/versions/202607020001_investment_information_system.py`
- Test: `backend/tests/test_investment_models.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_investment_models.py`：

```python
from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base
from app.infrastructure.models import (
    InvestmentClaim,
    InvestmentItem,
    InvestmentSource,
    InvestmentThesis,
    InvestmentWatchlist,
    MacroEvent,
    Workspace,
)


@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=eng)
    return eng


@pytest.fixture()
def session(engine) -> Generator[Session, None, None]:
    sm = sessionmaker(bind=engine, expire_on_commit=False)
    with sm() as s:
        yield s


def _seed_workspace(session: Session) -> str:
    session.add(Workspace(id="ws_test", name="Test"))
    session.commit()
    return "ws_test"


def test_create_watchlist(session):
    ws = _seed_workspace(session)
    wl = InvestmentWatchlist(id="wl_1", workspace_id=ws, name="Apple", watch_type="stock", ticker="AAPL")
    session.add(wl)
    session.commit()
    got = session.get(InvestmentWatchlist, "wl_1")
    assert got is not None
    assert got.name == "Apple"
    assert got.enabled is True


def test_create_source(session):
    ws = _seed_workspace(session)
    src = InvestmentSource(
        id="src_1", workspace_id=ws, source_type="rss", name="Fed RSS",
        url="https://www.federalreserve.gov/feeds/press_monetary.xml",
        default_info_layer="macro_calendar",
    )
    session.add(src)
    session.commit()
    got = session.get(InvestmentSource, "src_1")
    assert got is not None
    assert got.next_poll_at is None  # nullable
    assert got.enabled is True


def test_create_item(session):
    ws = _seed_workspace(session)
    item = InvestmentItem(
        id="inv_1", workspace_id=ws, title="10-K",
        info_layer="primary_source", source_credibility="official",
        importance="medium", impact_direction="neutral", impact_horizon="unknown",
        thesis_impact="unknown", action_status="pending_review",
        dedupe_key="dk_1",
    )
    session.add(item)
    session.commit()
    got = session.get(InvestmentItem, "inv_1")
    assert got is not None
    assert got.info_layer == "primary_source"


def test_item_dedupe_key_unique_per_workspace(session):
    ws = _seed_workspace(session)
    session.add(InvestmentItem(
        id="inv_a", workspace_id=ws, title="A",
        info_layer="news", source_credibility="reliable_media",
        importance="low", impact_direction="neutral", impact_horizon="unknown",
        thesis_impact="unknown", action_status="pending_review",
        dedupe_key="dk_dup",
    ))
    session.commit()
    session.add(InvestmentItem(
        id="inv_b", workspace_id=ws, title="B",
        info_layer="news", source_credibility="reliable_media",
        importance="low", impact_direction="neutral", impact_horizon="unknown",
        thesis_impact="unknown", action_status="pending_review",
        dedupe_key="dk_dup",
    ))
    with pytest.raises(IntegrityError):
        session.commit()


def test_create_claim_and_thesis(session):
    ws = _seed_workspace(session)
    session.add(InvestmentWatchlist(id="wl_1", workspace_id=ws, name="T", watch_type="stock"))
    session.add(InvestmentThesis(
        id="th_1", workspace_id=ws, watchlist_id="wl_1", title="thesis",
        status="open", confidence="medium",
    ))
    session.add(InvestmentClaim(
        id="cl_1", workspace_id=ws, watchlist_id="wl_1", thesis_id="th_1",
        claim_text="x", verification_status="pending",
    ))
    session.commit()
    assert session.get(InvestmentThesis, "th_1") is not None
    assert session.get(InvestmentClaim, "cl_1") is not None


def test_create_macro_event(session):
    ws = _seed_workspace(session)
    session.add(MacroEvent(
        id="me_1", workspace_id=ws, title="CPI",
        source_name="BLS", importance="high",
    ))
    session.commit()
    assert session.get(MacroEvent, "me_1") is not None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_investment_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'InvestmentWatchlist'`

- [ ] **Step 3: 追加 ORM 模型**

在 `backend/app/infrastructure/models.py` 末尾追加（紧跟 `Video` 类之后）：

```python
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
    """A single investment information entry — the main feed table."""

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
    importance: Mapped[str] = mapped_column(String(32), default="medium", server_default="medium")
    impact_direction: Mapped[str] = mapped_column(
        String(32), default="neutral", server_default="neutral"
    )
    impact_horizon: Mapped[str] = mapped_column(String(32), default="unknown", server_default="unknown")
    thesis_impact: Mapped[str] = mapped_column(String(32), default="unknown", server_default="unknown")
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
    __table_args__ = (
        Index("idx_investment_thesis_watchlist", "workspace_id", "watchlist_id"),
    )

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
```

- [ ] **Step 4: 运行模型测试确认通过**

Run: `cd backend && python -m pytest tests/test_investment_models.py -v`
Expected: PASS（6 passed）

- [ ] **Step 5: 写 Alembic 迁移**

创建 `backend/alembic/versions/202607020001_investment_information_system.py`：

```python
"""investment information system

Revision ID: 202607020001
Revises: 202606230001
Create Date: 2026-07-02
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.types import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import Text

# revision identifiers, used by Alembic.
revision = "202607020001"
down_revision = "202606230001"
branch_labels = None
depends_on = None

JsonType = JSON().with_variant(JSONB(astext_type=Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "investment_watchlist",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("workspace_id", sa.String(length=64), sa.ForeignKey("workspace.id"), nullable=False),
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
        sa.Column("workspace_id", sa.String(length=64), sa.ForeignKey("workspace.id"), nullable=False),
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
        sa.Column("workspace_id", sa.String(length=64), sa.ForeignKey("workspace.id"), nullable=False),
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
        sa.Column("workspace_id", sa.String(length=64), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("watchlist_id", sa.String(length=64), sa.ForeignKey("investment_watchlist.id")),
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
        sa.Column("workspace_id", sa.String(length=64), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("source_item_id", sa.String(length=64), sa.ForeignKey("investment_item.id")),
        sa.Column("watchlist_id", sa.String(length=64), sa.ForeignKey("investment_watchlist.id")),
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
        sa.Column("workspace_id", sa.String(length=64), sa.ForeignKey("workspace.id"), nullable=False),
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
```

- [ ] **Step 6: 应用迁移并跑全套测试确认无回归**

Run: `cd backend && alembic upgrade head && python -m pytest -q`
Expected: alembic 输出 `Running upgrade 202606230001 -> 202607020001`；全部测试 PASS。

- [ ] **Step 7: lint / type check**

Run: `cd backend && ruff check . && mypy app`
Expected: 无新增错误。

- [ ] **Step 8: Commit**

```bash
git add backend/app/infrastructure/models.py backend/alembic/versions/202607020001_investment_information_system.py backend/tests/test_investment_models.py
git commit -m "feat(investment): 投资信息 ORM 模型 + Alembic 迁移 + 模型测试"
```

---

## Task 2: Pydantic Schemas + API 骨架 + API 测试

（后端 schema/router 注册、dashboard 真实统计、`/sources/{id}/poll` enqueue、`GET /jobs/{id}`。先写 API 测试，再实现 schema + router + 最小 service stub。每端点配独立测试。完整代码见 spec §3。）

**Files:**
- Create: `backend/app/schemas/investment.py`
- Create: `backend/app/api/v1/investment.py`
- Create: `backend/app/services/investment/__init__.py`
- Create: `backend/app/services/investment/service.py`（CRUD + poll_source 入队 + dashboard）
- Create: `backend/app/services/investment/investment_dependencies.py`
- Modify: `backend/app/api/v1/router.py`
- Test: `backend/tests/test_investment_api.py`

- [ ] 写 API 测试（TestClient + override get_db_session/get_investment_service）覆盖 watchlist/items CRUD、dashboard 真实统计、poll 创建 pending TaskJob、GET /jobs/{id} 投影。
- [ ] 实现 `schemas/investment.py`：`StrEnum` + 全部 `*Create/*Update/*Response` + `InvestmentDashboardResponse` + `InvestmentFetchJobResponse`。
- [ ] 实现 `service.py`：`InvestmentService(session)`，CRUD 直接走 ORM；`dashboard()` 真实 count；`poll_source()` 创建 `TaskJob(job_type="investment_fetch")`；`get_job(job_id)` 投影为 `InvestmentFetchJobResponse`。
- [ ] 实现 `api/v1/investment.py`：文档 §12 全部端点 + `/sources/{id}/poll` + `/jobs/{id}`。
- [ ] 注册 router，跑 `pytest tests/test_investment_api.py -v`，ruff/mypy，commit。

---

## Task 3: P0 Fetchers（RSS / SEC / FederalReserve）+ 依赖 + 测试

**Files:**
- Modify: `backend/pyproject.toml`（httpx 上移到生产、加 feedparser）
- Modify: `backend/app/core/config.py`（spec §4.2 配置字段）
- Modify: `.env.example`
- Create: `backend/app/services/investment/fetchers.py`
- Create: `backend/app/services/investment/normalizers.py`
- Test: `backend/tests/test_investment_fetchers_rss.py`
- Test: `backend/tests/test_investment_fetchers_sec.py`

- [ ] 加依赖、配置项。
- [ ] 实现 `fetchers.py`：`InvestmentFetcher` Protocol、`InvestmentRawItem`、`SourceConfigError`、`RssFetcher`（httpx+feedparser）、`SecEdgarFetcher`（缺 UA 抛 SourceConfigError、构造 source_url、过滤 forms）、`FederalReserveRssFetcher`（复用 RSS）。
- [ ] 实现 `normalizers.py`：`compute_dedupe_key(source_type, external_id, url)`。
- [ ] 测试用本地 fixture 响应，不触网。SEC 缺 UA 抛 SourceConfigError。跑测试 + ruff/mypy + commit。

---

## Task 4: 抓取 Service（async handler + repository）+ 测试

**Files:**
- Create: `backend/app/services/investment/repositories.py`
- Modify: `backend/app/services/investment/service.py`（补 poll_source 实现链路）
- Create: `backend/app/services/investment/fetch_job_handler.py`
- Modify: `backend/app/services/task_worker.py`（注册 `investment_fetch` handler）
- Create: `backend/app/services/investment/scheduler.py`
- Modify: `backend/app/main.py`（启动 scheduler）
- Test: `backend/tests/test_investment_fetch_service.py`

- [ ] 实现 repositories：source/item/document upsert + dedupe（按 `(workspace_id, dedupe_key)` 幂等）。
- [ ] 实现 `InvestmentFetchJobHandler.handle()`：选 fetcher → fetch → normalize → dedupe → upsert Document + InvestmentItem → 写 `TaskJob.output` → 更新 source stats。失败 raise 由 processor 记 failed。
- [ ] 注册到 `task_worker._HANDLERS["investment_fetch"]`。
- [ ] 实现 scheduler：`IntervalScheduler` 周期扫描到期 source 入队（无重复 running/pending job）。
- [ ] 测试：fake fetcher 注入；重复抓取幂等；失败记 failed + last_error；成功 items_created 正确。commit。

---

## Task 5: YouTube → opinion 集成 + 测试

**Files:**
- Modify: `backend/app/services/youtube/orchestrator.py`
- Modify: `backend/tests/test_youtube_orchestrator.py`

- [ ] orchestrator 成功 persist Document 后调 `investment_service.create_item_from_document(info_layer="opinion", ...)`；捕获异常仅 warning，不影响总结；dedupe 防重复。
- [ ] 测试覆盖：成功生成 opinion item；重复不重建；investment 失败不影响总结。commit。

---

## Task 6: 前端第一阶段（dashboard / watchlist / items / claims / theses + 组件）

**Files:**
- Create: `frontend/src/services/investmentApi.ts`
- Create: `frontend/src/components/investment/{InfoLayerTag,ImpactTag,ReviewStatusTag,InvestmentItemDrawer,WatchlistSelector}.tsx`
- Create: `frontend/src/pages/Investment{Dashboard,Watchlist,Items,Claims,Theses}Page.tsx`
- Create: `frontend/src/pages/Investment{Calendar,Digest}Page.tsx`（stub）
- Modify: `frontend/src/App.tsx`
- Test: `frontend/src/pages/InvestmentDashboardPage.test.tsx`, `InvestmentItemsPage.test.tsx`

- [ ] investmentApi.ts：对象字面量 + inline types + `workspaceId="ws_default"` + `apiRequest`。
- [ ] App.tsx：加 `FundProjectionScreenOutlined` nav + 8 routes。
- [ ] 5 个页面 + 5 个组件（Table/Drawer 用 AntD v5 标准用法）。
- [ ] 测试：空状态真实提示、API 错误显示、筛选层级参数正确。`npm run lint && npm run test && npm run build`。commit。

---

## Task 7: 前端 SourcesPage + poll 端点对接 + job 轮询

**Files:**
- Modify: `frontend/src/services/investmentApi.ts`（加 `pollSource`、`getFetchJob`）
- Create: `frontend/src/pages/InvestmentSourcesPage.tsx`
- Modify: `frontend/src/App.tsx`
- Test: `frontend/src/pages/InvestmentSourcesPage.test.tsx`

- [ ] SourcesPage：source 表（类型/频率/上次/下次/错误/启用）+ 新增/编辑表单（rss/sec_edgar/federal_reserve_rss）+ "立即抓取" → `pollSource(id)` → `setInterval` 轮询 `getFetchJob` 直到 succeeded/failed → 刷新。
- [ ] 测试：点立即抓取调用 pollSource；错误显示。commit。

---

## Task 8: BLS / FRED / HKEX / CNINFO Fetcher + 测试

**Files:**
- Modify: `backend/app/services/investment/fetchers.py`
- Modify: `backend/app/api/v1/investment.py` + SourcesPage 表单（加类型）
- Test: `backend/tests/test_investment_fetchers_macro.py`, `test_investment_fetchers_hk_cn.py`

- [ ] `BlsFetcher`（无 key 仍请求公开 API）、`FredFetcher`（缺 key 抛 SourceConfigError）、`HkexFetcher`（用户保存搜索 URL 解析）、`CninfoFetcher`（手动 URL/PDF + 授权 API）。
- [ ] 测试：FRED 缺 key 抛错；BLS 无 key 走公开；HKEX/CNINFO 解析失败落 job error 不造假 item。commit。

---

## Task 9: GLM-5.2 分类 + 观点验证 + 测试

**Files:**
- Create: `backend/app/services/investment/classifier.py`
- Create: `backend/app/services/investment/claim_verifier.py`
- Modify: `backend/app/schemas/investment.py`（`InvestmentClassificationSchema`）
- Modify: fetch handler（抓取后 enqueue 分类）+ API（`POST /claims/{id}/verify`）
- Test: `backend/tests/test_investment_classifier.py`, `test_investment_claim_verifier.py`

- [ ] classifier：复用 `StructuredOutputClient`；系统规则同 spec §6.1；仅写 suggested_*，不覆盖用户确认字段。
- [ ] claim_verifier：本地 Document/InvestmentItem 搜索 → 可选 Tavily → 写 evidence_doc_ids；无 Tavily 标 `local_only`。
- [ ] 测试：观点层不被分类 official；无买卖建议；结果带 evidence_doc_ids。commit。

---

## Task 10: 最终验证

- [ ] 后端：`cd backend && alembic upgrade head && pytest && ruff check . && mypy app`
- [ ] 前端：`cd frontend && npm run lint && npm run test && npm run build`
- [ ] 手动验证（spec §0 交付标准）：SEC source（Apple CIK 0000320193）→ 立即抓取 → 真实 filing；Fed RSS source → 真实条目；YouTube 总结 → opinion item。无 mock、可追溯 source_url。

---

## Self-Review（写完计划后）

- **Spec 覆盖**：spec §1–§7 各节均有对应 Task。§1.2 并入 TaskJob → Task 1（无独立表）+ Task 4（handler）。§2 模型/迁移 → Task 1。§3 schema/API → Task 2。§4 fetcher/配置 → Task 3 + Task 8。§5 service → Task 4。§6 classifier/verifier/YouTube → Task 9 + Task 5。§7 前端 → Task 6/7。✅
- **Placeholder 扫描**：Task 2–9 为高层任务描述（spec 已含完整契约）。Task 1 是完整 TDD 详细步骤，作为后续任务的样板。✅
- **类型一致性**：`InvestmentService`、`InvestmentItem`、`dedupe_key`、`job_type="investment_fetch"` 在各 Task 间一致。✅
```

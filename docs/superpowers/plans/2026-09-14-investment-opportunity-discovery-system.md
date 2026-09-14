# Investment Opportunity Discovery System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 KnowPilot 从投资情报聚合器升级为可复盘的投资机会发现系统：区分情报、信号和机会候选，严谨统计 X 人物发言后的市场反应，推荐值得关注的 X/YouTube/机构账号，并把用户反馈用于后续排序校准。

**Architecture:** 继续复用现有 FastAPI modular monolith、`InvestmentItem/Fact/Signal/Claim/Thesis` 和 `TaskJob` worker，不新建平行投资系统。新增的机会候选、人物影响、账号推荐、市场数据和复盘结果都以 workspace 为边界，通过 Pydantic schema、SQLAlchemy model、service、API、React 页面逐层连接。所有长任务复用 `TaskJob`；市场数据必须通过可替换的 provider abstraction 获取真实数据，测试只注入 fake provider。

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic, existing `TaskJob` worker, `httpx`, React 18, TypeScript, Vite, Ant Design 5, Vitest, existing X web collector and Tavily web-search abstraction.

---

## 0. 文件边界与模块责任

先按下表锁定所有权，避免多个任务同时修改同一职责：

| 模块 | 负责 | 不负责 |
| --- | --- | --- |
| `backend/app/schemas/investment.py` | 所有新增 API enum、request、response 契约 | ORM、排序实现 |
| `backend/app/infrastructure/models.py` | 机会候选、人物影响、推荐、复盘和用户上下文持久化 | 市场计算、LLM 提示词 |
| `backend/app/services/investment/market_data.py` | `MarketDataProvider`、真实 provider、数据质量与交易日规范 | 机会排序、页面格式化 |
| `backend/app/services/investment/event_study.py` | 事件窗口、异常收益、成交量和窗口重叠计算 | 抓取账号、写 UI |
| `backend/app/services/investment/opportunity.py` | 信号升级门槛、机会候选生命周期、机会排序字段 | 原始采集 |
| `backend/app/services/investment/account_recommendation.py` | 候选发现、推荐理由、关注幂等、推荐结果 | 股票收益计算 |
| `backend/app/services/investment/person_impact.py` | 人物事件生成、profile 聚合、事件研究任务 | 账号推荐文案 |
| `backend/app/services/investment/service.py` | 现有投资 CRUD 与新 service 的 API 编排 | provider 具体实现 |
| `backend/app/api/v1/investment.py` | 路由、参数、response model | 业务计算 |
| `frontend/src/pages/*` | 页面、空/错/加载状态和用户动作 | 直接计算市场指标 |
| `frontend/src/services/investmentApi.ts` | 前端类型和 HTTP client | 页面布局 |

禁止在同一任务中同时修改 `service.py`、`models.py`、`investment.py` schema 的无关部分；每次提交只完成一个垂直切片。

## 1. Task 1 — 冻结领域契约与测试夹具

**Purpose:** 在任何实现前定义“机会候选”和“人物影响”最小契约，确保后续模型、API、前端字段一致。

**Files:**

- Modify: `backend/app/schemas/investment.py`
- Add: `backend/tests/test_investment_opportunity_schemas.py`
- Add: `backend/tests/fixtures/market_bars.py`
- Modify: `frontend/src/services/investmentApi.ts`
- Test: `frontend/src/services/investmentApi.test.ts`

- [ ] **Step 1: Write failing schema tests**

```python
import pytest

def test_opportunity_candidate_requires_research_fields() -> None:
    from pydantic import ValidationError
    from app.schemas.investment import OpportunityCandidateCreate

    with pytest.raises(ValidationError):
        OpportunityCandidateCreate(
            workspace_id="ws_default",
            title="AI server demand",
            asset_symbols=["NVDA"],
            opportunity_type="earnings_inflection",
        )


def test_person_impact_event_exposes_windows_and_data_quality() -> None:
    from app.schemas.investment import PersonImpactEventResponse

    event = PersonImpactEventResponse(
        id="pie_1",
        workspace_id="ws_default",
        person_source_id="person_1",
        source_item_id="inv_1",
        symbol="TSLA",
        benchmark_symbol="XLY",
        event_at="2026-09-12T20:00:00Z",
        event_cluster_id="cluster_1",
        window_overlap=False,
        event_status="computed",
        data_quality="complete",
        windows={"1d": {"excess_return": 0.028}},
        concurrent_events=[],
        confidence=0.81,
    )
    assert event.windows["1d"]["excess_return"] == 0.028
```

Run: `cd backend && pytest tests/test_investment_opportunity_schemas.py -q`

Expected: FAIL because the new enums and models do not exist.

- [ ] **Step 2: Add exact enums and Pydantic models**

Add these values to `backend/app/schemas/investment.py`:

```python
from pydantic import model_validator


class OpportunityStatus(StrEnum):
    NEW = "new"
    RESEARCHING = "researching"
    WAITING_FOR_EVIDENCE = "waiting_for_evidence"
    VALIDATED = "validated"
    INVALIDATED = "invalidated"
    PARKED = "parked"


class OpportunityType(StrEnum):
    CATALYST = "catalyst"
    EARNINGS_INFLECTION = "earnings_inflection"
    SUPPLY_DEMAND = "supply_demand"
    POLICY_CHANGE = "policy_change"
    COMPETITIVE_SHIFT = "competitive_shift"
    SENTIMENT_DISLOCATION = "sentiment_dislocation"
    VALUATION_REPRICING = "valuation_repricing"
    OTHER = "other"


class RecommendationStatus(StrEnum):
    NEW = "new"
    FOLLOWED = "followed"
    DISMISSED = "dismissed"
    EXPIRED = "expired"


class PersonImpactEventStatus(StrEnum):
    PENDING = "pending"
    COMPUTED = "computed"
    INSUFFICIENT_DATA = "insufficient_data"
    EXCLUDED = "excluded"


class MarketDataQuality(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    MISSING = "missing"
    STALE = "stale"
    INVALID = "invalid"


class OpportunityCandidateCreate(BaseModel):
    workspace_id: str = "ws_default"
    signal_id: str | None = None
    title: str = Field(min_length=1, max_length=500)
    asset_symbols: list[str] = Field(min_length=1)
    theme_id: str | None = None
    watchlist_id: str | None = None
    opportunity_type: OpportunityType = OpportunityType.OTHER
    change_summary: str = Field(min_length=1)
    expected_case: str = Field(min_length=1)
    market_case: str = Field(min_length=1)
    impact_path: str = Field(min_length=1)
    catalyst: str = Field(min_length=1)
    time_window_start: datetime | None = None
    time_window_end: datetime | None = None
    risk_flags: list[str] = Field(min_length=1)
    invalidation_conditions: list[str] = Field(min_length=1)
    next_action: str = Field(min_length=1)
    evidence_refs: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_time_window(self) -> "OpportunityCandidateCreate":
        if self.time_window_start and self.time_window_end and self.time_window_start > self.time_window_end:
            raise ValueError("time_window_start must be before time_window_end")
        return self


class OpportunityCandidateResponse(OpportunityCandidateCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: OpportunityStatus
    priority: str
    market_reaction_state: str
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    outcome: dict[str, object] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class OpportunityReviewAction(BaseModel):
    status: OpportunityStatus
    note: str | None = None


class OpportunityPromotionResult(BaseModel):
    created: bool
    reason: str | None = None
    opportunity: OpportunityCandidateResponse | None = None


class PersonImpactEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    person_source_id: str
    source_item_id: str
    symbol: str
    benchmark_symbol: str
    event_at: datetime
    event_cluster_id: str
    window_overlap: bool
    event_status: PersonImpactEventStatus
    data_quality: MarketDataQuality
    windows: dict[str, dict[str, float | str | None]]
    concurrent_events: list[str] = Field(default_factory=list)
    exclusion_reason: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    created_at: datetime | None = None


class PersonImpactProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    person_source_id: str
    sample_count: int
    valid_sample_count: int
    excluded_sample_count: int
    sample_sufficient: bool
    positive_event_count: int
    negative_event_count: int
    neutral_event_count: int
    hit_rate: float | None = None
    average_lead_time_hours: float | None = None
    average_excess_return_1d: float | None = None
    stability_score: float | None = None
    uncertainty: str


class AccountRecommendationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    platform: str
    handle: str
    display_name: str | None = None
    role_type: str
    theme_ids: list[str] = Field(default_factory=list)
    recommendation_label: str
    reason: str
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    sample_count: int
    evidence_count: int
    status: RecommendationStatus
    source_id: str | None = None


class FollowRecommendationRequest(BaseModel):
    theme_ids: list[str] = Field(default_factory=list)
    poll_interval_seconds: int = Field(default=900, ge=300, le=86400)


class UserInvestmentContextResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    workspace_id: str
    markets: list[str] = Field(default_factory=list)
    horizons: list[str] = Field(default_factory=list)
    focus_theme_ids: list[str] = Field(default_factory=list)
    min_liquidity: str = "any"
    excluded_watchlist_ids: list[str] = Field(default_factory=list)
    exposure_notes: str | None = None


class UserInvestmentContextUpdate(BaseModel):
    markets: list[str] = Field(default_factory=list)
    horizons: list[str] = Field(default_factory=list)
    focus_theme_ids: list[str] = Field(default_factory=list)
    min_liquidity: str = "any"
    excluded_watchlist_ids: list[str] = Field(default_factory=list)
    exposure_notes: str | None = None


class RecommendationOutcomeCreate(BaseModel):
    workspace_id: str = "ws_default"
    recommendation_id: str | None = None
    opportunity_id: str | None = None
    adopted: bool
    outcome_status: str
    outcome_note: str | None = None
    observed_at: datetime

    @model_validator(mode="after")
    def validate_target(self) -> "RecommendationOutcomeCreate":
        if not self.recommendation_id and not self.opportunity_id:
            raise ValueError("recommendation_id or opportunity_id is required")
        return self


class RecommendationOutcomeResponse(RecommendationOutcomeCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime | None = None
```

Update `frontend/src/services/investmentApi.ts` with matching string unions and functions:

```ts
export async function listOpportunityCandidates(params?: { status?: string; limit?: number }) {}
export async function reviewOpportunityCandidate(id: string, payload: OpportunityReviewAction) {}
export async function listAccountRecommendations(params?: { platform?: string; themeId?: string }) {}
export async function followAccountRecommendation(id: string, payload: FollowRecommendationRequest) {}
export async function listPersonImpactEvents(personSourceId: string, limit = 50) {}
export async function getPersonImpactProfile(personSourceId: string) {}
export async function getUserInvestmentContext() {}
export async function updateUserInvestmentContext(payload: UserInvestmentContextUpdate) {}
export async function createRecommendationOutcome(payload: RecommendationOutcomeCreate) {}
```

Create the shared fixture helper in `backend/tests/fixtures/market_bars.py`:

```python
from datetime import date, timedelta

from app.services.investment.market_data import MarketBar


class FakeMarketDataProvider:
    def __init__(self, series: dict[str, list[MarketBar]]) -> None:
        self.series = series

    def daily_bars(self, symbol: str, start: date, end: date) -> list[MarketBar]:
        return [bar for bar in self.series.get(symbol, []) if start <= bar.trading_date <= end]


def bars(symbol: str, closes: list[float]) -> list[MarketBar]:
    return [
        MarketBar(symbol, date(2026, 9, 14) + timedelta(days=index), close, 1_000_000)
        for index, close in enumerate(closes)
    ]
```

- [ ] **Step 3: Run schema and TypeScript type tests**

Run: `cd backend && pytest tests/test_investment_opportunity_schemas.py -q`; then `cd frontend && npm run test -- investmentApi.test.ts`.

Expected: PASS after the contract definitions are present.

- [ ] **Step 4: Commit**

```bash
git add backend/app/schemas/investment.py backend/tests/test_investment_opportunity_schemas.py backend/tests/fixtures/market_bars.py frontend/src/services/investmentApi.ts frontend/src/services/investmentApi.test.ts
git commit -m "feat(investment): freeze opportunity and impact contracts"
```

## 2. Task 2 — ORM 模型与 Alembic 迁移

**Purpose:** 持久化机会候选、人物影响事件/profile、账号推荐、复盘和用户投资上下文，同时保持历史快照不可变。

**Files:**

- Modify: `backend/app/infrastructure/models.py`
- Add: `backend/alembic/versions/202609140001_investment_opportunity_discovery.py`
- Add: `backend/tests/test_investment_opportunity_models.py`

- [ ] **Step 1: Write failing persistence tests**

```python
from sqlalchemy.orm import Session

from app.infrastructure.models import OpportunityCandidate


def test_opportunity_and_impact_models_persist_without_overwriting_history(session: Session) -> None:
    opportunity = OpportunityCandidate(
        id="opp_1",
        workspace_id="ws_default",
        title="AI server demand",
        asset_symbols=["NVDA"],
        opportunity_type="earnings_inflection",
        change_summary="Multiple primary sources raised capex guidance.",
        expected_case="Consensus underestimates demand persistence.",
        market_case="Price has not moved relative to SOXX.",
        impact_path="Orders -> revenue -> earnings revisions.",
        catalyst="Next earnings call",
        risk_flags=["valuation", "macro slowdown"],
        invalidation_conditions=["Orders cancel for two consecutive months"],
        next_action="Verify supplier lead times",
        evidence_refs=["inv_1", "fact_1"],
        status="new",
        priority="research",
        market_reaction_state="unknown",
        confidence=0.72,
    )
    session.add(opportunity)
    session.commit()
    saved = session.get(OpportunityCandidate, "opp_1")
    assert saved is not None
    assert saved.asset_symbols == ["NVDA"]
```

Run: `cd backend && pytest tests/test_investment_opportunity_models.py -q`

Expected: FAIL because the tables and classes do not exist.

- [ ] **Step 2: Add model classes**

Add these SQLAlchemy models after the existing investment models in `backend/app/infrastructure/models.py`:

```python
class OpportunityCandidate(UpdatedTimestampMixin, Base):
    __tablename__ = "investment_opportunity_candidate"
    __table_args__ = (
        Index("idx_investment_opportunity_workspace_status", "workspace_id", "status"),
        Index("idx_investment_opportunity_priority", "workspace_id", "priority"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), nullable=False)
    signal_id: Mapped[str | None] = mapped_column(ForeignKey("investment_signal.id"))
    title: Mapped[str] = mapped_column(Text(), nullable=False)
    asset_symbols: Mapped[JsonArray] = mapped_column(JsonType, default=list)
    theme_id: Mapped[str | None] = mapped_column(ForeignKey("investment_theme.id"))
    watchlist_id: Mapped[str | None] = mapped_column(ForeignKey("investment_watchlist.id"))
    opportunity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    change_summary: Mapped[str] = mapped_column(Text(), nullable=False)
    expected_case: Mapped[str] = mapped_column(Text(), nullable=False)
    market_case: Mapped[str] = mapped_column(Text(), nullable=False)
    impact_path: Mapped[str] = mapped_column(Text(), nullable=False)
    catalyst: Mapped[str] = mapped_column(Text(), nullable=False)
    time_window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    time_window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    risk_flags: Mapped[JsonArray] = mapped_column(JsonType, default=list)
    invalidation_conditions: Mapped[JsonArray] = mapped_column(JsonType, default=list)
    next_action: Mapped[str] = mapped_column(Text(), nullable=False)
    evidence_refs: Mapped[JsonArray] = mapped_column(JsonType, default=list)
    status: Mapped[str] = mapped_column(String(32), default="new", server_default="new")
    priority: Mapped[str] = mapped_column(String(32), default="research", server_default="research")
    market_reaction_state: Mapped[str] = mapped_column(String(32), default="unknown", server_default="unknown")
    score_breakdown: Mapped[JsonObject] = mapped_column(JsonType, default=dict)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    outcome: Mapped[JsonObject] = mapped_column(JsonType, default=dict)


class PersonImpactEvent(UpdatedTimestampMixin, Base):
    __tablename__ = "investment_person_impact_event"
    __table_args__ = (
        Index("idx_person_impact_person_time", "workspace_id", "person_source_id", "event_at"),
        Index("idx_person_impact_symbol_time", "workspace_id", "symbol", "event_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), nullable=False)
    person_source_id: Mapped[str] = mapped_column(ForeignKey("investment_person_source.id"), nullable=False)
    source_item_id: Mapped[str] = mapped_column(ForeignKey("investment_item.id"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    benchmark_symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_cluster_id: Mapped[str] = mapped_column(String(64), nullable=False)
    window_overlap: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    event_status: Mapped[str] = mapped_column(String(32), default="pending", server_default="pending")
    data_quality: Mapped[str] = mapped_column(String(32), default="missing", server_default="missing")
    windows: Mapped[JsonObject] = mapped_column(JsonType, default=dict)
    concurrent_events: Mapped[JsonArray] = mapped_column(JsonType, default=list)
    exclusion_reason: Mapped[str | None] = mapped_column(Text())
    confidence: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")


class PersonImpactProfile(UpdatedTimestampMixin, Base):
    __tablename__ = "investment_person_impact_profile"
    __table_args__ = (UniqueConstraint("workspace_id", "person_source_id", name="uq_person_impact_profile"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), nullable=False)
    person_source_id: Mapped[str] = mapped_column(ForeignKey("investment_person_source.id"), nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    valid_sample_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    excluded_sample_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    positive_event_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    negative_event_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    neutral_event_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    hit_rate: Mapped[float | None] = mapped_column(Float)
    average_lead_time_hours: Mapped[float | None] = mapped_column(Float)
    average_excess_return_1d: Mapped[float | None] = mapped_column(Float)
    stability_score: Mapped[float | None] = mapped_column(Float)
    uncertainty: Mapped[str] = mapped_column(Text(), default="样本不足", server_default="样本不足")


class AccountRecommendation(UpdatedTimestampMixin, Base):
    __tablename__ = "investment_account_recommendation"
    __table_args__ = (Index("idx_account_recommendation_workspace_status", "workspace_id", "status"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    handle: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))
    role_type: Mapped[str] = mapped_column(String(64), default="other", server_default="other")
    theme_ids: Mapped[JsonArray] = mapped_column(JsonType, default=list)
    recommendation_label: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(Text(), nullable=False)
    score_breakdown: Mapped[JsonObject] = mapped_column(JsonType, default=dict)
    sample_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    evidence_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    status: Mapped[str] = mapped_column(String(32), default="new", server_default="new")
    source_id: Mapped[str | None] = mapped_column(ForeignKey("investment_source.id"))


class RecommendationOutcome(TimestampMixin, Base):
    __tablename__ = "investment_recommendation_outcome"
    __table_args__ = (Index("idx_recommendation_outcome_workspace_time", "workspace_id", "observed_at"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), nullable=False)
    recommendation_id: Mapped[str | None] = mapped_column(ForeignKey("investment_account_recommendation.id"))
    opportunity_id: Mapped[str | None] = mapped_column(ForeignKey("investment_opportunity_candidate.id"))
    adopted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    outcome_status: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome_note: Mapped[str | None] = mapped_column(Text())
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UserInvestmentContext(UpdatedTimestampMixin, Base):
    __tablename__ = "investment_user_context"
    __table_args__ = (UniqueConstraint("workspace_id", name="uq_investment_user_context_workspace"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), nullable=False)
    markets: Mapped[JsonArray] = mapped_column(JsonType, default=list)
    horizons: Mapped[JsonArray] = mapped_column(JsonType, default=list)
    focus_theme_ids: Mapped[JsonArray] = mapped_column(JsonType, default=list)
    min_liquidity: Mapped[str] = mapped_column(String(32), default="any", server_default="any")
    excluded_watchlist_ids: Mapped[JsonArray] = mapped_column(JsonType, default=list)
    exposure_notes: Mapped[str | None] = mapped_column(Text())
```

- [ ] **Step 3: Add migration `202609140001_investment_opportunity_discovery.py`**

Set `revision = "202609140001"`, `down_revision = "202609030002"`. Create the six tables listed in this task with the exact indexes and unique constraints. The downgrade must drop indexes and tables in reverse dependency order. Do not alter or delete existing investment rows.

- [ ] **Step 4: Run SQLite model and migration checks**

Run: `cd backend && pytest tests/test_investment_opportunity_models.py tests/test_information_edge_models.py -q`.

Expected: PASS; existing information-edge model tests remain green.

- [ ] **Step 5: Commit**

```bash
git add backend/app/infrastructure/models.py backend/alembic/versions/202609140001_investment_opportunity_discovery.py backend/tests/test_investment_opportunity_models.py
git commit -m "feat(investment): persist opportunities impact profiles and recommendations"
```

## 3. Task 3 — 真实市场数据 provider 与事件研究计算

**Purpose:** 先建立可测试、可替换、不会把 mock 接入生产的市场数据底座，再计算人物发言后的收益和成交量反应。

**Files:**

- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example`
- Add: `backend/app/services/investment/market_data.py`
- Add: `backend/app/services/investment/event_study.py`
- Add: `backend/tests/test_market_data.py`
- Add: `backend/tests/test_person_impact_event_study.py`

- [ ] **Step 1: Write failing provider and event-study tests**

```python
from datetime import date, datetime
from datetime import UTC

import pytest

from app.services.investment.event_study import compute_event_windows, events_overlap
from tests.fixtures.market_bars import bars

def test_event_study_uses_next_trading_day_and_adjusted_close() -> None:
    result = compute_event_windows(
        event_at=datetime(2026, 9, 12, 20, tzinfo=UTC),
        asset_bars=bars("TSLA", [100, 103, 105, 106, 107]),
        benchmark_bars=bars("XLY", [200, 202, 203, 204, 205]),
        event_cluster_id="cluster_1",
    )
    assert result.data_quality == "complete"
    assert result.windows["1d"]["asset_return"] == pytest.approx(0.03)
    assert result.windows["1d"]["benchmark_return"] == pytest.approx(0.01)
    assert result.windows["1d"]["excess_return"] == pytest.approx(0.02)


def test_overlapping_events_are_not_counted_as_independent() -> None:
    assert events_overlap(
        datetime(2026, 9, 12, tzinfo=UTC),
        datetime(2026, 9, 13, tzinfo=UTC),
        trading_dates=[date(2026, 9, 14), date(2026, 9, 15), date(2026, 9, 16)],
        overlap_days=5,
    ) is True
```

Run: `cd backend && pytest tests/test_market_data.py tests/test_person_impact_event_study.py -q`.

Expected: FAIL because the provider and calculations do not exist.

- [ ] **Step 2: Add configuration and provider protocol**

Add to `backend/app/core/config.py`:

```python
market_data_provider: str = "stooq"
market_data_base_url: str = "https://stooq.com"
market_data_timeout_seconds: int = 30
market_data_max_lookback_days: int = 30
market_data_exchange_timezone: str = "America/New_York"
```

Implement in `market_data.py`:

```python
from dataclasses import dataclass
from datetime import date
from typing import Protocol


class MarketDataError(RuntimeError):
    def __init__(self, provider: str, message: str, response_status: int | None = None) -> None:
        self.provider = provider
        self.response_status = response_status
        super().__init__(message)


@dataclass(frozen=True)
class MarketBar:
    symbol: str
    trading_date: date
    adjusted_close: float
    volume: float | None


class MarketDataProvider(Protocol):
    def daily_bars(self, symbol: str, start: date, end: date) -> list[MarketBar]:
        raise NotImplementedError


class StooqDailyProvider:
    """Real daily CSV provider; credentials are never stored in the app."""
    def __init__(self, base_url: str, timeout_seconds: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def daily_bars(self, symbol: str, start: date, end: date) -> list[MarketBar]:
        raise NotImplementedError("implemented with the configured HTTP CSV provider")
```

The implementation must request the configured provider URL with `httpx`, parse CSV rows, reject missing/negative closes, normalize symbols to uppercase, and return `MarketDataError` with the provider response when the source is unavailable. Never instantiate a fake provider from application settings; tests inject `FakeMarketDataProvider` directly.

- [ ] **Step 3: Implement event-window calculations**

In `event_study.py`, implement these exact functions:

```python
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo

WINDOWS = ("1d", "3d", "5d")


@dataclass(frozen=True)
class EventStudyResult:
    event_cluster_id: str
    data_quality: str
    windows: dict[str, dict[str, float | str | None]]
    provider_name: str | None = None
    query_start: date | None = None
    query_end: date | None = None
    exchange_timezone: str = "America/New_York"
    missing_dates: list[date] = field(default_factory=list)
    window_overlap: bool = False


def select_event_trading_date(
    event_at: datetime,
    trading_dates: Sequence[date],
    exchange_timezone: str = "America/New_York",
) -> date:
    local_date = event_at.astimezone(ZoneInfo(exchange_timezone)).date()
    for trading_date in sorted(trading_dates):
        if trading_date >= local_date:
            return trading_date
    raise ValueError("event is after the last available trading date")

def compute_event_windows(
    *,
    event_at: datetime,
    asset_bars: Sequence[MarketBar],
    benchmark_bars: Sequence[MarketBar],
    event_cluster_id: str,
    exchange_timezone: str = "America/New_York",
) -> EventStudyResult:
    raise NotImplementedError

def events_overlap(
    left_event_at: datetime,
    right_event_at: datetime,
    trading_dates: Sequence[date],
    overlap_days: int = 5,
    exchange_timezone: str = "America/New_York",
) -> bool:
    left_date = select_event_trading_date(left_event_at, trading_dates, exchange_timezone)
    right_date = select_event_trading_date(right_event_at, trading_dates, exchange_timezone)
    return abs(trading_dates.index(right_date) - trading_dates.index(left_date)) <= overlap_days
```

Rules:

1. Convert all timestamps to the configured exchange timezone before selecting the first trading day at or after the event.
2. Use adjusted close, never raw close, for returns.
3. Compute asset return, benchmark return, excess return, volume ratio, and realized volatility for 1D/3D/5D.
4. If any required bar is missing, set `data_quality="partial"` and omit only the affected window.
5. If event timestamps overlap within five trading days, set `window_overlap=True`; do not count the later event as an independent profile sample.
6. Preserve provider name, query range, timezone, and missing dates in the serialized result.

- [ ] **Step 4: Run focused tests and lint**

Run: `cd backend && pytest tests/test_market_data.py tests/test_person_impact_event_study.py -q && ruff check app/services/investment/market_data.py app/services/investment/event_study.py`.

Expected: PASS with no production network calls in tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/config.py backend/.env.example backend/app/services/investment/market_data.py backend/app/services/investment/event_study.py backend/tests/test_market_data.py backend/tests/test_person_impact_event_study.py
git commit -m "feat(investment): add real market data event study foundation"
```

## 4. Task 4 — 人物影响事件、profile 聚合与异步任务

**Purpose:** 将 X 人物发言和市场反馈持久化，达到样本不足时不下结论、样本足够时可复核的要求。

**Files:**

- Add: `backend/app/services/investment/person_impact.py`
- Add: `backend/app/services/investment/person_impact_job_handler.py`
- Modify: `backend/app/services/task_worker.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/services/investment/service.py`
- Modify: `backend/app/api/v1/investment.py`
- Add: `backend/tests/test_person_impact_service.py`
- Add: `backend/tests/test_person_impact_api.py`

- [ ] **Step 1: Write failing service tests**

```python
def test_profile_reports_insufficient_sample_without_strength_label(session: Session) -> None:
    service = PersonImpactService(session, market_data=FakeMarketDataProvider({}))
    profile = service.rebuild_profile("person_1", workspace_id="ws_default")
    assert profile.valid_sample_count == 3
    assert profile.uncertainty == "样本不足"
    assert profile.hit_rate is None


def test_profile_excludes_overlapping_and_marked_concurrent_events(session: Session) -> None:
    service = PersonImpactService(session, market_data=FakeMarketDataProvider({}))
    profile = service.rebuild_profile("person_1", workspace_id="ws_default")
    assert profile.excluded_sample_count == 2
    assert profile.valid_sample_count == 6
```

Run: `cd backend && pytest tests/test_person_impact_service.py -q`.

Expected: FAIL because `PersonImpactService` and the job handler do not exist.

- [ ] **Step 2: Implement event generation and profile aggregation**

Implement:

```python
class PersonImpactService:
    def __init__(self, session: Session, market_data: MarketDataProvider) -> None:
        self.session = session
        self.market_data = market_data

    def rebuild_person(self, person_source_id: str, workspace_id: str) -> list[PersonImpactEvent]:
        raise NotImplementedError

    def rebuild_profile(self, person_source_id: str, workspace_id: str) -> PersonImpactProfile:
        raise NotImplementedError

    def list_events(self, person_source_id: str, workspace_id: str, limit: int) -> list[PersonImpactEvent]:
        raise NotImplementedError

    def get_profile(self, person_source_id: str, workspace_id: str) -> PersonImpactProfile:
        raise NotImplementedError
```

Rules:

1. Read only `InvestmentItem` rows whose `source_id` maps to the requested `InvestmentPersonSource` and whose `source_layer` is `human_source` or `expert_opinion`.
2. Map symbols from explicit item metadata, watchlist ticker, or theme ticker; if mapping is ambiguous, create an `insufficient_data` event with a concrete reason and do not calculate returns.
3. Select a configured benchmark (theme benchmark first, then market default) and call the injected provider.
4. Mark events as excluded when the event window overlaps another event cluster, a concurrent event is flagged, or required bars are missing.
5. Set `sample_sufficient = valid_sample_count >= 5`; only then calculate hit rate and stability label.
6. Store each calculation as an immutable event snapshot. Re-running updates only a new profile version or recomputes the same event ID from the same source snapshot; it must not mutate a saved digest.

- [ ] **Step 3: Add async handler and register it**

Define `PERSON_IMPACT_REFRESH_JOB_TYPE = "person_impact_refresh"`. The handler loads `target_id` as a person source, calls `rebuild_person()` and `rebuild_profile()`, writes counts to `TaskJob.output`, and raises a typed error for provider failures. Register it in `backend/app/main.py` beside the existing investment handlers. Duplicate active jobs for the same person/workspace must reuse the existing pending/running job.

- [ ] **Step 4: Add API routes**

Expose `list_person_impact_events`, `get_person_impact_profile`, and `refresh_person_impact` on `InvestmentService` so the router continues to use the existing `SERVICE_DEPENDENCY` pattern.

Add:

```python
@router.get("/person-sources/{person_id}/impact-events", response_model=list[PersonImpactEventResponse])
async def list_person_impact_events(
    person_id: str,
    workspace_id: str = "ws_default",
    limit: int = Query(default=50, ge=1, le=200),
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> list[PersonImpactEventResponse]:
    return [
        PersonImpactEventResponse.model_validate(event)
        for event in service.list_person_impact_events(person_id, workspace_id, limit)
    ]

@router.get("/person-sources/{person_id}/impact-profile", response_model=PersonImpactProfileResponse)
async def get_person_impact_profile(
    person_id: str,
    workspace_id: str = "ws_default",
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> PersonImpactProfileResponse:
    return PersonImpactProfileResponse.model_validate(
        service.get_person_impact_profile(person_id, workspace_id)
    )

@router.post("/person-sources/{person_id}/impact-refresh", response_model=PollSourceResponse, status_code=202)
async def refresh_person_impact(
    person_id: str,
    workspace_id: str = "ws_default",
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> PollSourceResponse:
    return PollSourceResponse.model_validate(
        service.refresh_person_impact(person_id, workspace_id)
    )
```

Enforce workspace ownership before loading a person, and return an explicit `insufficient_data` response rather than an empty success when market data is unavailable.

- [ ] **Step 5: Run backend tests**

Run: `cd backend && pytest tests/test_person_impact_service.py tests/test_person_impact_api.py tests/test_task_worker.py -q`.

Expected: PASS, including duplicate-job reuse and workspace isolation.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/investment/person_impact.py backend/app/services/investment/person_impact_job_handler.py backend/app/services/task_worker.py backend/app/main.py backend/app/services/investment/service.py backend/app/api/v1/investment.py backend/tests/test_person_impact_service.py backend/tests/test_person_impact_api.py
git commit -m "feat(investment): analyze person statements against market reactions"
```

## 5. Task 5 — OpportunityCandidate 生成、门槛与排序

**Purpose:** 让系统真正区分“信号”和“机会”，只有具备预期差、催化剂、风险和证伪条件的研究对象才进入机会候选列表。

**Files:**

- Add: `backend/app/services/investment/opportunity.py`
- Modify: `backend/app/services/investment/service.py`
- Modify: `backend/app/api/v1/investment.py`
- Add: `backend/tests/test_opportunity_candidate_service.py`
- Add: `backend/tests/test_opportunity_candidate_api.py`

- [ ] **Step 1: Write failing gate tests**

```python
from app.schemas.investment import OpportunityCandidateCreate
from app.services.investment.opportunity import OpportunityService


def test_signal_without_catalyst_stays_signal(session: Session) -> None:
    result = OpportunityService(session).promote_signal(
        signal_id="sig_1",
        workspace_id="ws_default",
        payload={"title": "hot topic", "asset_symbols": ["NVDA"]},
    )
    assert result.created is False
    assert result.reason == "missing_catalyst"


def test_valid_candidate_contains_expected_case_and_invalidation_condition(session: Session) -> None:
    result = OpportunityService(session).promote_signal(
        signal_id="sig_2",
        workspace_id="ws_default",
        payload=valid_opportunity_payload(),
    )
    assert result.created is True
    assert result.opportunity.expected_case
    assert result.opportunity.invalidation_conditions


def valid_opportunity_payload() -> OpportunityCandidateCreate:
    return OpportunityCandidateCreate(
        title="AI server demand",
        asset_symbols=["NVDA"],
        opportunity_type="earnings_inflection",
        change_summary="Three independent primary sources raised capex guidance.",
        expected_case="Consensus underestimates demand persistence.",
        market_case="Price has not moved relative to SOXX.",
        impact_path="Orders -> revenue -> earnings revisions.",
        catalyst="Next earnings call",
        risk_flags=["valuation"],
        invalidation_conditions=["Orders cancel for two consecutive months"],
        next_action="Verify supplier lead times",
        evidence_refs=["inv_1", "fact_1"],
        confidence=0.72,
    )
```

Run: `cd backend && pytest tests/test_opportunity_candidate_service.py -q`.

Expected: FAIL because the gate and service do not exist.

- [ ] **Step 2: Implement explicit promotion gate**

Implement:

```python
REQUIRED_OPPORTUNITY_FIELDS = (
    "asset_symbols", "evidence_refs", "impact_path", "catalyst",
    "expected_case", "market_case", "risk_flags", "invalidation_conditions",
    "next_action",
)

class OpportunityService:
    def promote_signal(self, signal_id: str, workspace_id: str, payload: OpportunityCandidateCreate) -> OpportunityPromotionResult:
        raise NotImplementedError

    def list_candidates(self, workspace_id: str, status: str | None, limit: int) -> list[OpportunityCandidate]:
        raise NotImplementedError

    def review(self, opportunity_id: str, workspace_id: str, action: OpportunityReviewAction) -> OpportunityCandidate:
        raise NotImplementedError
```

The service must reject or downgrade a signal when any required field is absent, evidence refs are empty, the asset mapping is ambiguous, or market reaction state is unknown and cannot be obtained. It must never infer expected return or valuation from a price move alone. Set `market_reaction_state` to `reacted`, `partially_reacted`, `not_observed`, or `unknown` with a reason.

- [ ] **Step 3: Implement opportunity scoring**

Store a breakdown with these normalized keys: `novelty`, `source_quality`, `independent_sources`, `theme_relevance`, `validation`, `market_reaction_gap`, `account_stability`, `expected_gap_clarity`, `catalyst_clarity`, `downside_risk`, `user_context_match`. The score is for research ordering only. Map to `priority="high_priority_research"`, `priority="research"`, or `priority="watch"`; never use `buy`, `sell`, `long`, or `short`.

- [ ] **Step 4: Add API routes and response tests**

Expose the three operations on `InvestmentService` and inject it with `SERVICE_DEPENDENCY`; each method must enforce the requested workspace before querying or mutating a candidate.

Add:

```python
@router.get("/opportunities", response_model=list[OpportunityCandidateResponse])
async def list_opportunities(
    workspace_id: str = "ws_default",
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> list[OpportunityCandidateResponse]:
    return [
        OpportunityCandidateResponse.model_validate(candidate)
        for candidate in service.list_opportunities(workspace_id, status, limit)
    ]

@router.post("/signals/{signal_id}/opportunity", response_model=OpportunityPromotionResult, status_code=201)
async def promote_signal_to_opportunity(
    signal_id: str,
    payload: OpportunityCandidateCreate,
    workspace_id: str = "ws_default",
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> OpportunityPromotionResult:
    result = service.promote_signal_to_opportunity(signal_id, workspace_id, payload)
    return OpportunityPromotionResult.model_validate(result)

@router.patch("/opportunities/{opportunity_id}", response_model=OpportunityCandidateResponse)
async def review_opportunity(
    opportunity_id: str,
    payload: OpportunityReviewAction,
    workspace_id: str = "ws_default",
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> OpportunityCandidateResponse:
    return OpportunityCandidateResponse.model_validate(
        service.review_opportunity(opportunity_id, workspace_id, payload)
    )
```

Ensure the API exposes evidence refs and risk/invalidation fields; do not flatten them into a marketing-style score only.

- [ ] **Step 5: Run tests and commit**

Run: `cd backend && pytest tests/test_opportunity_candidate_service.py tests/test_opportunity_candidate_api.py tests/test_investment_signals.py -q`.

```bash
git add backend/app/services/investment/opportunity.py backend/app/services/investment/service.py backend/app/api/v1/investment.py backend/tests/test_opportunity_candidate_service.py backend/tests/test_opportunity_candidate_api.py
git commit -m "feat(investment): separate opportunity candidates from early signals"
```

## 6. Task 6 — 账号发现、推荐理由与一键追踪

**Purpose:** 推荐 X、YouTube 和机构账号，并允许用户在 KnowPilot 内一键创建可恢复的追踪订阅。

**Files:**

- Add: `backend/app/services/investment/account_recommendation.py`
- Modify: `backend/app/services/investment/service.py`
- Modify: `backend/app/api/v1/investment.py`
- Add: `backend/tests/test_account_recommendation.py`
- Add: `backend/tests/test_account_recommendation_api.py`

- [ ] **Step 1: Write failing recommendation tests**

```python
def test_recommendation_reason_mentions_evidence_and_sample_count(session: Session) -> None:
    recommendations = AccountRecommendationService(session, web_search=FakeWebSearch([])).refresh("ws_default")
    rec = next(item for item in recommendations if item.handle == "NickTimiraos")
    assert rec.sample_count == 12
    assert "验证" in rec.reason
    assert rec.recommendation_label in {"高匹配", "值得学习", "一手源", "样本不足"}


def test_follow_is_idempotent_and_does_not_touch_external_accounts(client: TestClient) -> None:
    first = client.post("/api/v1/investment/account-recommendations/rec_1/follow", json={"theme_ids": ["theme_macro"]})
    second = client.post("/api/v1/investment/account-recommendations/rec_1/follow", json={"theme_ids": ["theme_macro"]})
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["source_id"] == second.json()["source_id"]
```

Run: `cd backend && pytest tests/test_account_recommendation.py tests/test_account_recommendation_api.py -q`。

Expected: FAIL because recommendation refresh and follow endpoints do not exist.

- [ ] **Step 2: Implement source-backed candidate discovery**

Implement:

```python
class AccountRecommendationService:
    def __init__(self, session: Session, web_search: WebSearchClient | None = None) -> None:
        self.session = session
        self.web_search = web_search

    def refresh(self, workspace_id: str, theme_id: str | None = None) -> list[AccountRecommendation]:
        raise NotImplementedError

    def follow(self, recommendation_id: str, workspace_id: str, payload: FollowRecommendationRequest) -> InvestmentSource:
        raise NotImplementedError

    def dismiss(self, recommendation_id: str, workspace_id: str) -> AccountRecommendation:
        raise NotImplementedError
```

Candidate sources:

1. Existing `InvestmentPersonSource` and `InvestmentSource` records.
2. Explicitly configured real web-search provider for discovering public X/YouTube/official pages; when Tavily is not configured, return a visible “搜索服务未配置” state and do not fabricate candidates.
3. Existing item/fact/signal history for sample count, evidence count, lead time and validation outcomes.

Recommendation score keys: `theme_relevance`, `source_quality`, `lead_time`, `validation_rate`, `independence`, `noise_penalty`, `blind_spot_coverage`, `sample_sufficiency`. A new account with fewer than five valid events must receive `样本不足`, regardless of raw score. Reasons must be generated from persisted facts and metrics, not static claims.

- [ ] **Step 3: Implement idempotent follow behavior**

For X accounts, create or reuse an `x_web` `InvestmentSource` with normalized username. For YouTube, create or reuse the existing YouTube subscription/source path. For institutions, bind the source URL and configured fetcher. Add `theme_ids` to the person source, enqueue the existing source polling task once, and set recommendation status to `followed`. Never call an external “follow” API and never store external credentials.

- [ ] **Step 4: Add API routes**

Expose the four operations on `InvestmentService` and inject it with `SERVICE_DEPENDENCY`; all list, refresh, follow and dismiss operations must check workspace ownership.

```python
@router.get("/account-recommendations", response_model=list[AccountRecommendationResponse])
async def list_account_recommendations(
    workspace_id: str = "ws_default",
    platform: str | None = Query(default=None),
    theme_id: str | None = Query(default=None),
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> list[AccountRecommendationResponse]:
    return [
        AccountRecommendationResponse.model_validate(item)
        for item in service.list_account_recommendations(workspace_id, platform, theme_id)
    ]

@router.post("/account-recommendations/refresh", response_model=list[AccountRecommendationResponse])
async def refresh_account_recommendations(
    workspace_id: str = "ws_default",
    theme_id: str | None = Query(default=None),
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> list[AccountRecommendationResponse]:
    return [
        AccountRecommendationResponse.model_validate(item)
        for item in service.refresh_account_recommendations(workspace_id, theme_id)
    ]

@router.post("/account-recommendations/{recommendation_id}/follow", response_model=InvestmentSourceResponse, status_code=201)
async def follow_account_recommendation(
    recommendation_id: str,
    payload: FollowRecommendationRequest,
    workspace_id: str = "ws_default",
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> InvestmentSourceResponse:
    return InvestmentSourceResponse.model_validate(
        service.follow_account_recommendation(recommendation_id, workspace_id, payload)
    )

@router.post("/account-recommendations/{recommendation_id}/dismiss", response_model=AccountRecommendationResponse)
async def dismiss_account_recommendation(
    recommendation_id: str,
    workspace_id: str = "ws_default",
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> AccountRecommendationResponse:
    return AccountRecommendationResponse.model_validate(
        service.dismiss_account_recommendation(recommendation_id, workspace_id)
    )
```

- [ ] **Step 5: Run tests and commit**

Run: `cd backend && pytest tests/test_account_recommendation.py tests/test_account_recommendation_api.py tests/test_investment_x_web.py -q`.

```bash
git add backend/app/services/investment/account_recommendation.py backend/app/services/investment/service.py backend/app/api/v1/investment.py backend/tests/test_account_recommendation.py backend/tests/test_account_recommendation_api.py
git commit -m "feat(investment): recommend and follow high-value accounts"
```

## 7. Task 7 — 用户上下文、结果复盘与权重校准

**Purpose:** 让系统知道用户关心什么，并将推荐/机会的后续结果写入不可变快照，用于校准但不篡改历史。

**Files:**

- Add: `backend/app/services/investment/outcomes.py`
- Modify: `backend/app/services/investment/service.py`
- Modify: `backend/app/api/v1/investment.py`
- Add: `backend/tests/test_investment_outcomes.py`
- Add: `backend/tests/test_investment_context_api.py`

- [ ] **Step 1: Write failing outcome tests**

```python
def test_outcome_is_append_only_and_does_not_change_saved_digest(session: Session) -> None:
    service = OutcomeService(session)
    snapshot_id = service.record(
        RecommendationOutcomeCreate(
            opportunity_id="opp_1",
            adopted=True,
            outcome_status="invalidated",
            observed_at=datetime(2026, 9, 20, tzinfo=UTC),
        )
    )
    assert session.get(RecommendationOutcome, snapshot_id) is not None
    assert service.list_for_opportunity("opp_1", "ws_default")[0].outcome_status == "invalidated"


def test_context_filters_recommendations_without_requiring_brokerage_data(client: TestClient) -> None:
    response = client.patch(
        "/api/v1/investment/context",
        json={"markets": ["us"], "horizons": ["mid"], "focus_theme_ids": ["theme_ai"], "min_liquidity": "high"},
    )
    assert response.status_code == 200
    assert response.json()["markets"] == ["us"]
```

- [ ] **Step 2: Implement context and outcome APIs**

Expose `get_user_context`, `update_user_context`, `record_recommendation_outcome`, and `list_opportunity_outcomes` on `InvestmentService` and inject it with `SERVICE_DEPENDENCY`. Reject a payload whose `workspace_id` differs from the request workspace.

Add:

```python
@router.get("/context", response_model=UserInvestmentContextResponse)
async def get_investment_context(
    workspace_id: str = "ws_default",
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> UserInvestmentContextResponse:
    return UserInvestmentContextResponse.model_validate(service.get_user_context(workspace_id))


@router.patch("/context", response_model=UserInvestmentContextResponse)
async def update_investment_context(
    payload: UserInvestmentContextUpdate,
    workspace_id: str = "ws_default",
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> UserInvestmentContextResponse:
    return UserInvestmentContextResponse.model_validate(
        service.update_user_context(workspace_id, payload)
    )


@router.post("/recommendation-outcomes", response_model=RecommendationOutcomeResponse, status_code=201)
async def create_recommendation_outcome(
    payload: RecommendationOutcomeCreate,
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> RecommendationOutcomeResponse:
    return RecommendationOutcomeResponse.model_validate(service.record_recommendation_outcome(payload))


@router.get("/opportunities/{opportunity_id}/outcomes", response_model=list[RecommendationOutcomeResponse])
async def list_opportunity_outcomes(
    opportunity_id: str,
    workspace_id: str = "ws_default",
    service: InvestmentService = SERVICE_DEPENDENCY,
) -> list[RecommendationOutcomeResponse]:
    return [
        RecommendationOutcomeResponse.model_validate(outcome)
        for outcome in service.list_opportunity_outcomes(opportunity_id, workspace_id)
    ]
```

Use `UserInvestmentContext` as a singleton per workspace. Validate all referenced theme/watchlist IDs belong to the workspace. Recording an outcome appends a row; it never rewrites `InvestmentDigestSnapshot`, `OpportunityCandidate.score_breakdown`, or historical `PersonImpactEvent` rows.

- [ ] **Step 3: Add deterministic calibration job/service**

Define `CalibrationResult` in `outcomes.py` with `version: int`, `changed: bool`, `reason: str`, and `weights: dict[str, float]`. Implement `OutcomeService` with `record(payload: RecommendationOutcomeCreate) -> RecommendationOutcome`, `list_for_opportunity(opportunity_id: str, workspace_id: str) -> list[RecommendationOutcome]`, and `recalculate_recommendation_weights(workspace_id: str, as_of: datetime) -> CalibrationResult`.

Implement `recalculate_recommendation_weights(workspace_id, as_of)` using only outcomes with `observed_at <= as_of`. Store a version and reason in the next recommendation score breakdown. Use a minimum of 10 evaluated outcomes before changing a weight; otherwise retain the previous version and show `样本不足`. Add a test proving a future outcome cannot change an earlier recommendation snapshot.

- [ ] **Step 4: Run tests and commit**

Run: `cd backend && pytest tests/test_investment_outcomes.py tests/test_investment_context_api.py -q`。

```bash
git add backend/app/services/investment/outcomes.py backend/app/services/investment/service.py backend/app/api/v1/investment.py backend/tests/test_investment_outcomes.py backend/tests/test_investment_context_api.py
git commit -m "feat(investment): add context and outcome calibration"
```

## 8. Task 8 — 前端应用壳层与情报流首页

**Purpose:** 将首页改为情报流中心，主导航收敛为投资工作流，辅助资料能力继续可访问但不打扰日常机会发现。

**Files:**

- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/pages/InvestmentDashboardPage.tsx`
- Add: `frontend/src/pages/IntelligenceFlowPage.tsx`
- Add: `frontend/src/components/investment/OpportunityCandidateCard.tsx`
- Add: `frontend/src/test/fixtures/investmentFixtures.ts`
- Modify: `frontend/src/components/investment/InvestmentItemDrawer.tsx`
- Modify: `frontend/src/pages/InvestmentDashboardPage.test.tsx`
- Add: `frontend/src/pages/IntelligenceFlowPage.test.tsx`
- Modify: `frontend/src/App.test.tsx`

- [ ] **Step 1: Write failing UI tests**

Add `frontend/src/test/fixtures/investmentFixtures.ts` with typed `investmentFetchFixture`, `recommendationFixture`, and `personImpactFixture` fetch responders; each fixture must include the API fields from Task 1 and accept the count/sample overrides used below.

```tsx
it("shows at most five high-priority opportunity candidates", async () => {
  vi.stubGlobal("fetch", investmentFetchFixture({ opportunityCount: 8 }));
  render(<IntelligenceFlowPage />, { wrapper: MemoryRouter });
  expect((await screen.findAllByTestId("opportunity-card")).length).toBe(5);
  expect(screen.getByText("查看全部机会候选")).toBeInTheDocument();
});

it("separates information, signals, and opportunities", async () => {
  vi.stubGlobal("fetch", investmentFetchFixture());
  render(<IntelligenceFlowPage />, { wrapper: MemoryRouter });
  expect(await screen.findByText("最新情报")).toBeInTheDocument();
  expect(screen.getByText("正在发生")).toBeInTheDocument();
  expect(screen.getByText("高优先研究")).toBeInTheDocument();
});
```

Run: `cd frontend && npm run test -- IntelligenceFlowPage.test.tsx InvestmentDashboardPage.test.tsx`。

Expected: FAIL because the new page and card do not exist and `/` still renders the generic dashboard.

- [ ] **Step 2: Update navigation and routes**

In `App.tsx`:

1. Map `/` to `IntelligenceFlowPage` and keep `/investment` mapped to the compatibility dashboard/page.
2. Keep `/youtube`, `/youtube/summary/:documentId`, and subscription routes.
3. Replace the primary menu with `情报流`, `观察对象`, `假设验证`, `研究简报`, `账号发现`, `YouTube 观点`, `数据源`.
4. Add a collapsed `辅助` menu containing links to existing import/library/reader/search/graph/provenance/entity/notebook/settings routes.
5. Change the global search placeholder to `搜索情报、对象、假设和证据`.

Do not delete old routes or data. Update `App.test.tsx` expectations from generic `仪表盘` to `情报流`, while preserving route reachability tests for every legacy page.

- [ ] **Step 3: Build the information-flow page**

`IntelligenceFlowPage.tsx` must call `getInvestmentDashboard`, `listInvestmentItems`, `listInvestmentSignals`, and `listOpportunityCandidates` in parallel. Render:

- header with date and data range;
- four summary metrics: `值得注意`, `机会线索`, `假设受挑战`, `待验证`;
- compact filters for all objects, source layer, macro, opinion, high impact and 24-hour range;
- exactly five or fewer `OpportunityCandidateCard` items with “why now / expected gap / catalyst / risk / invalidation / next action” collapsed into readable rows;
- separate `最新情报` and `正在发生` sections;
- explicit loading, empty, partial-error and retry states.

`OpportunityCandidateCard` must use `data-testid="opportunity-card"`, link to evidence refs, and never render a buy/sell button.

- [ ] **Step 4: Extend evidence drawer**

Add an opportunity tab/section to `InvestmentItemDrawer.tsx` showing source excerpt, confidence, market reaction state, expected case, market case, catalyst, risks, invalidation conditions, and recommended next action. Actions are `加入验证`, `继续观察`, `建立研究任务`, `忽略`, `打开原文`.

- [ ] **Step 5: Run frontend gates**

Run: `cd frontend && npm run lint && npm run test -- IntelligenceFlowPage.test.tsx InvestmentDashboardPage.test.tsx App.test.tsx && npm run build`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/App.tsx frontend/src/styles.css frontend/src/pages/InvestmentDashboardPage.tsx frontend/src/pages/IntelligenceFlowPage.tsx frontend/src/components/investment/OpportunityCandidateCard.tsx frontend/src/components/investment/InvestmentItemDrawer.tsx frontend/src/test/fixtures/investmentFixtures.ts frontend/src/pages/IntelligenceFlowPage.test.tsx frontend/src/pages/InvestmentDashboardPage.test.tsx frontend/src/App.test.tsx
git commit -m "feat(frontend): make intelligence flow the investment home"
```

## 9. Task 9 — 账号发现与人物影响前端

**Purpose:** 让非专业用户直接理解推荐理由、点击关注追踪，并查看人物发言后的市场反应，而不需要阅读统计学术语。

**Files:**

- Add: `frontend/src/pages/AccountDiscoveryPage.tsx`
- Add: `frontend/src/pages/PersonImpactPage.tsx`
- Add: `frontend/src/components/investment/RecommendationCard.tsx`
- Add: `frontend/src/components/investment/ImpactSummary.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Add: `frontend/src/pages/AccountDiscoveryPage.test.tsx`
- Add: `frontend/src/pages/PersonImpactPage.test.tsx`

- [ ] **Step 1: Write failing tests**

Import the shared fixture responders from `frontend/src/test/fixtures/investmentFixtures.ts` and assert against the public labels, not implementation-specific class names.

```tsx
it("explains why an account is recommended and follows it idempotently", async () => {
  vi.stubGlobal("fetch", recommendationFixture());
  render(<AccountDiscoveryPage />, { wrapper: MemoryRouter });
  expect(await screen.findByText(/过去 30 天/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "+ 关注追踪" }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/follow"), expect.anything()));
});

it("shows insufficient sample instead of an impact conclusion", async () => {
  vi.stubGlobal("fetch", personImpactFixture({ valid_sample_count: 3, sample_sufficient: false }));
  render(<PersonImpactPage />, { wrapper: MemoryRouter });
  expect(await screen.findByText("样本不足")).toBeInTheDocument();
  expect(screen.queryByText("影响较强")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Implement `AccountDiscoveryPage`**

Render tabs `全部推荐`, `X 人物`, `YouTube 频道`, `机构与一手源`; cards show platform, handle, label, reason, theme tags, sample count, evidence count, expected update frequency, and `+ 关注追踪`. After follow, show `已关注` and actions `暂停追踪`, `查看最近内容`, `查看人物影响`. Surface `搜索服务未配置` and provider errors as visible alerts.

- [ ] **Step 3: Implement `PersonImpactPage`**

Render:

- profile summary with valid/total samples, positive/negative/neutral distribution, average lead time, average excess return and stability;
- `样本不足` or `不可归因` labels when required;
- event table with original X link, symbol, benchmark, 1D/3D/5D, volume ratio, duration, concurrent event flags and data quality;
- a simple SVG or CSS chart only from API-provided points, not client-side market calculations;
- disclaimer that historical association is not causality or a future-return promise.

- [ ] **Step 4: Wire routes and run tests**

Add `/investment/accounts` and `/investment/person-sources/:personId/impact`; keep `/investment/sources` as the configuration page. Run: `cd frontend && npm run lint && npm run test -- AccountDiscoveryPage.test.tsx PersonImpactPage.test.tsx App.test.tsx && npm run build`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/AccountDiscoveryPage.tsx frontend/src/pages/PersonImpactPage.tsx frontend/src/components/investment/RecommendationCard.tsx frontend/src/components/investment/ImpactSummary.tsx frontend/src/App.tsx frontend/src/styles.css frontend/src/pages/AccountDiscoveryPage.test.tsx frontend/src/pages/PersonImpactPage.test.tsx
git commit -m "feat(frontend): add account discovery and person impact views"
```

## 10. Task 10 — 假设验证、简报和复盘展示

**Purpose:** 将机会候选和人物影响接入原有假设验证与每日简报，形成可回看的日常工作闭环。

**Files:**

- Modify: `frontend/src/pages/InvestmentClaimsPage.tsx`
- Modify: `frontend/src/pages/InvestmentThesesPage.tsx`
- Modify: `frontend/src/pages/InvestmentDigestPage.tsx`
- Modify: `frontend/src/services/investmentApi.ts`
- Add: `frontend/src/components/investment/OutcomeTimeline.tsx`
- Add: `frontend/src/pages/InvestmentDigestPage.test.tsx`
- Add: `backend/app/services/investment/digest_service.py`
- Add: `backend/tests/test_investment_digest_opportunities.py`

- [ ] **Step 1: Write failing digest tests**

```python
def test_digest_contains_opportunity_fields_and_failed_outcomes() -> None:
    digest = InvestmentDigestService(session).build("ws_default")
    assert digest["opportunities"][0]["next_action"]
    assert digest["opportunities"][0]["invalidation_conditions"]
    assert digest["outcomes"][0]["outcome_status"] == "invalidated"
```

- [ ] **Step 2: Extend digest schema and service**

Add `opportunities`, `person_impact_events`, and `outcomes` to the digest response. Keep existing sections for primary information, YouTube opinions, early signals, claims and macro calendar. Each highlight includes evidence refs, confidence, market reaction state and reason. Do not regenerate or overwrite historical snapshots when a newer market bar arrives; create a new snapshot version/date.

- [ ] **Step 3: Update claims/theses UI**

In claims, group evidence as `支持`, `削弱`, `冲突`, `无关`, `还不确定`, and show the linked opportunity candidate if one exists. In theses, show which evidence caused the status change and allow the user to record an outcome note. Render `OutcomeTimeline` with recommendation date, adopted state, catalyst result, realized 1D/3D/5D and failure reason.

- [ ] **Step 4: Run tests and commit**

Run: `cd backend && pytest tests/test_investment_digest_opportunities.py tests/test_investment_digest.py -q`; then `cd frontend && npm run test -- InvestmentDigestPage.test.tsx && npm run build`.

```bash
git add backend/app/schemas/investment.py backend/app/services/investment/digest_service.py backend/tests/test_investment_digest_opportunities.py frontend/src/pages/InvestmentClaimsPage.tsx frontend/src/pages/InvestmentThesesPage.tsx frontend/src/pages/InvestmentDigestPage.tsx frontend/src/components/investment/OutcomeTimeline.tsx frontend/src/services/investmentApi.ts frontend/src/pages/InvestmentDigestPage.test.tsx
git commit -m "feat(investment): connect opportunities and outcomes to digest"
```

## 11. Task 11 — 回填、运营可观测性与迁移安全

**Purpose:** 让现有 X/YouTube 数据可以渐进回填，确保失败可见、迁移可回滚、历史结果不被覆盖。

**Files:**

- Add: `backend/scripts/backfill_person_impact.py`
- Add: `backend/scripts/backfill_opportunity_candidates.py`
- Modify: `backend/scripts/backfill_investment_signals.py`
- Modify: `README.md`
- Modify: `docs/development/local-dev-guide.md`
- Add: `backend/tests/test_investment_opportunity_backfill.py`

- [ ] **Step 1: Write backfill tests**

```python
def test_backfill_is_idempotent_and_keeps_existing_items() -> None:
    first = backfill_person_impact(session, workspace_id="ws_default", limit=100)
    second = backfill_person_impact(session, workspace_id="ws_default", limit=100)
    assert first.created >= 0
    assert second.created == 0
    assert second.skipped >= first.created
```

- [ ] **Step 2: Implement scripts**

`backfill_person_impact.py` finds human-source items with explicit person source and symbol mapping, enqueues/reuses `person_impact_refresh` jobs, and reports `created/skipped/failed` JSON. `backfill_opportunity_candidates.py` only promotes signals passing the gate; it never guesses missing catalyst, risk or invalidation fields. Both scripts accept `--workspace-id`, `--limit`, `--dry-run`, and `--as-of`.

- [ ] **Step 3: Add observability and runbook**

Document:

- market provider name, URL, timezone, delay and data-quality states;
- job types `person_impact_refresh`, opportunity promotion and calibration;
- visible failure messages for provider timeout, rate limit, missing symbol and search unconfigured;
- rollback command for `202609140001` migration;
- how to pause a recommendation without deleting evidence;
- how to rebuild a profile or digest snapshot from an `as_of` timestamp.

- [ ] **Step 4: Run full verification**

Run:

```bash
cd backend
pytest
ruff check .
mypy app
alembic upgrade head
alembic downgrade 202609030002
alembic upgrade head

cd ../frontend
npm run lint
npm run test
npm run build
```

Expected: all tests pass; migration downgrade/upgrade preserves pre-existing investment rows; frontend build succeeds.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/backfill_person_impact.py backend/scripts/backfill_opportunity_candidates.py backend/scripts/backfill_investment_signals.py backend/tests/test_investment_opportunity_backfill.py README.md docs/development/local-dev-guide.md
git commit -m "chore(investment): add opportunity backfill and operations runbook"
```

## 12. 合并顺序与发布门槛

每个任务完成后单独提交，按以下顺序合并：

1. Task 1 contracts。
2. Task 2 models/migration。
3. Task 3 market provider/event study。
4. Task 4 person impact jobs/API。
5. Task 5 opportunity candidates.
6. Task 6 account recommendations/follow.
7. Task 7 context/outcomes/calibration.
8. Task 8 intelligence-flow shell.
9. Task 9 account and impact pages.
10. Task 10 claims/digest integration.
11. Task 11 backfill and operations.

发布前必须满足：

- 没有 mock provider、mock source 或静态推荐理由进入生产依赖；
- 每条机会候选都有证据、预期差、催化剂、风险、证伪条件和下一步动作；
- 每个人物 profile 显示有效样本数，并在少于 5 个有效样本时显示“样本不足”；
- 同事件转载链不会伪造独立来源，重叠事件不会伪造独立样本；
- 市场数据声明复权、时区、交易日历、供应商、延迟和缺失处理；
- 首页最多展示 3–5 条高优先研究候选；
- 账号关注是 KnowPilot 内部订阅，不修改外部 X/YouTube 关注关系；
- 结果复盘为追加写入，历史简报和评分快照不可被未来数据覆盖；
- 旧路由、YouTube、文档和知识图谱数据继续可访问；
- 后端和前端完整验证命令全部通过。

## 13. 计划自检

- 产品规格中的 `OpportunityCandidate`、预期差、催化剂、时间窗口、风险和证伪条件：Tasks 1、5、8、10 覆盖。
- 人物影响事件研究、复权、基准、1D/3D/5D、重叠窗口、同期干扰和样本不足：Tasks 1、3、4、9 覆盖。
- 账号推荐、理由、一键追踪、幂等和外部关注边界：Tasks 1、6、9 覆盖。
- 用户投资上下文与结果复盘校准：Task 7 覆盖。
- 首页有限输出、情报/信号/机会分层：Task 8 覆盖。
- 假设验证、简报、失败结果和历史快照：Task 10 覆盖。
- 迁移、回填、可观测性、回滚和全量测试：Task 11、12 覆盖。
- 全文已扫描，未发现占位文本；后续任务引用的类型、路由和 job type 均在前序任务中定义。

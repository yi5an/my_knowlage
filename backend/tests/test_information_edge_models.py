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
    assert saved is not None
    assert saved.signal_stage == "repeating"
    assert saved.information_edge_score == 0.72
    assert saved.score_breakdown["lead_time_score"] == 0.8

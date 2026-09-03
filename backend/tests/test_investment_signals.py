"""Tests for early signal aggregation from structured investment facts."""

from __future__ import annotations

from collections.abc import Generator
from uuid import uuid4

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base
from app.infrastructure.models import (
    InvestmentFact,
    InvestmentItem,
    InvestmentSignal,
    InvestmentSource,
    InvestmentWatchlist,
    TraceEdge,
    TraceNode,
    Workspace,
)
from app.services.investment.signal_service import InvestmentSignalService
from app.services.provenance.links import TraceLinkService


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


def _watchlist(session: Session) -> InvestmentWatchlist:
    watchlist = InvestmentWatchlist(
        id="wl_ai",
        workspace_id="ws_default",
        name="AI Infrastructure",
        watch_type="theme",
        keywords=["AI", "data center"],
    )
    session.add(watchlist)
    session.commit()
    return watchlist


def _source(session: Session, name: str, watchlist_id: str) -> InvestmentSource:
    source = InvestmentSource(
        id=f"src_{uuid4().hex}",
        workspace_id="ws_default",
        source_type="x_web",
        name=name,
        config={"mode": "account", "username": name},
        default_info_layer="opinion",
        default_watchlist_ids=[watchlist_id],
        poll_interval_seconds=900,
    )
    session.add(source)
    session.commit()
    return source


def _item(session: Session, source: InvestmentSource, title: str) -> InvestmentItem:
    item = InvestmentItem(
        id=f"inv_{uuid4().hex}",
        workspace_id="ws_default",
        source_id=source.id,
        dedupe_key=f"dk_{uuid4().hex}",
        title=title,
        source_url=f"https://x.com/{source.name}/status/{uuid4().int % 100000}",
        source_name=f"@{source.name}",
        info_layer="opinion",
        source_credibility="personal_opinion",
    )
    session.add(item)
    session.commit()
    return item


def _fact(
    session: Session,
    item: InvestmentItem,
    watchlist_id: str,
    text: str,
    confidence: float,
) -> InvestmentFact:
    fact = InvestmentFact(
        id=f"fact_{uuid4().hex}",
        workspace_id="ws_default",
        source_item_id=item.id,
        watchlist_id=watchlist_id,
        fact_text=text,
        fact_text_zh=text,
        fact_type="capex_signal",
        entities=["NVIDIA", "data center"],
        evidence_url=item.source_url,
        evidence_excerpt=text,
        confidence=confidence,
        verification_status="pending",
    )
    session.add(fact)
    session.commit()
    return fact


def test_refresh_signals_clusters_facts_and_counts_sources() -> None:
    session = next(_session())
    watchlist = _watchlist(session)
    source_a = _source(session, "nvidia", watchlist.id)
    source_b = _source(session, "semianalysis", watchlist.id)
    item_a = _item(session, source_a, "NVIDIA data center capex")
    item_b = _item(session, source_b, "Data center capex remains strong")
    fact_a = _fact(
        session,
        item_a,
        watchlist.id,
        "NVIDIA data center demand remains strong.",
        0.8,
    )
    fact_b = _fact(
        session,
        item_b,
        watchlist.id,
        "Data center demand remains strong for NVIDIA.",
        0.9,
    )

    signals = InvestmentSignalService(session).refresh_signals("ws_default")

    assert len(signals) == 1
    signal = signals[0]
    assert signal.watchlist_id == watchlist.id
    assert signal.signal_type == "capex_signal"
    assert signal.source_count == 2
    assert sorted(signal.fact_ids) == sorted([fact_a.id, fact_b.id])
    assert sorted(signal.item_ids) == sorted([item_a.id, item_b.id])
    assert signal.confidence == 0.85
    assert signal.status == "tracking"

    listed = list(session.scalars(select(InvestmentSignal)))
    assert [s.id for s in listed] == [signal.id]


def test_refresh_signals_is_idempotent_for_same_fact_cluster() -> None:
    session = next(_session())
    watchlist = _watchlist(session)
    source = _source(session, "nvidia", watchlist.id)
    item = _item(session, source, "NVIDIA platform")
    _fact(session, item, watchlist.id, "NVIDIA announced a new platform.", 0.7)

    first = InvestmentSignalService(session).refresh_signals("ws_default")
    second = InvestmentSignalService(session).refresh_signals("ws_default")

    assert len(first) == 1
    assert len(second) == 1
    assert session.scalar(select(func.count(InvestmentSignal.id))) == 1
    assert second[0].id == first[0].id


def test_refresh_preserves_signal_review_and_registers_fact_aggregation_edges() -> None:
    session = next(_session())
    watchlist = _watchlist(session)
    source = _source(session, "nvidia", watchlist.id)
    item = _item(session, source, "NVIDIA platform")
    fact = _fact(session, item, watchlist.id, "NVIDIA announced a new platform.", 0.7)

    signal = InvestmentSignalService(session).refresh_signals("ws_default")[0]
    signal_node = session.scalar(
        select(TraceNode).where(
            TraceNode.backing_type == "investment_signal",
            TraceNode.backing_id == signal.id,
        )
    )
    fact_node = session.scalar(
        select(TraceNode).where(
            TraceNode.backing_type == "investment_fact",
            TraceNode.backing_id == fact.id,
        )
    )
    assert signal_node is not None and fact_node is not None
    edge = session.scalar(
        select(TraceEdge).where(
            TraceEdge.source_node_id == fact_node.id,
            TraceEdge.target_node_id == signal_node.id,
            TraceEdge.relation_type == "aggregates",
        )
    )
    assert edge is not None
    TraceLinkService(session).review(
        edge_id=edge.id,
        workspace_id="ws_default",
        action="confirm",
        expected_version=edge.version_no,
        reviewer_id="reviewer",
        note="verified cluster",
    )
    session.commit()

    refreshed = InvestmentSignalService(session).refresh_signals("ws_default")[0]
    refreshed_edge = session.get(TraceEdge, edge.id)
    assert refreshed.id == signal.id
    assert refreshed_edge is not None
    assert refreshed_edge.review_status == "confirmed"
    assert refreshed_edge.version_no == 2


def test_membership_change_versions_signal_and_keeps_old_history() -> None:
    session = next(_session())
    watchlist = _watchlist(session)
    source_a = _source(session, "nvidia", watchlist.id)
    source_b = _source(session, "analyst", watchlist.id)
    item_a = _item(session, source_a, "NVIDIA demand")
    item_b = _item(session, source_b, "NVIDIA demand follow-up")
    fact_a = _fact(session, item_a, watchlist.id, "NVIDIA data center demand remains strong.", 0.8)
    fact_b = _fact(session, item_b, watchlist.id, "NVIDIA data center demand remains strong.", 0.9)

    first = InvestmentSignalService(session).refresh_signals("ws_default")[0]
    fact_b_node = session.scalar(
        select(TraceNode).where(
            TraceNode.backing_type == "investment_fact",
            TraceNode.backing_id == fact_b.id,
        )
    )
    first_node = session.scalar(
        select(TraceNode).where(
            TraceNode.backing_type == "investment_signal",
            TraceNode.backing_id == first.id,
        )
    )
    assert fact_b_node is not None and first_node is not None
    old_edge = session.scalar(
        select(TraceEdge).where(
            TraceEdge.source_node_id == fact_b_node.id,
            TraceEdge.target_node_id == first_node.id,
            TraceEdge.relation_type == "aggregates",
        )
    )
    assert old_edge is not None
    TraceLinkService(session).review(
        edge_id=old_edge.id,
        workspace_id="ws_default",
        action="confirm",
        expected_version=old_edge.version_no,
        reviewer_id="reviewer",
        note="confirmed source",
    )
    fact_b.is_active = False
    session.commit()

    second = InvestmentSignalService(session).refresh_signals("ws_default")[0]
    old_signal = session.get(InvestmentSignal, first.id)
    historical_edge = session.get(TraceEdge, old_edge.id)
    assert second.id != first.id
    assert second.fact_ids == [fact_a.id]
    assert old_signal is not None and old_signal.is_active is False
    assert historical_edge is not None and historical_edge.review_status == "confirmed"


def test_refresh_signals_clusters_near_duplicate_facts_with_different_entities() -> None:
    session = next(_session())
    watchlist = _watchlist(session)
    source_a = _source(session, "nvidia", watchlist.id)
    source_b = _source(session, "analyst", watchlist.id)
    item_a = _item(session, source_a, "NVIDIA demand")
    item_b = _item(session, source_b, "NVDA demand")
    fact_a = _fact(
        session,
        item_a,
        watchlist.id,
        "NVIDIA data center demand remains strong.",
        0.82,
    )
    fact_b = _fact(
        session,
        item_b,
        watchlist.id,
        "NVDA data-center demand is still strong.",
        0.78,
    )
    fact_b.entities = ["NVDA", "data center"]
    session.commit()

    signals = InvestmentSignalService(session).refresh_signals("ws_default")

    assert len(signals) == 1
    assert sorted(signals[0].fact_ids) == sorted([fact_a.id, fact_b.id])
    assert signals[0].source_count == 2


def test_refresh_signals_penalizes_repeated_posts_from_one_source() -> None:
    session = next(_session())
    watchlist = _watchlist(session)
    source = _source(session, "nvidia", watchlist.id)
    item_a = _item(session, source, "first")
    item_b = _item(session, source, "repost")
    _fact(session, item_a, watchlist.id, "NVIDIA data center demand remains strong.", 0.9)
    _fact(session, item_b, watchlist.id, "Data center demand remains strong for NVIDIA.", 0.9)

    signals = InvestmentSignalService(session).refresh_signals("ws_default")

    assert len(signals) == 1
    assert signals[0].source_count == 1
    assert signals[0].confidence == 0.59

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base
from app.infrastructure.models import (
    InvestmentItem,
    InvestmentPersonImpactEvent,
    InvestmentPersonImpactProfile,
    InvestmentPersonSource,
    Workspace,
)
from app.services.investment.market_data import MarketBar, MarketDataError
from app.services.investment.person_impact import PersonImpactService


class FakeProvider:
    provider_name = "fake"

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def daily_bars(self, symbol: str, start, end):
        if self.fail:
            raise MarketDataError("fake", "provider unavailable")
        from datetime import timedelta

        first = max(start, datetime(2026, 9, 14, tzinfo=UTC).date())
        count = (end - first).days + 1
        direction = 2 if symbol == "AAA" else -1 if symbol == "BBB" else 0
        return [
            MarketBar(symbol, first + timedelta(days=i), 100 + direction * i, 1_000_000)
            for i in range(count)
            if start <= first + timedelta(days=i) <= end
        ]


class EmptyProvider(FakeProvider):
    def daily_bars(self, symbol: str, start, end):  # noqa: ARG002
        return []


def _session() -> Session:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    session.add(Workspace(id="ws_test", name="Test"))
    session.commit()
    return session


def _seed_person(session: Session, person_id: str = "person_1") -> InvestmentPersonSource:
    person = InvestmentPersonSource(
        id=person_id, workspace_id="ws_test", platform="x", handle="analyst"
    )
    session.add(person)
    session.commit()
    return person


def _item(
    session: Session,
    item_id: str,
    person_id: str,
    symbol: str | list[str] | None,
    event_at: datetime | None,
    title: str = "statement",
) -> InvestmentItem:
    raw = {} if symbol is None else {"symbol": symbol}
    item = InvestmentItem(
        id=item_id,
        workspace_id="ws_test",
        source_id=person_id,
        title=title,
        dedupe_key=item_id,
        source_layer="human_source",
        published_at=event_at,
        event_at=event_at,
        raw_payload=raw,
    )
    session.add(item)
    session.commit()
    return item


def test_rebuild_profile_tracks_valid_excluded_and_uncertainty() -> None:
    session = _session()
    _seed_person(session)
    base = datetime(2026, 9, 14, tzinfo=UTC)
    for index in range(3):
        _item(
            session,
            f"valid_{index}",
            "person_1",
            "AAA",
            base + timedelta(days=index * 7),
            f"valid {index}",
        )
    _item(session, "ambiguous", "person_1", ["AAA", "BBB"], base, "ambiguous")
    _item(session, "missing", "person_1", None, base, "missing symbol")
    result = PersonImpactService(session, market_provider=FakeProvider()).rebuild_person("person_1")
    profile = result["profile"]
    assert profile.sample_count == 5
    assert profile.valid_sample_count == 3
    assert profile.excluded_sample_count == 2
    assert profile.hit_rate is None
    assert profile.uncertainty == "样本不足"
    events = list(session.scalars(select(InvestmentPersonImpactEvent)))
    assert any(event.event_status == "insufficient_data" for event in events)


def test_six_valid_events_populate_hit_rate_and_stability() -> None:
    session = _session()
    _seed_person(session)
    base = datetime(2026, 9, 14, tzinfo=UTC)
    for index in range(6):
        _item(
            session,
            f"valid_{index}",
            "person_1",
            "AAA" if index % 2 == 0 else "BBB",
            base + timedelta(days=index * 7),
            f"statement {index}",
        )
    result = PersonImpactService(session, market_provider=FakeProvider()).rebuild_person("person_1")
    profile = result["profile"]
    assert profile.valid_sample_count == 6
    assert profile.hit_rate is not None
    assert profile.stability_score is not None
    assert profile.uncertainty != "样本不足"


def test_duplicate_event_is_idempotent_and_workspace_isolated() -> None:
    session = _session()
    _seed_person(session)
    base = datetime(2026, 9, 14, tzinfo=UTC)
    _item(session, "same", "person_1", "AAA", base)
    service = PersonImpactService(session, market_provider=FakeProvider())
    service.rebuild_person("person_1")
    service.rebuild_person("person_1")
    assert session.scalar(
        select(InvestmentPersonImpactEvent).where(
            InvestmentPersonImpactEvent.source_item_id == "same"
        )
    )
    assert len(list(session.scalars(select(InvestmentPersonImpactEvent)))) == 1
    other = InvestmentPersonSource(
        id="person_other", workspace_id="ws_other", platform="x", handle="analyst"
    )
    session.add(Workspace(id="ws_other", name="Other"))
    session.add(other)
    session.commit()
    assert (
        PersonImpactService(session, market_provider=FakeProvider()).list_events(
            "ws_other", "person_other"
        )
        == []
    )


def test_rebuild_does_not_turn_first_cluster_event_into_overlap() -> None:
    session = _session()
    _seed_person(session)
    base = datetime(2026, 9, 14, tzinfo=UTC)
    _item(session, "cluster_a", "person_1", "AAA", base, "same statement")
    _item(session, "cluster_b", "person_1", "AAA", base, "same statement")
    service = PersonImpactService(session, market_provider=FakeProvider())
    service.rebuild_person("person_1")
    service.rebuild_person("person_1")
    events = list(
        session.scalars(
            select(InvestmentPersonImpactEvent).order_by(InvestmentPersonImpactEvent.source_item_id)
        )
    )
    assert [event.window_overlap for event in events] == [False, True]


def test_provider_error_and_source_layer_filter_are_explicit() -> None:
    session = _session()
    _seed_person(session)
    now = datetime(2026, 9, 14, tzinfo=UTC)
    _item(session, "good", "person_1", "AAA", now)
    ignored = _item(session, "ignored", "person_1", "AAA", now)
    ignored.source_layer = "news_confirmation"
    session.commit()
    result = PersonImpactService(session, market_provider=FakeProvider(fail=True)).rebuild_person(
        "person_1"
    )
    assert result["profile"].sample_count == 1
    event = session.scalar(select(InvestmentPersonImpactEvent))
    assert event is not None
    assert event.event_status == "insufficient_data"
    assert "provider unavailable" in (event.exclusion_reason or "")


def test_missing_bars_remain_insufficient_data() -> None:
    session = _session()
    _seed_person(session)
    _item(session, "missing_bars", "person_1", "AAA", datetime(2026, 9, 14, tzinfo=UTC))
    result = PersonImpactService(session, market_provider=EmptyProvider()).rebuild_person(
        "person_1"
    )
    assert result["profile"].valid_sample_count == 0
    event = session.scalar(select(InvestmentPersonImpactEvent))
    assert event is not None
    assert event.event_status == "insufficient_data"


def test_profile_can_be_loaded_after_rebuild() -> None:
    session = _session()
    _seed_person(session)
    _item(session, "one", "person_1", "AAA", datetime(2026, 9, 14, tzinfo=UTC))
    PersonImpactService(session, market_provider=FakeProvider()).rebuild_person("person_1")
    profile = session.scalar(select(InvestmentPersonImpactProfile))
    assert profile is not None

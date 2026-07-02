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
    wl = InvestmentWatchlist(
        id="wl_1", workspace_id=ws, name="Apple", watch_type="stock", ticker="AAPL"
    )
    session.add(wl)
    session.commit()
    got = session.get(InvestmentWatchlist, "wl_1")
    assert got is not None
    assert got.name == "Apple"
    assert got.enabled is True


def test_create_source_and_next_poll_nullable(session):
    ws = _seed_workspace(session)
    src = InvestmentSource(
        id="src_1",
        workspace_id=ws,
        source_type="rss",
        name="Fed RSS",
        url="https://www.federalreserve.gov/feeds/press_monetary.xml",
        default_info_layer="macro_calendar",
    )
    session.add(src)
    session.commit()
    got = session.get(InvestmentSource, "src_1")
    assert got is not None
    assert got.next_poll_at is None  # explicitly nullable
    assert got.enabled is True
    assert got.config == {}


def test_create_item_defaults(session):
    ws = _seed_workspace(session)
    item = InvestmentItem(
        id="inv_1",
        workspace_id=ws,
        title="10-K",
        info_layer="primary_source",
        source_credibility="official",
        dedupe_key="dk_1",
    )
    session.add(item)
    session.commit()
    got = session.get(InvestmentItem, "inv_1")
    assert got is not None
    assert got.info_layer == "primary_source"
    assert got.action_status == "pending_review"
    assert got.raw_payload == {}


def test_item_dedupe_key_unique_per_workspace(session):
    ws = _seed_workspace(session)
    session.add(
        InvestmentItem(
            id="inv_a",
            workspace_id=ws,
            title="A",
            info_layer="news",
            source_credibility="reliable_media",
            dedupe_key="dk_dup",
        )
    )
    session.commit()
    session.add(
        InvestmentItem(
            id="inv_b",
            workspace_id=ws,
            title="B",
            info_layer="news",
            source_credibility="reliable_media",
            dedupe_key="dk_dup",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_create_claim_and_thesis(session):
    ws = _seed_workspace(session)
    session.add(InvestmentWatchlist(id="wl_1", workspace_id=ws, name="T", watch_type="stock"))
    session.add(
        InvestmentThesis(
            id="th_1",
            workspace_id=ws,
            watchlist_id="wl_1",
            title="thesis",
            status="open",
            confidence="medium",
        )
    )
    session.add(
        InvestmentClaim(
            id="cl_1",
            workspace_id=ws,
            watchlist_id="wl_1",
            thesis_id="th_1",
            claim_text="x",
            verification_status="pending",
        )
    )
    session.commit()
    assert session.get(InvestmentThesis, "th_1") is not None
    assert session.get(InvestmentClaim, "cl_1") is not None
    assert session.get(InvestmentClaim, "cl_1").evidence_doc_ids == []


def test_create_macro_event(session):
    ws = _seed_workspace(session)
    session.add(
        MacroEvent(id="me_1", workspace_id=ws, title="CPI", source_name="BLS", importance="high")
    )
    session.commit()
    assert session.get(MacroEvent, "me_1") is not None

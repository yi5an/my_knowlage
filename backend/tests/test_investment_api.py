"""API-level tests for the investment endpoints.

Overrides the DB session dependency so the whole stack runs against an
in-memory SQLite database. No mocks of investment data: the dashboard counts
come from real rows inserted via the API.
"""

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base, get_db_session
from app.infrastructure.models import (
    InvestmentDigestSnapshot,
    InvestmentFact,
    InvestmentItem,
    InvestmentSignal,
    InvestmentTheme,
    TaskJob,
    Workspace,
)
from app.main import app
from app.services.investment.fact_extraction import (
    INVESTMENT_FACT_EXTRACTION_JOB_TYPE,
    InvestmentFactExtractionItem,
    InvestmentFactExtractionSchema,
    InvestmentFactJobHandler,
)
from app.services.investment.investment_dependencies import get_investment_service
from app.services.investment.service import InvestmentService
from app.services.structured_output import MockStructuredOutputClient


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
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


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def _override_session() -> Generator[Session, None, None]:
        yield db_session

    def _override_service() -> InvestmentService:
        return InvestmentService(session=db_session)

    app.dependency_overrides[get_db_session] = _override_session
    app.dependency_overrides[get_investment_service] = _override_service
    yield TestClient(app)
    app.dependency_overrides.clear()


# --- watchlist -------------------------------------------------------------


def test_create_and_list_watchlist(client: TestClient):
    resp = client.post(
        "/api/v1/investment/watchlist",
        json={"name": "Apple", "watch_type": "stock", "ticker": "AAPL"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Apple"
    assert body["ticker"] == "AAPL"
    assert body["workspace_id"] == "ws_default"

    listed = client.get("/api/v1/investment/watchlist")
    assert listed.status_code == 200
    assert any(w["name"] == "Apple" for w in listed.json())


def test_update_watchlist(client: TestClient):
    created = client.post(
        "/api/v1/investment/watchlist", json={"name": "TSLA", "ticker": "TSLA"}
    ).json()
    patched = client.patch(
        f"/api/v1/investment/watchlist/{created['id']}",
        json={"importance": "high", "notes": "watch earnings"},
    )
    assert patched.status_code == 200
    assert patched.json()["importance"] == "high"
    assert patched.json()["notes"] == "watch earnings"


def test_bind_source_to_watchlist_and_filter_items(
    client: TestClient,
):
    watchlist = client.post(
        "/api/v1/investment/watchlist",
        json={"name": "NVIDIA", "watch_type": "company", "ticker": "NVDA"},
    ).json()
    source = client.post(
        "/api/v1/investment/sources",
        json={
            "source_type": "x_web",
            "name": "NVIDIA X",
            "config": {"mode": "account", "username": "nvidia"},
            "poll_interval_seconds": 900,
        },
    ).json()
    other_source = client.post(
        "/api/v1/investment/sources",
        json={
            "source_type": "x_web",
            "name": "Elon X",
            "config": {"mode": "account", "username": "elonmusk"},
            "poll_interval_seconds": 900,
        },
    ).json()

    bind = client.post(
        f"/api/v1/investment/watchlist/{watchlist['id']}/sources/{source['id']}"
    )
    duplicate_bind = client.post(
        f"/api/v1/investment/watchlist/{watchlist['id']}/sources/{source['id']}"
    )

    assert bind.status_code == 200, bind.text
    assert duplicate_bind.status_code == 200, duplicate_bind.text
    assert bind.json()["default_watchlist_ids"] == [watchlist["id"]]
    assert duplicate_bind.json()["default_watchlist_ids"] == [watchlist["id"]]

    sources = client.get(f"/api/v1/investment/watchlist/{watchlist['id']}/sources")
    assert sources.status_code == 200
    assert [s["id"] for s in sources.json()] == [source["id"]]

    imported_nvda = client.post(
        "/api/v1/investment/import/x-posts",
        json={
            "source_id": source["id"],
            "collector_id": "collector_test",
            "items": [
                {
                    "tweet_id": "2075367885438890135",
                    "author_username": "nvidia",
                    "text": "NVIDIA announces a new AI platform",
                    "published_at": "2026-07-14T00:00:00Z",
                    "url": "https://x.com/nvidia/status/2075367885438890135",
                    "metrics": {"like_count": 10},
                    "media": [],
                }
            ],
        },
    )
    imported_other = client.post(
        "/api/v1/investment/import/x-posts",
        json={
            "source_id": other_source["id"],
            "collector_id": "collector_test",
            "items": [
                {
                    "tweet_id": "2075367885438890136",
                    "author_username": "elonmusk",
                    "text": "Tesla unrelated post",
                    "published_at": "2026-07-14T00:00:00Z",
                    "url": "https://x.com/elonmusk/status/2075367885438890136",
                    "metrics": {"like_count": 2},
                    "media": [],
                }
            ],
        },
    )
    assert imported_nvda.status_code == 200, imported_nvda.text
    assert imported_other.status_code == 200, imported_other.text

    filtered = client.get(f"/api/v1/investment/items?watchlist_id={watchlist['id']}")
    assert filtered.status_code == 200
    assert [item["source_id"] for item in filtered.json()] == [source["id"]]
    assert filtered.json()[0]["title"] == "@nvidia: NVIDIA announces a new AI platform"

    unbind = client.delete(
        f"/api/v1/investment/watchlist/{watchlist['id']}/sources/{source['id']}"
    )
    assert unbind.status_code == 200
    assert unbind.json()["default_watchlist_ids"] == []

    assert client.get(f"/api/v1/investment/items?watchlist_id={watchlist['id']}").json() == []


def test_list_item_facts(client: TestClient, db_session: Session):
    item = client.post(
        "/api/v1/investment/items",
        json={
            "title": "NVIDIA announces platform",
            "source_url": "https://x.com/nvidia/status/1",
        },
    ).json()
    db_session.add(
        InvestmentFact(
            id="fact_api",
            workspace_id="ws_default",
            source_item_id=item["id"],
            fact_text="NVIDIA announced a platform.",
            fact_text_zh="英伟达宣布了一个平台。",
            fact_type="company_update",
            entities=["NVIDIA"],
            evidence_url="https://x.com/nvidia/status/1",
            evidence_excerpt="NVIDIA announces platform",
            confidence=0.8,
            verification_status="pending",
        )
    )
    db_session.commit()

    response = client.get(f"/api/v1/investment/items/{item['id']}/facts")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "fact_api",
            "workspace_id": "ws_default",
            "source_item_id": item["id"],
            "watchlist_id": None,
            "fact_text": "NVIDIA announced a platform.",
            "fact_text_zh": "英伟达宣布了一个平台。",
            "fact_type": "company_update",
            "entities": ["NVIDIA"],
            "evidence_url": "https://x.com/nvidia/status/1",
            "evidence_excerpt": "NVIDIA announces platform",
            "evidence_timestamp": None,
            "confidence": 0.8,
            "verification_status": "pending",
            "created_at": response.json()[0]["created_at"],
            "updated_at": response.json()[0]["updated_at"],
        }
    ]


def test_list_items_can_filter_by_theme(client: TestClient, db_session: Session):
    theme = InvestmentTheme(
        id="theme_ai",
        workspace_id="ws_default",
        name="AI 算力",
        theme_type="sector",
        keywords=["NVIDIA"],
        entities=["NVIDIA"],
        tickers=["NVDA"],
    )
    matching = InvestmentItem(
        id="inv_theme_match",
        workspace_id="ws_default",
        theme_id=theme.id,
        dedupe_key="theme_match",
        title="NVIDIA AI factories need more power",
        info_layer="opinion",
        source_credibility="personal_opinion",
    )
    other = InvestmentItem(
        id="inv_theme_other",
        workspace_id="ws_default",
        dedupe_key="theme_other",
        title="Unrelated macro note",
        info_layer="macro_calendar",
        source_credibility="official",
    )
    db_session.add_all([theme, matching, other])
    db_session.commit()

    response = client.get("/api/v1/investment/items?theme_id=theme_ai")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == ["inv_theme_match"]
    assert response.json()[0]["theme_id"] == "theme_ai"


def test_list_facts_can_filter_by_source_watchlist_and_status(
    client: TestClient, db_session: Session
):
    watchlist = client.post(
        "/api/v1/investment/watchlist",
        json={"name": "AI Infra", "watch_type": "theme"},
    ).json()
    source = client.post(
        "/api/v1/investment/sources",
        json={
            "source_type": "x_web",
            "name": "NVIDIA X",
            "config": {"mode": "account", "username": "nvidia"},
        },
    ).json()
    other_source = client.post(
        "/api/v1/investment/sources",
        json={
            "source_type": "x_web",
            "name": "Macro X",
            "config": {"mode": "keyword", "query": "fed rates"},
        },
    ).json()
    item = client.post(
        "/api/v1/investment/items",
        json={
            "source_id": source["id"],
            "title": "NVIDIA announces platform",
            "source_url": "https://x.com/nvidia/status/1",
        },
    ).json()
    verified_item = client.post(
        "/api/v1/investment/items",
        json={
            "source_id": source["id"],
            "title": "NVIDIA verifies guidance",
            "source_url": "https://x.com/nvidia/status/2",
        },
    ).json()
    other_item = client.post(
        "/api/v1/investment/items",
        json={
            "source_id": other_source["id"],
            "title": "Fed announces policy",
            "source_url": "https://x.com/fed/status/1",
        },
    ).json()
    db_session.add_all(
        [
            InvestmentFact(
                id="fact_source_pending",
                workspace_id="ws_default",
                source_item_id=item["id"],
                watchlist_id=watchlist["id"],
                fact_text="NVIDIA announced a platform.",
                fact_type="company_update",
                evidence_url="https://x.com/nvidia/status/1",
                evidence_excerpt="NVIDIA announces platform",
                confidence=0.9,
                verification_status="pending",
            ),
            InvestmentFact(
                id="fact_source_verified",
                workspace_id="ws_default",
                source_item_id=verified_item["id"],
                watchlist_id=watchlist["id"],
                fact_text="NVIDIA verified guidance.",
                fact_type="company_update",
                evidence_url="https://x.com/nvidia/status/2",
                evidence_excerpt="NVIDIA verifies guidance",
                confidence=0.8,
                verification_status="verified",
            ),
            InvestmentFact(
                id="fact_other_source",
                workspace_id="ws_default",
                source_item_id=other_item["id"],
                fact_text="Fed announced policy.",
                fact_type="policy_update",
                evidence_url="https://x.com/fed/status/1",
                evidence_excerpt="Fed announces policy",
                confidence=0.7,
                verification_status="pending",
            ),
        ]
    )
    db_session.commit()

    by_source = client.get(
        f"/api/v1/investment/facts?source_id={source['id']}&verification_status=pending"
    )

    assert by_source.status_code == 200
    assert [fact["id"] for fact in by_source.json()] == ["fact_source_pending"]

    by_watchlist = client.get(
        f"/api/v1/investment/facts?watchlist_id={watchlist['id']}"
    )

    assert by_watchlist.status_code == 200
    assert [fact["id"] for fact in by_watchlist.json()] == [
        "fact_source_pending",
        "fact_source_verified",
    ]


# --- item ------------------------------------------------------------------


def test_create_and_list_item(client: TestClient):
    resp = client.post(
        "/api/v1/investment/items",
        json={
            "title": "Apple 10-K filing",
            "info_layer": "primary_source",
            "source_credibility": "official",
            "source_url": "https://sec.gov/x",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["title"] == "Apple 10-K filing"
    assert body["action_status"] == "pending_review"
    assert body["dedupe_key"]  # auto-computed

    listed = client.get("/api/v1/investment/items?info_layer=primary_source")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    # filter by a different layer returns nothing
    empty = client.get("/api/v1/investment/items?info_layer=opinion")
    assert empty.json() == []


def test_create_item_enqueues_translation_job(
    client: TestClient,
    db_session: Session,
):
    resp = client.post(
        "/api/v1/investment/items",
        json={
            "title": "AI capex thread",
            "summary": "Hyperscaler capex remains strong.",
            "info_layer": "opinion",
            "source_credibility": "unverified",
            "source_url": "https://x.com/investor/status/123",
        },
    )

    assert resp.status_code == 201, resp.text
    jobs = list(
        db_session.query(TaskJob).filter(TaskJob.job_type == "investment_translation")
    )
    assert len(jobs) == 1
    assert jobs[0].status == "pending"
    assert jobs[0].workspace_id == "ws_default"
    assert jobs[0].target_type == "investment_item"
    assert jobs[0].input == {"workspace_id": "ws_default", "item_id": resp.json()["id"]}


def test_x_import_fact_extraction_flow_can_be_processed_and_read(
    client: TestClient,
    db_session: Session,
):
    watchlist = client.post(
        "/api/v1/investment/watchlist",
        json={"name": "POTUS", "watch_type": "official_account", "keywords": ["policy"]},
    ).json()
    thesis = client.post(
        "/api/v1/investment/theses",
        json={
            "watchlist_id": watchlist["id"],
            "title": "POTUS policy changes can move markets",
            "body": "Track new policy announcements from official POTUS sources.",
        },
    ).json()
    source = client.post(
        "/api/v1/investment/sources",
        json={
            "source_type": "x_web",
            "name": "POTUS",
            "config": {"mode": "account", "username": "POTUS"},
            "default_watchlist_ids": [watchlist["id"]],
            "poll_interval_seconds": 900,
        },
    ).json()

    response = client.post(
        "/api/v1/investment/import/x-posts",
        json={
            "source_id": source["id"],
            "collector_id": "collector_test",
            "items": [
                {
                    "tweet_id": "2075367885438890137",
                    "author_username": "POTUS",
                    "text": "The President announced a new policy.",
                    "published_at": "2026-07-14T00:00:00Z",
                    "url": "https://x.com/POTUS/status/2075367885438890137",
                    "metrics": {"like_count": 5},
                    "media": [],
                }
            ],
        },
    )

    assert response.status_code == 200, response.text
    jobs = list(
        db_session.query(TaskJob).filter(
            TaskJob.job_type == INVESTMENT_FACT_EXTRACTION_JOB_TYPE
        )
    )
    assert len(jobs) == 1
    assert jobs[0].target_type == "investment_source"
    assert jobs[0].target_id == source["id"]
    assert jobs[0].input == {"workspace_id": "ws_default", "source_id": source["id"]}

    item = client.get(f"/api/v1/investment/items?source_id={source['id']}").json()[0]
    out = InvestmentFactJobHandler().handle(
        jobs[0],
        db_session,
        MockStructuredOutputClient(
            outputs={
                InvestmentFactExtractionSchema: InvestmentFactExtractionSchema(
                    facts=[
                        InvestmentFactExtractionItem(
                            fact_text="The President announced a new policy.",
                            fact_text_zh="总统宣布了一项新政策。",
                            fact_type="policy_update",
                            entities=["POTUS"],
                            evidence_excerpt="The President announced a new policy.",
                            confidence=0.8,
                        )
                    ]
                )
            }
        ),
    )

    assert out["facts_created"] == 1
    facts = client.get(f"/api/v1/investment/items/{item['id']}/facts")
    assert facts.status_code == 200
    assert facts.json()[0]["fact_text_zh"] == "总统宣布了一项新政策。"
    assert facts.json()[0]["evidence_url"] == item["source_url"]
    assert facts.json()[0]["confidence"] == 0.8

    signals = client.get("/api/v1/investment/signals")
    assert signals.status_code == 200
    assert signals.json()[0]["signal_type"] == "policy_update"
    assert signals.json()[0]["fact_ids"] == [facts.json()[0]["id"]]
    assert signals.json()[0]["source_count"] == 1

    claims = client.get(
        f"/api/v1/investment/claims?watchlist_id={watchlist['id']}&verification_status=pending"
    )
    assert claims.status_code == 200
    assert len(claims.json()) == 1
    assert claims.json()[0]["thesis_id"] == thesis["id"]
    assert claims.json()[0]["claim_text"] == "总统宣布了一项新政策。"


def test_list_signals_can_filter_by_theme(client: TestClient, db_session: Session):
    db_session.add_all(
        [
            InvestmentTheme(
                id="theme_ai",
                workspace_id="ws_default",
                name="AI 算力",
                theme_type="sector",
                keywords=["NVIDIA"],
                entities=["NVIDIA"],
                tickers=["NVDA"],
            ),
            InvestmentSignal(
                id="sig_ai",
                workspace_id="ws_default",
                theme_id="theme_ai",
                title="NVIDIA / capex_signal",
                summary="AI capex signal",
                signal_type="capex_signal",
                first_seen_at=datetime.now(UTC),
                last_seen_at=datetime.now(UTC),
                source_count=2,
                fact_ids=[],
                item_ids=[],
                confidence=0.8,
                information_edge_score=0.7,
            ),
            InvestmentSignal(
                id="sig_global",
                workspace_id="ws_default",
                title="Global / opinion",
                summary="Unscoped chatter",
                signal_type="opinion",
                first_seen_at=datetime.now(UTC),
                last_seen_at=datetime.now(UTC),
                source_count=1,
                fact_ids=[],
                item_ids=[],
                confidence=0.4,
                information_edge_score=0.2,
            ),
        ]
    )
    db_session.commit()

    response = client.get("/api/v1/investment/signals?theme_id=theme_ai")

    assert response.status_code == 200
    assert [signal["id"] for signal in response.json()] == ["sig_ai"]
    assert response.json()[0]["theme_id"] == "theme_ai"


def test_item_response_includes_attachments_from_raw_payload(client: TestClient):
    resp = client.post(
        "/api/v1/investment/items",
        json={
            "title": "Fed projections",
            "raw_payload": {
                "attachments": [
                    {
                        "title": "Accessible Materials",
                        "url": "https://www.federalreserve.gov/monetarypolicy/projections.htm",
                        "content_type": "html",
                        "text_excerpt": "Median federal funds rate 3.6 percent.",
                    }
                ]
            },
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["attachments"] == [
        {
            "title": "Accessible Materials",
            "url": "https://www.federalreserve.gov/monetarypolicy/projections.htm",
            "content_type": "html",
            "text_excerpt": "Median federal funds rate 3.6 percent.",
        }
    ]


def test_update_item(client: TestClient):
    item = client.post("/api/v1/investment/items", json={"title": "x"}).json()
    patched = client.patch(
        f"/api/v1/investment/items/{item['id']}",
        json={"importance": "high", "action_status": "researched"},
    )
    assert patched.status_code == 200
    assert patched.json()["importance"] == "high"
    assert patched.json()["action_status"] == "researched"


def test_translate_items_returns_structured_error_on_llm_failure(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    client.post("/api/v1/investment/items", json={"title": "FOMC statement"})

    class _BoomClient:
        def generate(self, prompt, schema):  # noqa: ANN001
            raise RuntimeError("auth_unavailable")

    monkeypatch.setattr(
        "app.api.v1.investment._build_llm_client",
        lambda: _BoomClient(),
    )

    resp = client.post("/api/v1/investment/items/translate?limit=100")

    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "translation_failed"
    assert "investment translation failed" in resp.json()["error"]["message"]


# --- source + poll ---------------------------------------------------------


def test_create_source_and_poll_enqueues_job(client: TestClient, db_session: Session):
    src = client.post(
        "/api/v1/investment/sources",
        json={
            "source_type": "rss",
            "name": "Fed RSS",
            "url": "https://www.federalreserve.gov/feeds/press_monetary.xml",
            "default_info_layer": "macro_calendar",
        },
    ).json()
    assert src["source_type"] == "rss"

    poll = client.post(f"/api/v1/investment/sources/{src['id']}/poll")
    assert poll.status_code == 200, poll.text
    job_body = poll.json()
    assert job_body["status"] == "pending"
    job_id = job_body["job_id"]

    # a real pending TaskJob row exists
    job = db_session.get(TaskJob, job_id)
    assert job is not None
    assert job.job_type == "investment_fetch"
    assert job.target_id == src["id"]
    assert job.status == "pending"


def test_google_news_rss_source_is_marked_disabled_when_x_first(client: TestClient):
    resp = client.post(
        "/api/v1/investment/sources",
        json={
            "source_type": "rss",
            "name": "Google News - Fed",
            "url": "https://news.google.com/rss/search?q=Federal%20Reserve",
        },
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["enabled"] is False
    assert "Google News fallback disabled" in body["last_error"]


def test_create_default_x_sources_is_idempotent(client: TestClient):
    first = client.post("/api/v1/investment/sources/defaults")

    assert first.status_code == 201, first.text
    first_body = first.json()
    assert [source["name"] for source in first_body] == [
        "POTUS 官方",
        "特朗普个人",
        "NVIDIA 官方",
        "马斯克",
        "美联储主题",
    ]
    assert first_body[0]["config"] == {
        "mode": "account",
        "username": "POTUS",
        "max_items_per_poll": 50,
    }
    assert first_body[-1]["config"]["mode"] == "keyword"

    second = client.post("/api/v1/investment/sources/defaults")

    assert second.status_code == 201
    listed = client.get("/api/v1/investment/sources")
    assert listed.status_code == 200
    assert len(listed.json()) == 5
    assert [source["id"] for source in second.json()] == [
        source["id"] for source in first_body
    ]


def test_poll_is_idempotent_while_pending(client: TestClient, db_session: Session):
    src = client.post(
        "/api/v1/investment/sources", json={"source_type": "rss", "name": "s"}
    ).json()
    first = client.post(f"/api/v1/investment/sources/{src['id']}/poll").json()
    second = client.post(f"/api/v1/investment/sources/{src['id']}/poll").json()
    assert first["job_id"] == second["job_id"]


def test_get_job_projects_output(db_session: Session, client: TestClient):
    src = client.post(
        "/api/v1/investment/sources", json={"source_type": "rss", "name": "s2"}
    ).json()
    job_id = client.post(f"/api/v1/investment/sources/{src['id']}/poll").json()["job_id"]
    # simulate the worker having run the job
    job = db_session.get(TaskJob, job_id)
    job.status = "succeeded"
    job.output = {"items_seen": 5, "items_created": 3, "items_skipped": 2}
    db_session.commit()

    got = client.get(f"/api/v1/investment/jobs/{job_id}")
    assert got.status_code == 200
    body = got.json()
    assert body["status"] == "succeeded"
    assert body["items_seen"] == 5
    assert body["items_created"] == 3
    assert body["source_id"] == src["id"]


# --- thesis / claim --------------------------------------------------------


def test_create_thesis_and_claim(client: TestClient):
    wl = client.post(
        "/api/v1/investment/watchlist", json={"name": "NVDA", "ticker": "NVDA"}
    ).json()
    thesis = client.post(
        "/api/v1/investment/theses",
        json={"watchlist_id": wl["id"], "title": "AI demand stays strong"},
    ).json()
    assert thesis["status"] == "open"

    claim = client.post(
        "/api/v1/investment/claims",
        json={
            "watchlist_id": wl["id"],
            "thesis_id": thesis["id"],
            "claim_text": "Data center revenue doubles",
            "required_evidence": ["10-K segment data"],
        },
    ).json()
    assert claim["verification_status"] == "pending"
    assert claim["required_evidence"] == ["10-K segment data"]

    listed = client.get("/api/v1/investment/claims")
    assert len(listed.json()) == 1


def test_claim_status_action_updates_status_summary_and_thesis(client: TestClient):
    wl = client.post(
        "/api/v1/investment/watchlist", json={"name": "NVDA", "ticker": "NVDA"}
    ).json()
    thesis = client.post(
        "/api/v1/investment/theses",
        json={"watchlist_id": wl["id"], "title": "AI demand stays strong"},
    ).json()
    claim = client.post(
        "/api/v1/investment/claims",
        json={
            "watchlist_id": wl["id"],
            "claim_text": "Data center revenue doubles",
            "required_evidence": ["10-K segment data"],
        },
    ).json()

    response = client.post(
        f"/api/v1/investment/claims/{claim['id']}/status",
        json={
            "verification_status": "refuted",
            "verification_summary": "最新财报没有支持收入翻倍。",
            "thesis_id": thesis["id"],
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["verification_status"] == "refuted"
    assert body["verification_summary"] == "最新财报没有支持收入翻倍。"
    assert body["thesis_id"] == thesis["id"]


# --- dashboard (real counts, no sample data) -------------------------------


def test_dashboard_reflects_real_counts(client: TestClient, db_session: Session):
    # empty workspace -> all zero
    empty = client.get("/api/v1/investment/dashboard").json()
    assert empty == {
        "pending_review_count": 0,
        "pending_claims_count": 0,
        "theses_challenged_count": 0,
        "today_primary_count": 0,
        "today_macro_count": 0,
        "untranslated_count": 0,
        "unextracted_count": 0,
        "unsignaled_count": 0,
        "failed_job_count": 0,
    }

    client.post(
        "/api/v1/investment/items",
        json={"title": "a", "action_status": "pending_review"},
    )
    client.post(
        "/api/v1/investment/items",
        json={"title": "b", "action_status": "tracking", "thesis_impact": "weakens"},
    )
    suggested = client.post(
        "/api/v1/investment/items",
        json={"title": "suggested challenge", "action_status": "tracking"},
    ).json()
    suggested_item = db_session.get(InvestmentItem, suggested["id"])
    assert suggested_item is not None
    suggested_item.suggested_thesis_impact = "contradicts"
    db_session.commit()
    client.post("/api/v1/investment/claims", json={"claim_text": "c"})
    translated = client.post(
        "/api/v1/investment/items",
        json={"title": "translated", "summary": "done", "action_status": "tracking"},
    ).json()
    translated_item = db_session.get(InvestmentItem, translated["id"])
    assert translated_item is not None
    translated_item.title_zh = "已翻译"
    translated_item.summary_zh = "完成"
    db_session.add(
        InvestmentFact(
            id="fact_ops",
            workspace_id="ws_default",
            source_item_id=translated["id"],
            fact_text="ops fact",
            fact_type="ops",
            evidence_excerpt="ops fact",
            confidence=0.8,
            verification_status="pending",
        )
    )
    db_session.add(
        TaskJob(
            id="job_ops_failed",
            workspace_id="ws_default",
            job_type="investment_fact_extract",
            target_type="investment_item",
            target_id=suggested["id"],
            status="failed",
            error_message="boom",
        )
    )
    db_session.commit()

    filled = client.get("/api/v1/investment/dashboard").json()
    assert filled["pending_review_count"] == 1
    assert filled["theses_challenged_count"] == 2
    assert filled["pending_claims_count"] == 1
    assert filled["untranslated_count"] == 3
    assert filled["unextracted_count"] == 3
    assert filled["unsignaled_count"] == 1
    assert filled["failed_job_count"] == 1


# --- macro-events & digest -------------------------------------------------


def test_macro_events_only_returns_macro_calendar_layer(client: TestClient):
    now_iso = datetime.now(UTC).isoformat()
    # a macro item and a non-macro item
    client.post(
        "/api/v1/investment/items",
        json={
            "title": "FOMC statement",
            "info_layer": "macro_calendar",
            "importance": "high",
            "published_at": now_iso,
        },
    )
    client.post(
        "/api/v1/investment/items",
        json={
            "title": "earnings call",
            "info_layer": "primary_source",
            "published_at": now_iso,
        },
    )

    resp = client.get("/api/v1/investment/macro-events")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["info_layer"] == "macro_calendar"
    assert body[0]["title"] == "FOMC statement"


def test_macro_events_importance_filter(client: TestClient):
    now_iso = datetime.now(UTC).isoformat()
    client.post(
        "/api/v1/investment/items",
        json={
            "title": "high impact",
            "info_layer": "macro_calendar",
            "importance": "high",
            "published_at": now_iso,
        },
    )
    client.post(
        "/api/v1/investment/items",
        json={
            "title": "low impact",
            "info_layer": "macro_calendar",
            "importance": "low",
            "published_at": now_iso,
        },
    )

    only_high = client.get("/api/v1/investment/macro-events?importance=high").json()
    assert len(only_high) == 1
    assert only_high[0]["importance"] == "high"


def test_digest_aggregates_counts_and_lists(client: TestClient, db_session: Session):
    now_iso = datetime.now(UTC).isoformat()
    client.post(
        "/api/v1/investment/items",
        json={
            "title": "a",
            "action_status": "pending_review",
            "importance": "high",
            "published_at": now_iso,
        },
    )
    client.post(
        "/api/v1/investment/items",
        json={
            "title": "b",
            "thesis_impact": "weakens",
            "action_status": "tracking",
            "published_at": now_iso,
        },
    )
    client.post("/api/v1/investment/claims", json={"claim_text": "claim to verify"})
    item = client.post(
        "/api/v1/investment/items",
        json={
            "title": "NVIDIA platform",
            "source_url": "https://x.com/nvidia/status/1",
            "action_status": "tracking",
        },
    ).json()
    db_session.add(
        InvestmentFact(
            id="fact_digest",
            workspace_id="ws_default",
            source_item_id=item["id"],
            fact_text="NVIDIA announced a platform.",
            fact_text_zh="英伟达宣布了一个平台。",
            fact_type="company_update",
            entities=["NVIDIA"],
            evidence_url="https://x.com/nvidia/status/1",
            evidence_excerpt="NVIDIA platform",
            confidence=0.8,
            verification_status="pending",
        )
    )
    db_session.add(
        InvestmentSignal(
            id="sig_digest",
            workspace_id="ws_default",
            title="NVIDIA / company_update",
            summary="英伟达宣布了一个平台。",
            signal_type="company_update",
            first_seen_at=datetime.now(UTC),
            last_seen_at=datetime.now(UTC),
            source_count=1,
            fact_ids=["fact_digest"],
            item_ids=[item["id"]],
            confidence=0.8,
            status="tracking",
        )
    )
    db_session.commit()

    resp = client.get("/api/v1/investment/digest")
    assert resp.status_code == 200
    body = resp.json()
    assert body["counts"]["pending_review_count"] == 1
    assert body["counts"]["theses_challenged_count"] == 1
    assert body["counts"]["pending_claims_count"] == 1
    # today_highlights includes today's items; challenged_items has the weakens one
    titles = [h["title"] for h in body["today_highlights"]]
    assert "a" in titles
    assert any(c["claim_text"] == "claim to verify" for c in body["pending_claims"])
    assert any(i["title"] == "b" for i in body["challenged_items"])
    assert body["pending_facts"][0]["id"] == "fact_digest"
    assert body["early_signals"][0]["id"] == "sig_digest"


def test_digest_can_be_scoped_to_watchlist(client: TestClient, db_session: Session):
    wl_ai = client.post(
        "/api/v1/investment/watchlist",
        json={"name": "AI Infra", "watch_type": "theme"},
    ).json()
    wl_macro = client.post(
        "/api/v1/investment/watchlist",
        json={"name": "Macro", "watch_type": "macro"},
    ).json()
    src_ai = client.post(
        "/api/v1/investment/sources",
        json={
            "source_type": "x_web",
            "name": "NVIDIA",
            "config": {"mode": "account", "username": "nvidia"},
            "default_watchlist_ids": [wl_ai["id"]],
            "poll_interval_seconds": 900,
        },
    ).json()
    src_macro = client.post(
        "/api/v1/investment/sources",
        json={
            "source_type": "x_web",
            "name": "POTUS",
            "config": {"mode": "account", "username": "POTUS"},
            "default_watchlist_ids": [wl_macro["id"]],
            "poll_interval_seconds": 900,
        },
    ).json()
    ai_item = client.post(
        "/api/v1/investment/items",
        json={
            "title": "AI data center demand",
            "source_id": src_ai["id"],
            "action_status": "pending_review",
            "published_at": datetime.now(UTC).isoformat(),
        },
    ).json()
    macro_item = client.post(
        "/api/v1/investment/items",
        json={
            "title": "Macro policy note",
            "source_id": src_macro["id"],
            "action_status": "pending_review",
            "published_at": datetime.now(UTC).isoformat(),
        },
    ).json()
    client.post(
        "/api/v1/investment/claims",
        json={"watchlist_id": wl_ai["id"], "claim_text": "AI claim"},
    )
    client.post(
        "/api/v1/investment/claims",
        json={"watchlist_id": wl_macro["id"], "claim_text": "Macro claim"},
    )
    db_session.add(
        InvestmentFact(
            id="fact_ai_digest",
            workspace_id="ws_default",
            source_item_id=ai_item["id"],
            watchlist_id=wl_ai["id"],
            fact_text="AI demand remains strong.",
            fact_type="demand_signal",
            entities=["NVIDIA"],
            evidence_url="https://x.com/nvidia/status/1",
            evidence_excerpt="AI demand remains strong.",
            confidence=0.8,
            verification_status="pending",
        )
    )
    db_session.add(
        InvestmentFact(
            id="fact_macro_digest",
            workspace_id="ws_default",
            source_item_id=macro_item["id"],
            watchlist_id=wl_macro["id"],
            fact_text="Macro policy changed.",
            fact_type="policy_update",
            entities=["POTUS"],
            evidence_url="https://x.com/POTUS/status/1",
            evidence_excerpt="Macro policy changed.",
            confidence=0.7,
            verification_status="pending",
        )
    )
    db_session.add(
        InvestmentSignal(
            id="sig_ai_digest",
            workspace_id="ws_default",
            watchlist_id=wl_ai["id"],
            title="NVIDIA / demand_signal",
            summary="AI demand remains strong.",
            signal_type="demand_signal",
            first_seen_at=datetime.now(UTC),
            last_seen_at=datetime.now(UTC),
            source_count=1,
            fact_ids=["fact_ai_digest"],
            item_ids=[ai_item["id"]],
            confidence=0.8,
            status="tracking",
        )
    )
    db_session.add(
        InvestmentSignal(
            id="sig_macro_digest",
            workspace_id="ws_default",
            watchlist_id=wl_macro["id"],
            title="POTUS / policy_update",
            summary="Macro policy changed.",
            signal_type="policy_update",
            first_seen_at=datetime.now(UTC),
            last_seen_at=datetime.now(UTC),
            source_count=1,
            fact_ids=["fact_macro_digest"],
            item_ids=[macro_item["id"]],
            confidence=0.7,
            status="tracking",
        )
    )
    db_session.commit()

    body = client.get(f"/api/v1/investment/digest?watchlist_id={wl_ai['id']}").json()

    assert [item["title"] for item in body["today_highlights"]] == [
        "AI data center demand"
    ]
    assert [claim["claim_text"] for claim in body["pending_claims"]] == ["AI claim"]
    assert [fact["id"] for fact in body["pending_facts"]] == ["fact_ai_digest"]
    assert [signal["id"] for signal in body["early_signals"]] == ["sig_ai_digest"]


def test_digest_snapshot_persists_current_digest(client: TestClient, db_session: Session):
    watchlist = client.post(
        "/api/v1/investment/watchlist",
        json={"name": "AI Infra", "watch_type": "theme"},
    ).json()
    source = client.post(
        "/api/v1/investment/sources",
        json={
            "source_type": "x_web",
            "name": "NVIDIA",
            "config": {"mode": "account", "username": "nvidia"},
            "default_watchlist_ids": [watchlist["id"]],
            "poll_interval_seconds": 900,
        },
    ).json()
    item = client.post(
        "/api/v1/investment/items",
        json={
            "title": "AI data center demand",
            "source_id": source["id"],
            "action_status": "pending_review",
            "published_at": datetime.now(UTC).isoformat(),
        },
    ).json()
    db_session.add(
        InvestmentFact(
            id="fact_snapshot",
            workspace_id="ws_default",
            source_item_id=item["id"],
            watchlist_id=watchlist["id"],
            fact_text="AI demand remains strong.",
            fact_type="demand_signal",
            entities=["NVIDIA"],
            evidence_url="https://x.com/nvidia/status/1",
            evidence_excerpt="AI demand remains strong.",
            confidence=0.8,
            verification_status="pending",
        )
    )
    db_session.add(
        InvestmentSignal(
            id="sig_snapshot",
            workspace_id="ws_default",
            watchlist_id=watchlist["id"],
            title="NVIDIA / demand_signal",
            summary="AI demand remains strong.",
            signal_type="demand_signal",
            first_seen_at=datetime.now(UTC),
            last_seen_at=datetime.now(UTC),
            source_count=1,
            fact_ids=["fact_snapshot"],
            item_ids=[item["id"]],
            confidence=0.8,
            status="tracking",
        )
    )
    db_session.commit()

    created = client.post(
        f"/api/v1/investment/digest/snapshots?watchlist_id={watchlist['id']}"
    )

    assert created.status_code == 201, created.text
    body = created.json()
    assert body["watchlist_id"] == watchlist["id"]
    assert body["digest"]["early_signals"][0]["id"] == "sig_snapshot"
    assert body["digest"]["pending_facts"][0]["id"] == "fact_snapshot"

    saved = db_session.get(InvestmentDigestSnapshot, body["id"])
    assert saved is not None
    assert saved.digest["early_signals"][0]["id"] == "sig_snapshot"

    listed = client.get(
        f"/api/v1/investment/digest/snapshots?watchlist_id={watchlist['id']}"
    )
    assert listed.status_code == 200
    assert [snapshot["id"] for snapshot in listed.json()] == [body["id"]]


# --- operational health and task recovery ---------------------------------


def test_investment_health_endpoint_projects_workspace_sources(client: TestClient):
    source = client.post(
        "/api/v1/investment/sources",
        json={
            "source_type": "x_web",
            "name": "Health check source",
            "config": {"mode": "account", "username": "healthcheck"},
            "poll_interval_seconds": 900,
        },
    ).json()

    response = client.get("/api/v1/investment/health?workspace_id=ws_default")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["workspace_id"] == "ws_default"
    assert body["freshness_state"] == "stale"
    assert [entry["source_id"] for entry in body["sources"]] == [source["id"]]


def test_task_health_counts_only_investment_jobs_and_sanitizes_failures(
    client: TestClient,
    db_session: Session,
):
    for job_id, job_type, status in (
        ("health_pending", "investment_translation", "pending"),
        ("health_running", "investment_fact_extract", "running"),
        ("health_succeeded", "investment_classification", "succeeded"),
        ("health_failed", "investment_fetch", "failed"),
    ):
        db_session.add(
            TaskJob(
                id=job_id,
                workspace_id="ws_default",
                job_type=job_type,
                target_type="investment_source",
                target_id="source_health",
                status=status,
                input={"api_key": "must-not-be-returned", "source_id": "source_health"},
                error_message=(
                    "provider password=hunter2 authorization: Bearer top-secret"
                    if status == "failed"
                    else None
                ),
                finished_at=datetime.now(UTC) if status in {"succeeded", "failed"} else None,
            )
        )
    db_session.add(
        TaskJob(
            id="health_unrelated",
            workspace_id="ws_default",
            job_type="youtube_summary",
            target_type="video",
            target_id="video_health",
            status="failed",
            error_message="not part of investment task health",
        )
    )
    db_session.commit()

    response = client.get("/api/v1/investment/tasks/health?workspace_id=ws_default")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["workspace_id"] == "ws_default"
    assert body["pending_count"] == 1
    assert body["running_count"] == 1
    assert body["succeeded_count"] == 1
    assert body["failed_count"] == 1
    assert len(body["recent_failures"]) == 1
    failure = body["recent_failures"][0]
    assert failure["job_id"] == "health_failed"
    assert failure["job_type"] == "investment_fetch"
    assert failure["retryable"] is True
    assert failure["error_message"] == (
        "provider password=[REDACTED] authorization=[REDACTED]"
    )
    assert "input" not in failure
    assert "hunter2" not in response.text
    assert "top-secret" not in response.text
    assert "must-not-be-returned" not in response.text


def test_retry_failed_investment_job_is_workspace_scoped_safe_and_idempotent(
    client: TestClient,
    db_session: Session,
):
    failed = TaskJob(
        id="retry_failed_translation",
        workspace_id="ws_default",
        job_type="investment_translation",
        target_type="investment_source",
        target_id="source_retry",
        status="failed",
        input={
            "workspace_id": "ws_default",
            "source_id": "source_retry",
            "api_key": "secret-key",
            "nested": {"access_token": "secret-token"},
        },
        error_message="timeout",
        finished_at=datetime.now(UTC),
    )
    db_session.add(failed)
    db_session.commit()

    first = client.post(
        "/api/v1/investment/tasks/retry_failed_translation/retry"
        "?workspace_id=ws_default"
    )
    second = client.post(
        "/api/v1/investment/tasks/retry_failed_translation/retry"
        "?workspace_id=ws_default"
    )

    assert first.status_code == 202, first.text
    assert second.status_code == 202, second.text
    assert first.json()["original_job_id"] == failed.id
    assert first.json()["job_id"] == second.json()["job_id"]
    assert first.json()["reused"] is False
    assert second.json()["reused"] is True
    retried = db_session.get(TaskJob, first.json()["job_id"])
    assert retried is not None
    assert retried.status == "pending"
    assert retried.input == {"workspace_id": "ws_default", "source_id": "source_retry"}
    assert db_session.get(TaskJob, failed.id).status == "failed"  # type: ignore[union-attr]

    wrong_workspace = client.post(
        "/api/v1/investment/tasks/retry_failed_translation/retry"
        "?workspace_id=ws_other"
    )
    assert wrong_workspace.status_code == 404


def test_retry_rejects_unsupported_or_non_failed_jobs(
    client: TestClient,
    db_session: Session,
):
    db_session.add_all(
        [
            TaskJob(
                id="retry_unsupported",
                workspace_id="ws_default",
                job_type="youtube_summary",
                target_type="video",
                target_id="video_retry",
                status="failed",
            ),
            TaskJob(
                id="retry_succeeded",
                workspace_id="ws_default",
                job_type="investment_fetch",
                target_type="investment_source",
                target_id="source_done",
                status="succeeded",
            ),
        ]
    )
    db_session.commit()

    unsupported = client.post(
        "/api/v1/investment/tasks/retry_unsupported/retry?workspace_id=ws_default"
    )
    not_failed = client.post(
        "/api/v1/investment/tasks/retry_succeeded/retry?workspace_id=ws_default"
    )

    assert unsupported.status_code == 400
    assert unsupported.json()["error"]["code"] == "unsupported_investment_job_type"
    assert not_failed.status_code == 409
    assert not_failed.json()["error"]["code"] == "investment_job_not_failed"

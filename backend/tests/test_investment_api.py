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
from app.infrastructure.models import TaskJob, Workspace
from app.main import app
from app.services.investment.investment_dependencies import get_investment_service
from app.services.investment.service import InvestmentService


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


# --- dashboard (real counts, no sample data) -------------------------------


def test_dashboard_reflects_real_counts(client: TestClient):
    # empty workspace -> all zero
    empty = client.get("/api/v1/investment/dashboard").json()
    assert empty == {
        "pending_review_count": 0,
        "pending_claims_count": 0,
        "theses_challenged_count": 0,
        "today_primary_count": 0,
        "today_macro_count": 0,
    }

    client.post(
        "/api/v1/investment/items",
        json={"title": "a", "action_status": "pending_review"},
    )
    client.post(
        "/api/v1/investment/items",
        json={"title": "b", "action_status": "tracking", "thesis_impact": "weakens"},
    )
    client.post("/api/v1/investment/claims", json={"claim_text": "c"})

    filled = client.get("/api/v1/investment/dashboard").json()
    assert filled["pending_review_count"] == 1
    assert filled["theses_challenged_count"] == 1
    assert filled["pending_claims_count"] == 1


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


def test_digest_aggregates_counts_and_lists(client: TestClient):
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

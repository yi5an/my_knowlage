from datetime import UTC, datetime

from tests.test_investment_themes_api import _client


def test_source_trace_service_persists_likely_earlier_source() -> None:
    _, session = _client()
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


def test_source_trace_endpoint_lists_persisted_traces() -> None:
    client, session = _client()
    from app.infrastructure.models import InvestmentItem
    from app.services.investment.source_trace_service import SourceTraceService

    earlier = InvestmentItem(
        id="inv_endpoint_earlier",
        workspace_id="ws_default",
        dedupe_key="endpoint-earlier",
        title="NVIDIA Blackwell shipments accelerating",
        source_layer="primary_source",
        published_at=datetime(2026, 7, 15, 8, tzinfo=UTC),
    )
    later = InvestmentItem(
        id="inv_endpoint_later",
        workspace_id="ws_default",
        dedupe_key="endpoint-later",
        title="YouTube: Blackwell shipments are accelerating",
        source_layer="expert_opinion",
        published_at=datetime(2026, 7, 15, 20, tzinfo=UTC),
    )
    session.add_all([earlier, later])
    session.commit()
    SourceTraceService(session).trace_item(later)

    response = client.get(
        "/api/v1/investment/source-traces",
        params={"target_item_id": later.id},
    )

    assert response.status_code == 200, response.text
    assert response.json()[0]["source_item_id"] == earlier.id

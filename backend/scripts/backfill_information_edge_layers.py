"""Backfill source layers and collection timestamps for investment items.

Usage:
    python -m scripts.backfill_information_edge_layers --workspace-id ws_default
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.database import SessionLocal
from app.infrastructure.models import InvestmentItem, InvestmentSource

PRIMARY_SOURCE_TYPES = {
    "sec_edgar",
    "federal_reserve_rss",
    "bls",
    "fred",
    "hkex",
    "cninfo",
}
X_SOURCE_TYPES = {"x_web", "x_rss", "x_nitter", "x_brightdata"}


def _layer_for_item(item: InvestmentItem, source: InvestmentSource | None) -> str:
    source_type = source.source_type if source is not None else None
    if item.info_layer == "primary_source" or source_type in PRIMARY_SOURCE_TYPES:
        return "primary_source"
    if source_type in X_SOURCE_TYPES:
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
    sources: dict[str, InvestmentSource] = {}
    if source_ids:
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

"""Refresh investment signals from existing facts.

Usage:
    python -m scripts.backfill_investment_signals --workspace-id ws_default
"""

from __future__ import annotations

import argparse

from sqlalchemy.orm import Session

from app.infrastructure.database import SessionLocal
from app.services.investment.signal_service import InvestmentSignalService


def refresh_signal_backfill(
    session: Session,
    *,
    workspace_id: str = "ws_default",
    watchlist_id: str | None = None,
) -> dict[str, int]:
    signals = InvestmentSignalService(session).refresh_signals(
        workspace_id=workspace_id,
        watchlist_id=watchlist_id,
    )
    return {"signals_created": len(signals)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-id", default="ws_default")
    parser.add_argument("--watchlist-id")
    args = parser.parse_args()
    with SessionLocal() as session:
        result = refresh_signal_backfill(
            session,
            workspace_id=args.workspace_id,
            watchlist_id=args.watchlist_id,
        )
    print(result)


if __name__ == "__main__":
    main()

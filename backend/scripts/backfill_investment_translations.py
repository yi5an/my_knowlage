"""Backfill Chinese translations for existing investment items.

Usage:
    python -m scripts.backfill_investment_translations --workspace-id ws_default
"""

from __future__ import annotations

import argparse
from typing import Any

from sqlalchemy.orm import Session

from app.infrastructure.database import SessionLocal
from app.services.investment.translation import InvestmentTranslationService
from app.services.research_dependencies import build_llm_client_from_settings


def run_backfill(
    session: Session,
    llm_client: Any,
    *,
    workspace_id: str = "ws_default",
    source_id: str | None = None,
    limit: int = 20,
    batches: int = 1,
    raise_on_failure: bool = False,
) -> dict[str, int]:
    service = InvestmentTranslationService(session=session, llm_client=llm_client)
    total_translated = 0
    total_skipped = 0
    batches_run = 0
    for _ in range(batches):
        result = service.translate_untranslated(
            workspace_id=workspace_id,
            source_id=source_id,
            limit=limit,
            raise_on_failure=raise_on_failure,
        )
        translated = int(result["translated"])
        skipped = int(result["skipped"])
        if translated == 0 and skipped == 0:
            break
        total_translated += translated
        total_skipped += skipped
        batches_run += 1
    return {
        "translated": total_translated,
        "skipped": total_skipped,
        "batches_run": batches_run,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-id", default="ws_default")
    parser.add_argument("--source-id")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--batches", type=int, default=1)
    parser.add_argument("--raise-on-failure", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as session:
        result = run_backfill(
            session,
            build_llm_client_from_settings(),
            workspace_id=args.workspace_id,
            source_id=args.source_id,
            limit=args.limit,
            batches=args.batches,
            raise_on_failure=args.raise_on_failure,
        )
    print(result)


if __name__ == "__main__":
    main()

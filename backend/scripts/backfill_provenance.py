#!/usr/bin/env python3
"""Run or preview the workspace-scoped provenance backfill."""

from __future__ import annotations

import argparse

from app.infrastructure.database import SessionLocal
from app.services.provenance.backfill import ProvenanceBackfillService


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as session:
        result = ProvenanceBackfillService(session).run(
            workspace_id=args.workspace_id,
            dry_run=args.dry_run,
        )
    print({"job_id": result.job_id, "dry_run": result.dry_run, "counts": result.counts})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

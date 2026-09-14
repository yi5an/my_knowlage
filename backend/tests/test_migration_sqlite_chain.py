"""SQLite migration-chain regression coverage."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _run_alembic(database_url: str, *arguments: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    return subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_sqlite_migration_chain_supports_upgrade_and_rollback(tmp_path: Path) -> None:
    backend_root = Path(__file__).parents[1]
    database_url = f"sqlite:///{tmp_path / 'migration.db'}"

    for arguments in (
        ("upgrade", "202609140002"),
        ("downgrade", "202609030002"),
        ("upgrade", "202609140002"),
    ):
        result = _run_alembic(database_url, *arguments, cwd=backend_root)
        assert result.returncode == 0, result.stderr

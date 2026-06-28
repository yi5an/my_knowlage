from collections.abc import Generator
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def create_database_engine(database_url: str | None = None) -> Engine:
    url = database_url or get_settings().database_url
    is_sqlite = url.startswith("sqlite")
    # SQLite concurrency: enable WAL (concurrent readers + serialized writer)
    # and busy_timeout so concurrent writes wait instead of raising
    # "database is locked" immediately. This matters because the research
    # workflow, the task worker, and request handlers all write to the same DB.
    connect_args: dict[str, Any] = (
        {
            "check_same_thread": False,
            "timeout": 10,
        }
        if is_sqlite
        else {}
    )
    engine = create_engine(url, connect_args=connect_args, future=True)
    if is_sqlite:
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_conn: Any, _conn_record: Any) -> None:
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=10000")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()
    return engine


engine = create_database_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db_session() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session

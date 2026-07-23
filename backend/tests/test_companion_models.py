"""Persistence contracts for the global AI companion."""

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.database import Base
from app.infrastructure.models import CompanionSession, Workspace


@pytest.fixture()
def session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db_session:
        db_session.add(Workspace(id="ws_default", name="default"))
        db_session.commit()
        yield db_session


def test_companion_session_is_unique_per_subject(session: Session) -> None:
    session.add(
        CompanionSession(
            id="cs_1",
            workspace_id="ws_default",
            subject_type="youtube_video",
            subject_id="video_1",
            title="Video",
        )
    )
    session.commit()
    session.add(
        CompanionSession(
            id="cs_2",
            workspace_id="ws_default",
            subject_type="youtube_video",
            subject_id="video_1",
            title="Video",
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()

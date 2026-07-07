"""Workspace-scoped application settings persisted in the database."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import Workspace, WorkspaceSetting
from app.schemas.youtube import (
    YouTubeAutoRetrySettings,
    YouTubeAutoRetrySettingsUpdate,
)

YOUTUBE_AUTO_RETRY_KEY = "youtube_auto_retry"


class WorkspaceSettingsService:
    """Read and update JSON settings rows for a workspace."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_youtube_auto_retry(
        self,
        workspace_id: str = "ws_default",
    ) -> YouTubeAutoRetrySettings:
        row = self._get_row(workspace_id, YOUTUBE_AUTO_RETRY_KEY)
        value = row.value if row is not None else {}
        return YouTubeAutoRetrySettings.model_validate(
            {"workspace_id": workspace_id, **value}
        )

    def update_youtube_auto_retry(
        self,
        workspace_id: str,
        payload: YouTubeAutoRetrySettingsUpdate,
    ) -> YouTubeAutoRetrySettings:
        self._ensure_workspace(workspace_id)
        settings = YouTubeAutoRetrySettings(
            workspace_id=workspace_id,
            **payload.model_dump(),
        )
        row = self._get_row(workspace_id, YOUTUBE_AUTO_RETRY_KEY)
        if row is None:
            row = WorkspaceSetting(
                id=f"setting_{uuid4().hex}",
                workspace_id=workspace_id,
                key=YOUTUBE_AUTO_RETRY_KEY,
                value=payload.model_dump(),
            )
            self.session.add(row)
        else:
            row.value = payload.model_dump()
        self.session.commit()
        return settings

    def list_enabled_youtube_auto_retry(self) -> list[YouTubeAutoRetrySettings]:
        rows = self.session.scalars(
            select(WorkspaceSetting).where(WorkspaceSetting.key == YOUTUBE_AUTO_RETRY_KEY)
        ).all()
        settings: list[YouTubeAutoRetrySettings] = []
        for row in rows:
            current = YouTubeAutoRetrySettings.model_validate(
                {"workspace_id": row.workspace_id, **(row.value or {})}
            )
            if current.enabled:
                settings.append(current)
        return settings

    def _get_row(self, workspace_id: str, key: str) -> WorkspaceSetting | None:
        return self.session.scalar(
            select(WorkspaceSetting).where(
                WorkspaceSetting.workspace_id == workspace_id,
                WorkspaceSetting.key == key,
            )
        )

    def _ensure_workspace(self, workspace_id: str) -> None:
        if self.session.get(Workspace, workspace_id) is None:
            self.session.add(Workspace(id=workspace_id, name=workspace_id))
            self.session.flush()

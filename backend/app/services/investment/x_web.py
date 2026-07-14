"""Collector-facing X Web ingestion service."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, cast

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.infrastructure.models import (
    InvestmentItem,
    InvestmentSource,
    TaskJob,
    XCollectorState,
)
from app.schemas.investment import (
    InvestmentFetchJobResponse,
    XCollectorCommandComplete,
    XCollectorCommandResponse,
    XCollectorHeartbeat,
    XCollectorStateResponse,
    XPostBatchImportRequest,
    XPostBatchImportResponse,
    XPostImportItem,
)
from app.services.investment.fetchers import InvestmentRawItem
from app.services.investment.normalizers import compute_dedupe_key
from app.services.investment.repositories import (
    InvestmentItemRepository,
    InvestmentSourceRepository,
)

UpsertResult = Literal["created", "updated"]
X_WEB_COLLECT_JOB_TYPE = "x_web_collect"


class XWebInvestmentService:
    """Validate and persist bounded batches produced by the Mac collector."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def import_posts(self, payload: XPostBatchImportRequest) -> XPostBatchImportResponse:
        source = self.session.get(InvestmentSource, payload.source_id)
        if source is None or source.source_type != "x_web":
            raise AppError("x_source_not_found", "X web source not found", 404)
        if source.workspace_id != payload.workspace_id:
            raise AppError("x_source_not_found", "X web source not found", 404)

        created = 0
        updated = 0
        skipped = 0
        errors: list[dict[str, object]] = []
        seen_ids: set[str] = set()

        try:
            for index, raw_item in enumerate(payload.items):
                try:
                    post = XPostImportItem.model_validate(raw_item)
                except ValidationError as exc:
                    skipped += 1
                    errors.append({"index": index, "message": _validation_message(exc)})
                    continue

                if post.tweet_id in seen_ids:
                    skipped += 1
                    continue
                seen_ids.add(post.tweet_id)

                result = self._upsert_post(
                    source=source,
                    workspace_id=payload.workspace_id,
                    post=post,
                )
                if result == "created":
                    created += 1
                else:
                    updated += 1
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        return XPostBatchImportResponse(
            items_seen=len(payload.items),
            items_created=created,
            items_updated=updated,
            items_skipped=skipped,
            errors=errors[:20],
        )

    def heartbeat(self, payload: XCollectorHeartbeat) -> XCollectorStateResponse:
        state = self.session.get(XCollectorState, payload.collector_id)
        if state is None:
            state = XCollectorState(
                collector_id=payload.collector_id,
                version=payload.version,
                login_status=payload.login_status,
                queue_size=payload.queue_size,
                last_success_at=payload.last_success_at,
                last_error=payload.last_error,
                heartbeat_at=datetime.now(UTC),
            )
            self.session.add(state)
        else:
            state.version = payload.version
            state.login_status = payload.login_status
            state.queue_size = payload.queue_size
            state.last_success_at = payload.last_success_at
            state.last_error = payload.last_error
            state.heartbeat_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(state)
        return XCollectorStateResponse.model_validate(state)

    def get_state(self, collector_id: str) -> XCollectorStateResponse | None:
        state = self.session.get(XCollectorState, collector_id)
        if state is None:
            return None
        return XCollectorStateResponse.model_validate(state)

    def list_states(self) -> list[XCollectorStateResponse]:
        states = self.session.scalars(
            select(XCollectorState).order_by(XCollectorState.heartbeat_at.desc())
        )
        return [XCollectorStateResponse.model_validate(state) for state in states]

    def claim_commands(self, collector_id: str) -> list[XCollectorCommandResponse]:
        jobs = list(
            self.session.scalars(
                select(TaskJob)
                .where(
                    TaskJob.job_type == X_WEB_COLLECT_JOB_TYPE,
                    TaskJob.status == "pending",
                )
                .order_by(TaskJob.created_at.asc())
                .limit(20)
            )
        )
        commands: list[XCollectorCommandResponse] = []
        now = datetime.now(UTC)
        for job in jobs:
            source = self.session.get(InvestmentSource, job.target_id)
            if source is None or source.source_type != "x_web":
                job.status = "failed"
                job.error_message = "X web source not found"
                job.finished_at = now
                continue
            job.status = "running"
            job.started_at = now
            job.input = {**(job.input or {}), "collector_id": collector_id}
            commands.append(
                XCollectorCommandResponse(
                    job_id=job.id,
                    source_id=source.id,
                    workspace_id=source.workspace_id,
                    name=source.name,
                    mode=cast(Literal["account", "keyword"], source.config["mode"]),
                    config=dict(source.config),
                    poll_interval_seconds=source.poll_interval_seconds,
                )
            )
        self.session.commit()
        return commands

    def complete_command(
        self,
        job_id: str,
        payload: XCollectorCommandComplete,
    ) -> InvestmentFetchJobResponse:
        job = self.session.get(TaskJob, job_id)
        if job is None or job.job_type != X_WEB_COLLECT_JOB_TYPE:
            raise AppError("x_command_not_found", "X collector command not found", 404)
        source = self.session.get(InvestmentSource, job.target_id)
        if source is None or source.source_type != "x_web":
            raise AppError("x_source_not_found", "X web source not found", 404)

        job.status = payload.status
        job.output = {
            "items_seen": payload.items_seen,
            "items_created": payload.items_created,
            "items_updated": payload.items_updated,
            "items_skipped": payload.items_skipped,
        }
        job.error_message = payload.error if payload.status == "failed" else None
        job.progress = 100
        job.finished_at = datetime.now(UTC)
        InvestmentSourceRepository(self.session).mark_polled(
            source,
            success=payload.status == "succeeded",
            error=payload.error,
        )
        self.session.commit()
        return _job_response(job)

    def _upsert_post(
        self,
        *,
        source: InvestmentSource,
        workspace_id: str,
        post: XPostImportItem,
    ) -> UpsertResult:
        canonical_url = f"https://x.com/{post.author_username}/status/{post.tweet_id}"
        dedupe_key = compute_dedupe_key("x_web", post.tweet_id, canonical_url)
        existing = self.session.scalar(
            select(InvestmentItem).where(
                InvestmentItem.workspace_id == workspace_id,
                InvestmentItem.dedupe_key == dedupe_key,
            )
        )
        raw = InvestmentRawItem(
            external_id=post.tweet_id,
            title=_post_title(post),
            url=canonical_url,
            source_name=f"@{post.author_username}",
            published_at=post.published_at,
            summary=post.text or None,
            raw_payload={
                "tweet_id": post.tweet_id,
                "author_id": post.author_id,
                "author_username": post.author_username,
                "author_name": post.author_name,
                "conversation_id": post.conversation_id,
                "lang": post.lang,
                "media": post.media,
                "quoted_tweet": post.quoted_tweet,
                "reposted_tweet": post.reposted_tweet,
                "reply_to_tweet_id": post.reply_to_tweet_id,
                "metrics": post.metrics,
                **post.raw_payload,
            },
        )
        InvestmentItemRepository(self.session).upsert_from_raw(
            raw,
            workspace_id=workspace_id,
            source=source,
        )
        return "updated" if existing is not None else "created"


def _post_title(post: XPostImportItem) -> str:
    first_line = next((line.strip() for line in post.text.splitlines() if line.strip()), "")
    excerpt = first_line[:160] if first_line else "Media post"
    return f"@{post.author_username}: {excerpt}"


def _validation_message(exc: ValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "Invalid X post"
    return str(errors[0].get("msg") or "Invalid X post")[:500]


def _job_response(job: TaskJob) -> InvestmentFetchJobResponse:
    output = job.output or {}
    return InvestmentFetchJobResponse(
        id=job.id,
        source_id=(job.input or {}).get("source_id"),
        workspace_id=job.workspace_id,
        status=job.status,
        started_at=job.started_at,
        finished_at=job.finished_at,
        items_seen=int(output.get("items_seen", 0)),
        items_created=int(output.get("items_created", 0)),
        items_skipped=int(output.get("items_skipped", 0)),
        last_error=job.error_message,
    )

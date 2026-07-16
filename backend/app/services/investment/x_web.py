"""Collector-facing X Web ingestion service."""

from __future__ import annotations

import logging
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

import requests
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
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
from app.services.investment.post_processing import enqueue_investment_post_processing
from app.services.investment.repositories import (
    InvestmentItemRepository,
    InvestmentSourceRepository,
)
from app.services.youtube.visual_analysis import OcrClient, structured_notes_from_ocr

UpsertResult = Literal["created", "updated"]
X_WEB_COLLECT_JOB_TYPE = "x_web_collect"
URL_RE = re.compile(r"https?://\S+")
MAX_MEDIA_OCR_PER_IMPORT = 10
logger = logging.getLogger(__name__)


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
        ocr_budget = MAX_MEDIA_OCR_PER_IMPORT

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
                    ocr_budget=ocr_budget,
                )
                if result.ocr_attempted:
                    ocr_budget -= 1
                if result == "created":
                    created += 1
                else:
                    updated += 1
            if created > 0 or updated > 0:
                enqueue_investment_post_processing(
                    self.session,
                    workspace_id=source.workspace_id,
                    target_type="investment_source",
                    target_id=source.id,
                    source_id=source.id,
                    include_classification=True,
                )
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
        ocr_budget: int = 0,
    ) -> _PostUpsertResult:
        canonical_url = f"https://x.com/{post.author_username}/status/{post.tweet_id}"
        dedupe_key = compute_dedupe_key("x_web", post.tweet_id, canonical_url)
        existing = self.session.scalar(
            select(InvestmentItem).where(
                InvestmentItem.workspace_id == workspace_id,
                InvestmentItem.dedupe_key == dedupe_key,
            )
        )
        media_context = _build_media_context(post, allow_ocr=ocr_budget > 0)
        raw = InvestmentRawItem(
            external_id=post.tweet_id,
            title=_post_title(post, media_context=media_context),
            url=canonical_url,
            source_name=f"@{post.author_username}",
            published_at=post.published_at,
            summary=_post_summary(post, media_context=media_context),
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
                "attachments": media_context.attachments,
                **post.raw_payload,
            },
        )
        InvestmentItemRepository(self.session).upsert_from_raw(
            raw,
            workspace_id=workspace_id,
            source=source,
        )
        return _PostUpsertResult(
            status="updated" if existing is not None else "created",
            ocr_attempted=media_context.ocr_attempted,
        )


class _PostUpsertResult:
    def __init__(self, *, status: UpsertResult, ocr_attempted: bool) -> None:
        self.status = status
        self.ocr_attempted = ocr_attempted

    def __eq__(self, other: object) -> bool:
        return self.status == other


class _MediaContext:
    def __init__(
        self,
        *,
        attachments: list[dict[str, object]],
        media_text: str | None,
        ocr_attempted: bool,
    ) -> None:
        self.attachments = attachments
        self.media_text = media_text
        self.ocr_attempted = ocr_attempted


def _post_title(post: XPostImportItem, *, media_context: _MediaContext) -> str:
    visible_text = _meaningful_text(post.text)
    if visible_text:
        excerpt = next((line.strip() for line in visible_text.splitlines() if line.strip()), "")
    elif media_context.media_text:
        excerpt = next(
            (line.strip() for line in media_context.media_text.splitlines() if line.strip()),
            "",
        )
    elif post.media:
        excerpt = _media_fallback_title(post.media)
    else:
        excerpt = "X post"
    excerpt = excerpt[:160]
    return f"@{post.author_username}: {excerpt}"


def _post_summary(post: XPostImportItem, *, media_context: _MediaContext) -> str | None:
    visible_text = _meaningful_text(post.text)
    if visible_text and media_context.media_text:
        return f"{visible_text}\n\n图片文字：\n{media_context.media_text}"
    if visible_text:
        return visible_text
    if media_context.media_text:
        return f"图片文字：\n{media_context.media_text}"
    if post.media:
        return f"包含 {_media_count_label(post.media)}，需打开媒体查看。"
    return post.text or None


def _build_media_context(post: XPostImportItem, *, allow_ocr: bool) -> _MediaContext:
    attachments: list[dict[str, object]] = []
    media_texts: list[str] = []
    ocr_attempted = False
    for index, media in enumerate(post.media, start=1):
        media_type = str(media.get("type") or "")
        url = _media_url(media)
        if not url:
            continue
        text_excerpt = _media_text(media)
        if not text_excerpt and allow_ocr and media_type == "photo" and not ocr_attempted:
            ocr_attempted = True
            text_excerpt = _ocr_image_url(url)
        if text_excerpt:
            media_texts.append(text_excerpt)
        attachment: dict[str, object] = {
            "title": _attachment_title(media_type, index),
            "url": url,
            "content_type": _attachment_content_type(media_type),
        }
        if text_excerpt:
            attachment["text_excerpt"] = text_excerpt
        attachments.append(attachment)
    return _MediaContext(
        attachments=attachments,
        media_text="\n".join(media_texts) if media_texts else None,
        ocr_attempted=ocr_attempted,
    )


def _media_url(media: dict[str, object]) -> str | None:
    for key in ("url", "preview_url", "media_url_https"):
        value = media.get(key)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value
    return None


def _media_text(media: dict[str, object]) -> str | None:
    for key in ("text_excerpt", "ocr_text", "alt_text", "ext_alt_text", "description"):
        value = media.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:4000]
    return None


def _ocr_image_url(url: str) -> str | None:
    settings = get_settings()
    if not settings.ocr_base_url:
        return None
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as image_file:
            image_file.write(response.content)
            image_path = Path(image_file.name)
        try:
            blocks = OcrClient(
                settings.ocr_base_url,
                timeout_seconds=settings.ocr_timeout_seconds,
            ).analyze_image(image_path)
            text = str(structured_notes_from_ocr(blocks).get("text") or "").strip()
            return text[:4000] if text else None
        finally:
            image_path.unlink(missing_ok=True)
    except Exception as exc:  # noqa: BLE001 - media OCR must not block import
        logger.warning("x media OCR failed for %s: %s", url, exc)
        return None


def _meaningful_text(value: str) -> str | None:
    stripped = value.strip()
    if not stripped:
        return None
    without_urls = URL_RE.sub("", stripped).strip()
    if not without_urls:
        return None
    return stripped


def _media_fallback_title(media: list[dict[str, object]]) -> str:
    return f"{_media_kind_label(media)}贴文（{_media_count_label(media)}）"


def _media_count_label(media: list[dict[str, object]]) -> str:
    photos = sum(1 for item in media if item.get("type") == "photo")
    videos = sum(1 for item in media if item.get("type") in {"video", "animated_gif"})
    parts: list[str] = []
    if photos:
        parts.append(f"{photos} 张图片")
    if videos:
        parts.append(f"{videos} 个视频")
    return "、".join(parts) if parts else f"{len(media)} 个媒体"


def _media_kind_label(media: list[dict[str, object]]) -> str:
    if any(item.get("type") in {"video", "animated_gif"} for item in media):
        return "视频"
    if any(item.get("type") == "photo" for item in media):
        return "图片"
    return "媒体"


def _attachment_title(media_type: str, index: int) -> str:
    if media_type == "photo":
        return f"X 图片 {index}"
    if media_type == "video":
        return f"X 视频 {index}"
    if media_type == "animated_gif":
        return f"X GIF {index}"
    return f"X 媒体 {index}"


def _attachment_content_type(media_type: str) -> str:
    if media_type == "photo":
        return "image"
    if media_type == "video":
        return "video"
    if media_type == "animated_gif":
        return "gif"
    return "media"


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

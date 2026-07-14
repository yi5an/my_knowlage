"""Collector-facing X Web ingestion service."""

from __future__ import annotations

from typing import Literal

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.infrastructure.models import InvestmentItem, InvestmentSource
from app.schemas.investment import (
    XPostBatchImportRequest,
    XPostBatchImportResponse,
    XPostImportItem,
)
from app.services.investment.fetchers import InvestmentRawItem
from app.services.investment.normalizers import compute_dedupe_key
from app.services.investment.repositories import InvestmentItemRepository

UpsertResult = Literal["created", "updated"]


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

from __future__ import annotations

import json
from hashlib import sha256
from http import HTTPStatus
from typing import NoReturn

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.infrastructure.models import (
    Document,
    DocumentChunk,
    DocumentVersion,
    EvidenceAnchor,
    InvestmentItem,
)
from app.schemas.provenance import (
    EvidenceAnchorCreate,
    EvidenceLocator,
    ImageRegionLocator,
    MediaSegmentLocator,
    PdfRegionLocator,
    TextSpanLocator,
    WebFragmentLocator,
)


class EvidenceAnchorService:
    """Validate and persist immutable, deterministic evidence anchors."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        workspace_id: str,
        request: EvidenceAnchorCreate,
        supersedes_anchor_id: str | None = None,
    ) -> EvidenceAnchor:
        document, version, chunk, source_item = self._resolve_source(workspace_id, request)
        self._validate_locator(request.locator, request.quote, chunk, source_item)
        anchor_id = _anchor_id(
            workspace_id,
            request.version_id or request.source_item_id or "",
            request.locator,
            request.quote,
        )
        existing = self.session.get(EvidenceAnchor, anchor_id)
        if existing is not None:
            return existing
        anchor = EvidenceAnchor(
            id=anchor_id,
            workspace_id=workspace_id,
            document_id=document.id if document else request.document_id,
            version_id=version.id if version else None,
            chunk_id=chunk.id if chunk else None,
            source_item_id=source_item.id if source_item else request.source_item_id,
            anchor_type=request.anchor_type.value,
            locator=request.locator.model_dump(mode="json"),
            quote=request.quote,
            content_hash=sha256(request.quote.encode()).hexdigest(),
            source_uri_snapshot=request.source_uri_snapshot
            or (document.source_uri if document else None)
            or (source_item.source_url if source_item else None),
            source_quality=request.source_quality,
            validation_state="valid",
            created_by_type=request.created_by_type.value,
            created_by_id=request.created_by_id,
            supersedes_anchor_id=supersedes_anchor_id,
        )
        self.session.add(anchor)
        self.session.flush()
        return anchor

    def reanchor(
        self,
        *,
        workspace_id: str,
        anchor_id: str,
        request: EvidenceAnchorCreate,
    ) -> EvidenceAnchor:
        original = self._owned_anchor(workspace_id, anchor_id)
        replacement = self.create(
            workspace_id=workspace_id,
            request=request,
            supersedes_anchor_id=original.id,
        )
        if replacement.id == original.id:
            raise AppError(
                "evidence_anchor_unchanged",
                "The replacement anchor is identical to the original anchor.",
            )
        return replacement

    def mark_stale_for_version(self, *, workspace_id: str, version_id: str) -> int:
        anchors = list(
            self.session.scalars(
                select(EvidenceAnchor).where(
                    EvidenceAnchor.workspace_id == workspace_id,
                    EvidenceAnchor.version_id == version_id,
                    EvidenceAnchor.validation_state == "valid",
                )
            )
        )
        changed = 0
        for anchor in anchors:
            if not self._anchor_still_matches(anchor):
                anchor.validation_state = "stale"
                changed += 1
        self.session.flush()
        return changed

    def _owned_anchor(self, workspace_id: str, anchor_id: str) -> EvidenceAnchor:
        anchor = self.session.get(EvidenceAnchor, anchor_id)
        if anchor is None or anchor.workspace_id != workspace_id:
            raise AppError(
                "provenance_object_not_found",
                "Evidence anchor was not found in this workspace.",
                HTTPStatus.NOT_FOUND,
            )
        return anchor

    def _resolve_source(
        self, workspace_id: str, request: EvidenceAnchorCreate
    ) -> tuple[
        Document | None,
        DocumentVersion | None,
        DocumentChunk | None,
        InvestmentItem | None,
    ]:
        document: Document | None = None
        version: DocumentVersion | None = None
        chunk: DocumentChunk | None = None
        source_item: InvestmentItem | None = None
        if request.version_id:
            version = self.session.get(DocumentVersion, request.version_id)
            document = self.session.get(Document, version.doc_id) if version else None
            if (
                document is None
                or document.workspace_id != workspace_id
                or (request.document_id is not None and request.document_id != document.id)
            ):
                self._raise_source_not_found()
        if request.source_item_id:
            source_item = self.session.get(InvestmentItem, request.source_item_id)
            if source_item is None or source_item.workspace_id != workspace_id:
                self._raise_source_not_found()
        chunk_id = getattr(request.locator, "chunk_id", None)
        if chunk_id:
            chunk = self.session.get(DocumentChunk, chunk_id)
            if (
                chunk is None
                or version is None
                or document is None
                or chunk.version_id != version.id
                or chunk.doc_id != document.id
            ):
                self._raise_source_not_found()
        return document, version, chunk, source_item

    def _validate_locator(
        self,
        locator: EvidenceLocator,
        quote: str,
        chunk: DocumentChunk | None,
        source_item: InvestmentItem | None,
    ) -> None:
        if isinstance(locator, TextSpanLocator):
            if chunk is None or chunk.content[locator.start_offset : locator.end_offset] != quote:
                self._raise_mismatch()
            return
        if isinstance(locator, PdfRegionLocator):
            if chunk is not None and (
                chunk.page_no != locator.page_no or quote not in chunk.content
            ):
                self._raise_mismatch()
            return
        if isinstance(locator, MediaSegmentLocator):
            if chunk is not None and quote not in chunk.content:
                self._raise_mismatch()
            return
        if isinstance(locator, ImageRegionLocator):
            return
        if isinstance(locator, WebFragmentLocator):
            if source_item is None or quote not in _investment_item_text(source_item):
                self._raise_mismatch()

    def _anchor_still_matches(self, anchor: EvidenceAnchor) -> bool:
        locator_type = anchor.locator.get("type")
        if locator_type == "text_span" and anchor.chunk_id:
            chunk = self.session.get(DocumentChunk, anchor.chunk_id)
            if chunk is None:
                return False
            start = int(anchor.locator["start_offset"])
            end = int(anchor.locator["end_offset"])
            return chunk.content[start:end] == anchor.quote
        if anchor.chunk_id:
            chunk = self.session.get(DocumentChunk, anchor.chunk_id)
            return chunk is not None and anchor.quote in chunk.content
        if anchor.source_item_id:
            item = self.session.get(InvestmentItem, anchor.source_item_id)
            return item is not None and anchor.quote in _investment_item_text(item)
        return True

    @staticmethod
    def _raise_source_not_found() -> NoReturn:
        raise AppError(
            "provenance_object_not_found",
            "Evidence source was not found in this workspace.",
            HTTPStatus.NOT_FOUND,
        )

    @staticmethod
    def _raise_mismatch() -> NoReturn:
        raise AppError(
            "evidence_anchor_mismatch",
            "The evidence quote does not match the persisted source locator.",
        )


def _anchor_id(
    workspace_id: str,
    source_version_id: str,
    locator: EvidenceLocator,
    quote: str,
) -> str:
    payload = json.dumps(
        locator.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    quote_hash = sha256(quote.encode()).hexdigest()
    digest = sha256(
        f"{workspace_id}|{source_version_id}|{payload}|{quote_hash}".encode()
    ).hexdigest()
    return f"evidence_{digest[:32]}"


def _investment_item_text(item: InvestmentItem) -> str:
    values = [item.title, item.summary, item.title_zh, item.summary_zh]
    return "\n".join(value for value in values if value)

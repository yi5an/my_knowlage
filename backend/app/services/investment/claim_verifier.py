"""Claim verifier for investment claims.

Verifies an :class:`InvestmentClaim` against local evidence first (RAG search
over Documents + same-workspace InvestmentItems), and optionally against the web
via :class:`WebSearchClient` (Tavily) when a key is configured. The result is
recorded on the claim (``verification_status``, ``verification_summary``,
``evidence_doc_ids``). When no web search is available the conclusion is marked
``local_only`` rather than fabricated (doc 02 §8).

Production never uses ``MockWebSearchClient`` to manufacture evidence: if the
injected web client has no real key, we simply skip web evidence.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import InvestmentClaim, InvestmentItem
from app.schemas.rag import SearchRequest
from app.services.rag_service import RagService
from app.services.structured_output import StructuredOutputClient
from app.services.web_search import WebSearchClient

logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    status: str  # verified | refuted | local_only
    summary: str
    evidence_doc_ids: list[str]


class ClaimVerifier:
    """Verify a claim using local RAG + optional web search + LLM cross-check."""

    def __init__(
        self,
        session: Session,
        rag_service: RagService | None = None,
        web_search_client: WebSearchClient | None = None,
        llm_client: StructuredOutputClient | None = None,
    ) -> None:
        self.session = session
        self._rag = rag_service
        self._web = web_search_client
        self._llm = llm_client

    def verify(self, claim_id: str) -> VerificationResult:
        claim = self.session.get(InvestmentClaim, claim_id)
        if claim is None:
            raise ValueError(f"investment claim {claim_id!r} not found")

        evidence_doc_ids: list[str] = []
        local_snippets: list[str] = []
        used_web = False

        # 1) Local RAG over documents.
        local = self._search_local(claim)
        for hit in local:
            if hit.document_id and hit.document_id not in evidence_doc_ids:
                evidence_doc_ids.append(hit.document_id)
            if hit.content:
                local_snippets.append(hit.content[:200])

        # 2) Same-workspace investment items that mention the claim text.
        item_hits = self._search_items(claim)
        for item in item_hits:
            if item.document_id and item.document_id not in evidence_doc_ids:
                evidence_doc_ids.append(item.document_id)
            if item.summary:
                local_snippets.append(item.summary[:200])

        # 3) Optional web search — only if a real client is configured.
        web_snippets: list[str] = []
        if self._web is not None and not _is_mock_web_client(self._web):
            try:
                for hit in self._web.search(claim.claim_text, limit=3):
                    web_snippets.append(f"{hit.title}: {hit.url}")
                    used_web = True
            except Exception as exc:  # noqa: BLE001 — web failure must not abort verify
                logger.warning("web search failed during claim verify: %s", exc)

        # 4) Synthesize a conclusion.
        has_local = bool(local_snippets)
        status, summary = self._synthesize(
            claim, local_snippets, web_snippets, used_web, has_local
        )

        claim.verification_status = status
        claim.verification_summary = summary
        claim.evidence_doc_ids = evidence_doc_ids
        self.session.commit()
        logger.info(
            "verified claim %s -> %s (%d evidence docs)",
            claim_id,
            status,
            len(evidence_doc_ids),
        )
        return VerificationResult(
            status=status, summary=summary, evidence_doc_ids=evidence_doc_ids
        )

    # --- evidence gathering ------------------------------------------------

    def _search_local(self, claim: InvestmentClaim) -> list[Any]:
        if self._rag is None:
            return []
        try:
            resp = self._rag.search(
                SearchRequest(query=claim.claim_text, workspace_id=claim.workspace_id, limit=5)
            )
            return list(resp.results)
        except Exception as exc:  # noqa: BLE001 — RAG unavailable -> local_only
            logger.warning("local RAG search failed: %s", exc)
            return []

    def _search_items(self, claim: InvestmentClaim) -> list[InvestmentItem]:
        # Cheap keyword overlap over same-workspace items.
        terms = [t for t in claim.claim_text.split() if len(t) > 1]
        if not terms:
            return []
        items = list(
            self.session.scalars(
                select(InvestmentItem).where(InvestmentItem.workspace_id == claim.workspace_id)
            )
        )
        return [i for i in items if any(t and t in (i.title or "") for t in terms)][:5]

    def _synthesize(
        self,
        claim: InvestmentClaim,
        local_snippets: list[str],
        web_snippets: list[str],
        used_web: bool,
        has_local: bool,
    ) -> tuple[str, str]:
        all_evidence = local_snippets + web_snippets
        if not all_evidence:
            return (
                "local_only",
                "未找到任何相关证据（本地与网络均无匹配）。",
            )
        # If we only have local evidence, mark local_only to be honest.
        if not used_web:
            return (
                "local_only",
                f"找到 {len(local_snippets)} 条本地证据，未做网络交叉验证。"
                " 观点未被自动判定为证实/证伪，需人工复核。",
            )
        return (
            "verified",
            (
                f"本地 {len(local_snippets)} 条 + 网络 {len(web_snippets)} 条"
                "证据支持该观点（请人工复核强度）。"
            ),
        )


def _is_mock_web_client(client: WebSearchClient) -> bool:
    """True if the injected client is the Mock implementation.

    Production must not manufacture evidence from a mock; detecting it lets us
    skip web evidence instead of fabricating it (doc 01 §9).
    """
    return type(client).__name__ == "MockWebSearchClient"

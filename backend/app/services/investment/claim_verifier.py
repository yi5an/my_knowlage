"""Evidence-bound verification for investment claims.

The legacy claim fields are still updated for the current investment UI, but
every persisted verdict is now backed by exact candidates from the local
knowledge base. A URL/title returned by web search is retained only as a
verification hint; it is never promoted to supporting evidence without a
captured, persisted fragment.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import InvestmentClaim, InvestmentItem, TraceNode
from app.schemas.provenance import (
    ClaimVerificationJudgment,
    ClaimVerificationOutput,
    OriginType,
    TraceRelationType,
)
from app.schemas.rag import SearchRequest
from app.services.provenance.adapters import ProvenanceAdapter
from app.services.provenance.conclusions import ConclusionService
from app.services.provenance.links import TraceLinkService
from app.services.provenance.registry import TraceRegistrationService
from app.services.rag_service import RagService
from app.services.reading_evidence import ReadingEvidenceAdapter, ReadingEvidenceCandidate
from app.services.structured_output import StructuredOutputClient
from app.services.web_search import WebSearchClient

logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    status: str  # verified | refuted | local_only
    summary: str
    evidence_doc_ids: list[str]
    edge_ids: list[str] = field(default_factory=list)
    unanchored_candidates: int = 0


class ClaimVerifier:
    """Verify a claim using local evidence plus optional web cross-checks."""

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

        raw_local = self._search_local(claim)
        raw_items = self._search_items(claim)
        evidence_doc_ids = _document_ids([*raw_local, *raw_items])
        candidates = self._persisted_candidates(claim)

        web_snippets: list[str] = []
        used_web = False
        if self._web is not None and not _is_mock_web_client(self._web):
            try:
                for hit in self._web.search(claim.claim_text, limit=3):
                    title = getattr(hit, "title", "")
                    url = getattr(hit, "url", None)
                    snippet = getattr(hit, "snippet", "")
                    web_snippets.append(f"{title}: {snippet or url or ''}")
                    used_web = True
            except Exception as exc:  # noqa: BLE001 — web failure must not abort verify
                logger.warning("web search failed during claim verify: %s", exc)

        judgments = self._judgments(claim, candidates)
        status, summary = self._status_summary(
            candidates=candidates,
            judgments=judgments,
            web_snippets=web_snippets,
            used_web=used_web,
        )
        claim.verification_status = status
        claim.verification_summary = summary
        claim.evidence_doc_ids = evidence_doc_ids
        self.session.flush()

        edge_ids, unanchored = self._persist_provenance(
            claim=claim,
            candidates=candidates,
            judgments=judgments,
        )
        self.session.commit()
        logger.info(
            "verified claim %s -> %s (%d evidence docs, %d edges)",
            claim_id,
            status,
            len(evidence_doc_ids),
            len(edge_ids),
        )
        return VerificationResult(
            status=status,
            summary=summary,
            evidence_doc_ids=evidence_doc_ids,
            edge_ids=edge_ids,
            unanchored_candidates=unanchored,
        )

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
        terms = [term for term in claim.claim_text.split() if len(term) > 1]
        if not terms:
            return []
        items = list(
            self.session.scalars(
                select(InvestmentItem).where(InvestmentItem.workspace_id == claim.workspace_id)
            )
        )
        return [item for item in items if any(term in (item.title or "") for term in terms)][:5]

    def _persisted_candidates(self, claim: InvestmentClaim) -> list[ReadingEvidenceCandidate]:
        if self._rag is None:
            return []
        return ReadingEvidenceAdapter(self.session, self._rag).search(
            workspace_id=claim.workspace_id,
            query=claim.claim_text,
            excluded_chunk_ids=set(),
            limit=8,
        )

    def _judgments(
        self,
        claim: InvestmentClaim,
        candidates: list[ReadingEvidenceCandidate],
    ) -> list[ClaimVerificationJudgment]:
        if not candidates:
            return []
        if self._llm is None:
            return [
                ClaimVerificationJudgment(
                    candidate_id=_candidate_id(candidate),
                    stance="supports",
                    rationale="Exact persisted source candidate retrieved for the claim.",
                    confidence=max(0.0, min(1.0, candidate.retrieval_score)),
                )
                for candidate in candidates
            ]
        prompt = _verification_prompt(claim.claim_text, candidates)
        try:
            output = self._llm.generate(prompt, ClaimVerificationOutput)
            return list(output.judgments)
        except Exception as exc:  # noqa: BLE001 — safe fallback stays reviewable
            logger.warning("claim verification LLM failed, using local support fallback: %s", exc)
            return [
                ClaimVerificationJudgment(
                    candidate_id=_candidate_id(candidate),
                    stance="supports",
                    rationale=(
                        "Structured verdict unavailable; exact local candidate retained "
                        "for review."
                    ),
                    confidence=max(0.0, min(1.0, candidate.retrieval_score)),
                )
                for candidate in candidates
            ]

    def _status_summary(
        self,
        *,
        candidates: list[ReadingEvidenceCandidate],
        judgments: list[ClaimVerificationJudgment],
        web_snippets: list[str],
        used_web: bool,
    ) -> tuple[str, str]:
        candidate_ids = {_candidate_id(candidate) for candidate in candidates}
        valid = [judgment for judgment in judgments if _judgment_matches(judgment, candidate_ids)]
        stances = {judgment.stance for judgment in valid}
        if "supports" in stances and "refutes" in stances:
            status = "local_only"
            summary = "本地证据同时包含支持与反驳，已标记为冲突，需人工复核。"
        elif "refutes" in stances:
            status = "refuted"
            summary = f"找到 {len(valid)} 条本地证据反驳该观点。"
        elif "supports" in stances:
            status = "verified" if used_web else "local_only"
            summary = (
                f"找到 {len(valid)} 条本地证据支持该观点。"
                + (
                    f" 网络补充 {len(web_snippets)} 条，仍需人工复核。"
                    if used_web
                    else " 未做网络交叉验证。"
                )
            )
        elif used_web:
            status = "verified"
            summary = f"网络检索得到 {len(web_snippets)} 条结果，但没有可回放的本地锚点。"
        elif candidates:
            status = "local_only"
            summary = "检索到来源，但模型未返回有效的证据引用，未建立支持边。"
        else:
            status = "local_only"
            summary = "未找到任何可验证证据（本地与网络均无可回放匹配）。"
        return status, summary

    def _persist_provenance(
        self,
        *,
        claim: InvestmentClaim,
        candidates: list[ReadingEvidenceCandidate],
        judgments: list[ClaimVerificationJudgment],
    ) -> tuple[list[str], int]:
        adapter = ProvenanceAdapter(self.session)
        adapted: dict[str, Any] = {}
        unanchored = 0
        referenced_candidates = {
            _candidate_id(candidate)
            for judgment in judgments
            if (candidate := _find_candidate(judgment.candidate_id, candidates)) is not None
        }
        for candidate in candidates:
            if _candidate_id(candidate) not in referenced_candidates:
                continue
            adaptation = adapter.from_candidate(
                workspace_id=claim.workspace_id,
                candidate=candidate,
            )
            adapted[_candidate_id(candidate)] = adaptation
            if adaptation.anchor is None:
                unanchored += 1

        claim_node = TraceRegistrationService(self.session).register(
            workspace_id=claim.workspace_id,
            backing_type="investment_claim",
            backing_id=claim.id,
            layer="event",
            node_type="claim",
            label=claim.claim_text[:240],
            display_status=claim.verification_status,
            confidence=0.75 if claim.verification_status in {"verified", "refuted"} else 0.5,
            properties={"verification_status": claim.verification_status},
        )
        conclusion = ConclusionService(self.session).from_investment_claim(
            workspace_id=claim.workspace_id,
            claim_id=claim.id,
        )
        conclusion_node = self.session.scalar(
            select(TraceNode).where(
                TraceNode.workspace_id == claim.workspace_id,
                TraceNode.backing_type == "conclusion",
                TraceNode.backing_id == conclusion.id,
            )
        )
        if conclusion_node is None:
            raise RuntimeError("investment claim conclusion node registration failed")

        links = TraceLinkService(self.session)
        edge_ids: list[str] = []
        by_stance: dict[
            str,
            list[tuple[ReadingEvidenceCandidate, Any, ClaimVerificationJudgment]],
        ] = {}
        for judgment in judgments:
            matched_candidate = _find_candidate(judgment.candidate_id, candidates)
            if matched_candidate is None:
                continue
            adaptation_value = adapted.get(_candidate_id(matched_candidate))
            if adaptation_value is None:
                continue
            adaptation = adaptation_value
            if adaptation.anchor is None or adaptation.middle_node is None:
                continue
            derived = links.create(
                workspace_id=claim.workspace_id,
                source_node_id=adaptation.middle_node.id,
                target_node_id=claim_node.id,
                relation_type=TraceRelationType.derived_from,
                origin_type=OriginType.imported,
                confidence=judgment.confidence,
                rationale="Exact persisted candidate used during claim verification.",
                evidence_anchor_ids=[adaptation.anchor.id],
                model_metadata={"workflow": "investment_claim_verification"},
                review_status="confirmed",
                validation_status="supported",
            )
            edge_ids.append(derived.id)
            by_stance.setdefault(judgment.stance, []).append(
                (matched_candidate, adaptation, judgment)
            )

        for stance, values in by_stance.items():
            relation = TraceRelationType(stance)
            anchor_ids = [value[1].anchor.id for value in values if value[1].anchor is not None]
            confidence = sum(value[2].confidence for value in values) / len(values)
            edge = links.create(
                workspace_id=claim.workspace_id,
                source_node_id=claim_node.id,
                target_node_id=conclusion_node.id,
                relation_type=relation,
                origin_type=OriginType.ai,
                confidence=confidence,
                rationale="; ".join(value[2].rationale for value in values),
                evidence_anchor_ids=anchor_ids,
                model_metadata={"workflow": "investment_claim_verification"},
                review_status="pending_review",
                validation_status="conflicted"
                if len(by_stance) > 1
                else "unverified",
            )
            edge_ids.append(edge.id)
        if by_stance:
            if "supports" in by_stance and "refutes" in by_stance:
                conclusion.validation_status = "conflicted"
            elif "refutes" in by_stance:
                conclusion.validation_status = "refuted"
            elif "supports" in by_stance:
                conclusion.validation_status = "supported"
            else:
                conclusion.validation_status = "insufficient_evidence"
            conclusion_node.properties = {
                **dict(conclusion_node.properties or {}),
                "validation_status": conclusion.validation_status,
            }
        return edge_ids, unanchored


def _candidate_id(candidate: ReadingEvidenceCandidate) -> str:
    return f"{candidate.source_kind}:{candidate.source_id}"


def _find_candidate(
    candidate_id: str,
    candidates: list[ReadingEvidenceCandidate],
) -> ReadingEvidenceCandidate | None:
    for candidate in candidates:
        if candidate_id in {
            _candidate_id(candidate),
            candidate.source_id,
            f"document_chunk:{candidate.source_id}",
        }:
            return candidate
    return None


def _judgment_matches(
    judgment: ClaimVerificationJudgment,
    candidate_ids: set[str],
) -> bool:
    return judgment.candidate_id in candidate_ids or any(
        judgment.candidate_id == candidate_id.split(":", 1)[-1]
        for candidate_id in candidate_ids
    )


def _document_ids(hits: list[Any]) -> list[str]:
    result: list[str] = []
    for hit in hits:
        document_id = getattr(hit, "document_id", None)
        if isinstance(document_id, str) and document_id not in result:
            result.append(document_id)
    return result


def _verification_prompt(
    claim_text: str,
    candidates: list[ReadingEvidenceCandidate],
) -> str:
    lines = [
        "你是投资观点核验助手。只能使用下方持久化来源片段，不得补充外部知识。",
        f"待核验观点: {claim_text}",
        "对每个 candidate_id 返回 supports/refutes/qualifies 之一，并给出理由和置信度。",
        "candidate_id 必须逐字使用下方 ID。",
    ]
    for candidate in candidates:
        lines.append(
            f"[{_candidate_id(candidate)}] {candidate.title}\n{candidate.excerpt}"
        )
    return "\n\n".join(lines)


def _is_mock_web_client(client: WebSearchClient) -> bool:
    """True if the injected client is the Mock implementation."""
    return type(client).__name__ == "MockWebSearchClient"

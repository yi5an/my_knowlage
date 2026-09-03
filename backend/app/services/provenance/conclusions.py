from __future__ import annotations

from http import HTTPStatus
from typing import NoReturn
from uuid import UUID, uuid4, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.infrastructure.models import (
    Conclusion,
    InvestmentClaim,
    InvestmentThesis,
    ReadingAnalysis,
    ReadingInsight,
)
from app.schemas.provenance import (
    ConclusionCreate,
    OriginType,
    ReviewStatus,
    ValidationStatus,
)
from app.services.provenance.registry import TraceRegistrationService

_CONCLUSION_NAMESPACE = UUID("3fc8b648-08c2-463a-a70a-a46d781c994a")

_CLAIM_STATUS: dict[str, tuple[ReviewStatus, ValidationStatus]] = {
    "pending": (ReviewStatus.pending_review, ValidationStatus.unverified),
    "verified": (ReviewStatus.confirmed, ValidationStatus.supported),
    "refuted": (ReviewStatus.confirmed, ValidationStatus.refuted),
    "local_only": (ReviewStatus.pending_review, ValidationStatus.insufficient_evidence),
}
_INSIGHT_REVIEW = {
    "active": ReviewStatus.ai_generated,
    "confirmed": ReviewStatus.confirmed,
    "dismissed": ReviewStatus.rejected,
}
_INSIGHT_VALIDATION = {
    "corroborated": ValidationStatus.supported,
    "conflicted": ValidationStatus.conflicted,
    "insufficient": ValidationStatus.insufficient_evidence,
}
_THESIS_CONFIDENCE = {"low": 0.35, "medium": 0.65, "high": 0.9}


class ConclusionService:
    """Persist versioned conclusions and adapt existing domain conclusions."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, *, workspace_id: str, request: ConclusionCreate) -> Conclusion:
        stable_id = self._stable_source_id(workspace_id, request)
        if stable_id:
            existing = self.session.get(Conclusion, stable_id)
            if existing is not None:
                self._register(existing)
                return existing
        conclusion = self._from_request(
            conclusion_id=stable_id or f"conclusion_{uuid4().hex}",
            workspace_id=workspace_id,
            request=request,
            version_no=1,
            supersedes_id=None,
        )
        self.session.add(conclusion)
        self.session.flush()
        self._register(conclusion)
        return conclusion

    def revise(
        self,
        *,
        workspace_id: str,
        conclusion_id: str,
        request: ConclusionCreate,
    ) -> Conclusion:
        previous = self._owned(workspace_id, conclusion_id)
        revised = self._from_request(
            conclusion_id=f"conclusion_{uuid4().hex}",
            workspace_id=workspace_id,
            request=request,
            version_no=previous.version_no + 1,
            supersedes_id=previous.id,
        )
        self.session.add(revised)
        self.session.flush()
        self._register(revised)
        return revised

    def from_investment_claim(self, *, workspace_id: str, claim_id: str) -> Conclusion:
        claim = self.session.get(InvestmentClaim, claim_id)
        if claim is None or claim.workspace_id != workspace_id:
            self._raise_not_found("Investment claim")
        if claim.verification_status not in _CLAIM_STATUS:
            raise AppError(
                "provenance_status_unknown",
                f"Unknown investment claim status: {claim.verification_status}",
            )
        review, validation = _CLAIM_STATUS[claim.verification_status]
        return self.create(
            workspace_id=workspace_id,
            request=ConclusionCreate(
                conclusion_type="investment",
                conclusion_subtype="claim",
                title=claim.claim_text[:240],
                body=claim.verification_summary or claim.claim_text,
                confidence=0.75 if claim.verification_status == "verified" else 0.5,
                review_status=review,
                validation_status=validation,
                origin_type=OriginType.imported,
                source_object_type="investment_claim",
                source_object_id=claim.id,
            ),
        )

    def from_investment_thesis(self, *, workspace_id: str, thesis_id: str) -> Conclusion:
        thesis = self.session.get(InvestmentThesis, thesis_id)
        if thesis is None or thesis.workspace_id != workspace_id:
            self._raise_not_found("Investment thesis")
        confidence = _THESIS_CONFIDENCE.get(thesis.confidence)
        if confidence is None:
            raise AppError(
                "provenance_status_unknown",
                f"Unknown investment thesis confidence: {thesis.confidence}",
            )
        return self.create(
            workspace_id=workspace_id,
            request=ConclusionCreate(
                conclusion_type="investment",
                conclusion_subtype="thesis",
                title=thesis.title,
                body=thesis.body or thesis.title,
                confidence=confidence,
                review_status=ReviewStatus.confirmed
                if thesis.status == "validated"
                else ReviewStatus.pending_review,
                validation_status=ValidationStatus.supported
                if thesis.status == "validated"
                else ValidationStatus.unverified,
                origin_type=OriginType.imported,
                source_object_type="investment_thesis",
                source_object_id=thesis.id,
            ),
        )

    def from_reading_insight(self, *, workspace_id: str, insight_id: str) -> Conclusion:
        insight = self.session.scalar(
            select(ReadingInsight)
            .join(ReadingAnalysis, ReadingAnalysis.id == ReadingInsight.analysis_id)
            .where(
                ReadingInsight.id == insight_id,
                ReadingAnalysis.workspace_id == workspace_id,
            )
        )
        if insight is None:
            self._raise_not_found("Reading insight")
        if (
            insight.status not in _INSIGHT_REVIEW
            or insight.evidence_state not in _INSIGHT_VALIDATION
        ):
            raise AppError("provenance_status_unknown", "Unknown reading insight status.")
        return self.create(
            workspace_id=workspace_id,
            request=ConclusionCreate(
                conclusion_type="research",
                conclusion_subtype=insight.kind,
                title=insight.headline,
                body=f"{insight.explanation}\n\n{insight.why_it_matters}",
                confidence=insight.confidence,
                review_status=_INSIGHT_REVIEW[insight.status],
                validation_status=_INSIGHT_VALIDATION[insight.evidence_state],
                origin_type=OriginType.imported,
                source_object_type="reading_insight",
                source_object_id=insight.id,
                scope={"priority": insight.priority},
            ),
        )

    def _register(self, conclusion: Conclusion) -> None:
        TraceRegistrationService(self.session).register(
            workspace_id=conclusion.workspace_id,
            backing_type="conclusion",
            backing_id=conclusion.id,
            layer="conclusion",
            node_type=conclusion.conclusion_type,
            label=conclusion.title,
            display_status=conclusion.review_status,
            confidence=conclusion.confidence,
            properties={
                "validation_status": conclusion.validation_status,
                "subtype": conclusion.conclusion_subtype,
            },
        )

    def _owned(self, workspace_id: str, conclusion_id: str) -> Conclusion:
        conclusion = self.session.get(Conclusion, conclusion_id)
        if conclusion is None or conclusion.workspace_id != workspace_id:
            self._raise_not_found("Conclusion")
        return conclusion

    @staticmethod
    def _stable_source_id(workspace_id: str, request: ConclusionCreate) -> str | None:
        if request.source_object_type and request.source_object_id:
            identity = (
                f"{workspace_id}/{request.source_object_type}/{request.source_object_id}/"
                f"{request.conclusion_type}"
            )
            return f"conclusion_{uuid5(_CONCLUSION_NAMESPACE, identity).hex}"
        return None

    @staticmethod
    def _from_request(
        *,
        conclusion_id: str,
        workspace_id: str,
        request: ConclusionCreate,
        version_no: int,
        supersedes_id: str | None,
    ) -> Conclusion:
        return Conclusion(
            id=conclusion_id,
            workspace_id=workspace_id,
            conclusion_type=request.conclusion_type,
            conclusion_subtype=request.conclusion_subtype,
            title=request.title,
            body=request.body,
            stance=request.stance,
            scope=request.scope,
            valid_from=request.valid_from,
            valid_to=request.valid_to,
            as_of=request.as_of,
            confidence=request.confidence,
            review_status=request.review_status.value,
            validation_status=request.validation_status.value,
            origin_type=request.origin_type.value,
            model_metadata=request.model_metadata,
            source_object_type=request.source_object_type,
            source_object_id=request.source_object_id,
            version_no=version_no,
            supersedes_id=supersedes_id,
        )

    @staticmethod
    def _raise_not_found(kind: str) -> NoReturn:
        raise AppError(
            "provenance_object_not_found",
            f"{kind} was not found in this workspace.",
            HTTPStatus.NOT_FOUND,
        )

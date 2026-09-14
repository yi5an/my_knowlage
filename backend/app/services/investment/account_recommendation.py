from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.infrastructure.models import (
    InvestmentAccountRecommendation,
    InvestmentFact,
    InvestmentPersonImpactProfile,
    InvestmentPersonSource,
    InvestmentSource,
    TaskJob,
)
from app.schemas.investment import FollowRecommendationRequest
from app.services.investment.x_web import X_WEB_COLLECT_JOB_TYPE


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _handle(value: object) -> str:
    return str(value or "").strip().lstrip("@").casefold()


class AccountRecommendationService:
    """Workspace-scoped, evidence-first account recommendations."""

    def __init__(self, session: Session, web_search: Any | None = None) -> None:
        self.session = session
        self.web_search = web_search

    def refresh(
        self, workspace_id: str, theme_id: str | None = None
    ) -> list[InvestmentAccountRecommendation]:
        people = list(
            self.session.scalars(
                select(InvestmentPersonSource).where(
                    InvestmentPersonSource.workspace_id == workspace_id,
                    InvestmentPersonSource.enabled.is_(True),
                )
            )
        )
        if theme_id:
            people = [p for p in people if theme_id in [str(v) for v in (p.theme_ids or [])]]
        candidates: list[dict[str, Any]] = []
        for person_source in people:
            candidates.append(
                {
                    "platform": person_source.platform,
                    "handle": person_source.handle,
                    "display_name": person_source.display_name,
                    "role_type": person_source.role_type,
                    "theme_ids": list(person_source.theme_ids or []),
                    "person": person_source,
                }
            )
        if self.web_search is not None:
            query = f"investment research {theme_id or 'macro'} X YouTube institution"
            try:
                search_results = self.web_search.search(query) or []
            except Exception:  # noqa: BLE001 - optional enrichment
                search_results = []
            for item in search_results:
                if isinstance(item, dict) and item.get("platform") and item.get("handle"):
                    candidates.append(dict(item))
        out: list[InvestmentAccountRecommendation] = []
        for item in candidates:
            handle = str(item["handle"]).strip().lstrip("@")
            platform = str(item.get("platform", "x")).lower()
            existing = self.session.scalar(
                select(InvestmentAccountRecommendation).where(
                    InvestmentAccountRecommendation.workspace_id == workspace_id,
                    InvestmentAccountRecommendation.platform == platform,
                    InvestmentAccountRecommendation.handle == handle,
                )
            )
            person_candidate = item.get("person")
            source_person: InvestmentPersonSource | None = (
                person_candidate if isinstance(person_candidate, InvestmentPersonSource) else None
            )
            profile = None
            if source_person is not None:
                profile = self.session.scalar(
                    select(InvestmentPersonImpactProfile).where(
                        InvestmentPersonImpactProfile.workspace_id == workspace_id,
                        InvestmentPersonImpactProfile.person_source_id == source_person.id,
                    )
                )
            sample = int(profile.sample_count) if profile else 0
            evidence = len(
                list(
                    self.session.scalars(
                        select(InvestmentFact.id)
                        .where(InvestmentFact.workspace_id == workspace_id)
                        .limit(100)
                    )
                )
            )
            sufficient = sample >= 5
            label = (
                "高匹配"
                if sufficient and (profile and (profile.hit_rate or 0) >= 0.6)
                else ("样本不足" if not sufficient else "值得学习")
            )
            reason = f"主题相关账号；基于 {sample} 个事件样本和 {evidence} 条事实验证。"
            scores = {
                k: 0.0
                for k in (
                    "theme_relevance",
                    "source_quality",
                    "lead_time",
                    "validation_rate",
                    "independence",
                    "noise_penalty",
                    "blind_spot_coverage",
                    "sample_sufficiency",
                )
            }
            scores["sample_sufficiency"] = min(sample / 5, 1.0)
            if profile and profile.hit_rate is not None:
                scores["validation_rate"] = float(profile.hit_rate)
            if existing is None:
                existing = InvestmentAccountRecommendation(
                    id=_id("rec"),
                    workspace_id=workspace_id,
                    platform=platform,
                    handle=handle,
                    display_name=item.get("display_name"),
                    role_type=item.get("role_type", "other"),
                    theme_ids=list(item.get("theme_ids", [])),
                    recommendation_label=label,
                    reason=reason,
                    score_breakdown=scores,
                    sample_count=sample,
                    evidence_count=evidence,
                    status="new",
                )
                self.session.add(existing)
            else:
                existing.recommendation_label, existing.reason = label, reason
                existing.sample_count, existing.evidence_count, existing.score_breakdown = (
                    sample,
                    evidence,
                    scores,
                )
            out.append(existing)
        self.session.commit()
        return out

    def list(
        self, workspace_id: str, platform: str | None = None, theme_id: str | None = None
    ) -> list[InvestmentAccountRecommendation]:
        stmt = select(InvestmentAccountRecommendation).where(
            InvestmentAccountRecommendation.workspace_id == workspace_id
        )
        if platform:
            stmt = stmt.where(InvestmentAccountRecommendation.platform == platform)
        rows = list(
            self.session.scalars(stmt.order_by(InvestmentAccountRecommendation.updated_at.desc()))
        )
        if theme_id:
            rows = [r for r in rows if theme_id in [str(v) for v in (r.theme_ids or [])]]
        return rows

    def _get(self, rec_id: str, workspace_id: str) -> InvestmentAccountRecommendation:
        rec = self.session.scalar(
            select(InvestmentAccountRecommendation).where(
                InvestmentAccountRecommendation.id == rec_id,
                InvestmentAccountRecommendation.workspace_id == workspace_id,
            )
        )
        if rec is None:
            raise AppError("not_found", "recommendation not found", 404)
        return rec

    def dismiss(self, rec_id: str, workspace_id: str) -> InvestmentAccountRecommendation:
        rec = self._get(rec_id, workspace_id)
        rec.status = "dismissed"
        self.session.commit()
        return rec

    def follow(
        self, rec_id: str, workspace_id: str, payload: FollowRecommendationRequest
    ) -> InvestmentSource:
        rec = self._get(rec_id, workspace_id)
        sources = list(
            self.session.scalars(
                select(InvestmentSource).where(InvestmentSource.workspace_id == workspace_id)
            )
        )
        expected_type = {"x": "x_web", "youtube": "youtube", "institution": "manual"}.get(
            rec.platform, "manual"
        )
        src = next(
            (
                s
                for s in sources
                if s.source_type == expected_type
                and _handle((s.config or {}).get("username")) == _handle(rec.handle)
            ),
            None,
        )
        if src is None:
            source_type = expected_type
            src = InvestmentSource(
                id=_id("src"),
                workspace_id=workspace_id,
                source_type=source_type,
                name=rec.display_name or rec.handle,
                config={
                    "mode": "account",
                    "username": rec.handle,
                    "platform": rec.platform,
                    "max_items_per_poll": 50,
                },
                default_info_layer="human_source",
                default_watchlist_ids=list(payload.theme_ids or []),
                poll_interval_seconds=payload.poll_interval_seconds,
                enabled=True,
            )
            self.session.add(src)
            self.session.flush()
        job_type = X_WEB_COLLECT_JOB_TYPE if src.source_type == "x_web" else "investment_fetch"
        job = self.session.scalar(
            select(TaskJob).where(
                TaskJob.workspace_id == workspace_id,
                TaskJob.job_type == job_type,
                TaskJob.target_id == src.id,
                TaskJob.status.in_(("pending", "running")),
            )
        )
        if job is None:
            self.session.add(
                TaskJob(
                    id=_id("job"),
                    workspace_id=workspace_id,
                    job_type=job_type,
                    target_type="investment_source",
                    target_id=src.id,
                    status="pending",
                    input={"source_id": src.id},
                )
            )
        rec.source_id, rec.status = src.id, "followed"
        self.session.commit()
        return src

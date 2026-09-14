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
        for person in people:
            candidates.append(
                {
                    "platform": person.platform,
                    "handle": person.handle,
                    "display_name": person.display_name,
                    "role_type": person.role_type,
                    "theme_ids": list(person.theme_ids or []),
                    "person": person,
                }
            )
        if self.web_search is not None:
            query = f"investment research {theme_id or 'macro'} X YouTube institution"
            for item in self.web_search.search(query) or []:
                if isinstance(item, dict) and item.get("platform") and item.get("handle"):
                    candidates.append(dict(item))
        out: list[InvestmentAccountRecommendation] = []
        for item in candidates:
            handle = str(item["handle"])
            platform = str(item.get("platform", "x")).lower()
            existing = self.session.scalar(
                select(InvestmentAccountRecommendation).where(
                    InvestmentAccountRecommendation.workspace_id == workspace_id,
                    InvestmentAccountRecommendation.platform == platform,
                    InvestmentAccountRecommendation.handle == handle,
                )
            )
            person = item.get("person")
            profile = None
            if person is not None:
                profile = self.session.scalar(
                    select(InvestmentPersonImpactProfile).where(
                        InvestmentPersonImpactProfile.workspace_id == workspace_id,
                        InvestmentPersonImpactProfile.person_source_id == person.id,
                    )
                )
            sample = int(profile.sample_count) if profile else 0
            evidence = (
                int(
                    self.session.scalar(
                        select(InvestmentFact.id)
                        .where(InvestmentFact.workspace_id == workspace_id)
                        .count()
                    )
                    or 0
                )
                if False
                else len(
                    list(
                        self.session.scalars(
                            select(InvestmentFact.id)
                            .where(InvestmentFact.workspace_id == workspace_id)
                            .limit(100)
                        )
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
        self, workspace_id: str, platform: str | None = None
    ) -> list[InvestmentAccountRecommendation]:
        stmt = select(InvestmentAccountRecommendation).where(
            InvestmentAccountRecommendation.workspace_id == workspace_id
        )
        if platform:
            stmt = stmt.where(InvestmentAccountRecommendation.platform == platform)
        return list(
            self.session.scalars(stmt.order_by(InvestmentAccountRecommendation.updated_at.desc()))
        )

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
        src = self.session.scalar(
            select(InvestmentSource).where(
                InvestmentSource.workspace_id == workspace_id,
                InvestmentSource.source_type == "x_web",
                InvestmentSource.config["username"].as_string() == rec.handle,
            )
        )
        if src is None:
            src = InvestmentSource(
                id=_id("src"),
                workspace_id=workspace_id,
                source_type="x_web",
                name=rec.display_name or rec.handle,
                config={"mode": "account", "username": rec.handle, "max_items_per_poll": 50},
                default_info_layer="human_source",
                default_watchlist_ids=list(payload.theme_ids or []),
                poll_interval_seconds=payload.poll_interval_seconds,
                enabled=True,
            )
            self.session.add(src)
            self.session.flush()
        job = self.session.scalar(
            select(TaskJob).where(
                TaskJob.workspace_id == workspace_id,
                TaskJob.job_type == X_WEB_COLLECT_JOB_TYPE,
                TaskJob.target_id == src.id,
                TaskJob.status.in_(("pending", "running")),
            )
        )
        if job is None:
            self.session.add(
                TaskJob(
                    id=_id("job"),
                    workspace_id=workspace_id,
                    job_type=X_WEB_COLLECT_JOB_TYPE,
                    target_type="investment_source",
                    target_id=src.id,
                    status="pending",
                    input={"source_id": src.id},
                )
            )
        rec.source_id, rec.status = src.id, "followed"
        self.session.commit()
        return src

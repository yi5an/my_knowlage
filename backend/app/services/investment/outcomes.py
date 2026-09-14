from __future__ import annotations
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.core.errors import AppError
from app.infrastructure.models import (InvestmentRecommendationOutcome,InvestmentOpportunityCandidate,InvestmentAccountRecommendation,InvestmentUserContext,InvestmentTheme,InvestmentWatchlist)
from app.schemas.investment import RecommendationOutcomeCreate, UserInvestmentContextUpdate

@dataclass
class CalibrationResult:
    changed: bool
    version: int
    weights: dict[str,float]
    reason: str

class OutcomeService:
    def __init__(self, session: Session): self.session=session
    def get_user_context(self, workspace_id:str):
        row=self.session.scalar(select(InvestmentUserContext).where(InvestmentUserContext.workspace_id==workspace_id))
        if row: return row
        row=InvestmentUserContext(id=f'ctx_{uuid4().hex}',workspace_id=workspace_id)
        self.session.add(row); self.session.commit(); self.session.refresh(row); return row
    def update_user_context(self, workspace_id:str, payload:UserInvestmentContextUpdate):
        for model, ids in ((InvestmentTheme,payload.focus_theme_ids),(InvestmentWatchlist,payload.excluded_watchlist_ids)):
            if ids:
                found=set(self.session.scalars(select(model.id).where(model.workspace_id==workspace_id, model.id.in_(ids))))
                if found != set(ids): raise AppError('not_found','referenced resource not found',404)
        row=self.get_user_context(workspace_id)
        for f in ('markets','horizons','focus_theme_ids','excluded_watchlist_ids','min_liquidity','exposure_notes'):
            setattr(row,f,getattr(payload,f))
        self.session.commit(); self.session.refresh(row); return row
    def record(self,payload:RecommendationOutcomeCreate):
        if payload.opportunity_id:
            obj=self.session.get(InvestmentOpportunityCandidate,payload.opportunity_id)
            if not obj or obj.workspace_id!=payload.workspace_id: raise AppError('not_found','opportunity not found',404)
        if payload.recommendation_id:
            obj=self.session.get(InvestmentAccountRecommendation,payload.recommendation_id)
            if not obj or obj.workspace_id!=payload.workspace_id: raise AppError('not_found','recommendation not found',404)
        row=InvestmentRecommendationOutcome(id=f'out_{uuid4().hex}',**payload.model_dump())
        self.session.add(row); self.session.commit(); self.session.refresh(row); return row
    def list_for_opportunity(self, opportunity_id:str, workspace_id:str):
        obj=self.session.get(InvestmentOpportunityCandidate,opportunity_id)
        if not obj or obj.workspace_id!=workspace_id: raise AppError('not_found','opportunity not found',404)
        return list(self.session.scalars(select(InvestmentRecommendationOutcome).where(InvestmentRecommendationOutcome.opportunity_id==opportunity_id,InvestmentRecommendationOutcome.workspace_id==workspace_id).order_by(InvestmentRecommendationOutcome.observed_at.desc())))
    def recalculate_recommendation_weights(self, workspace_id:str, as_of:datetime|None=None):
        cutoff=as_of or datetime.now(UTC)
        rows=list(self.session.scalars(select(InvestmentRecommendationOutcome).where(InvestmentRecommendationOutcome.workspace_id==workspace_id,InvestmentRecommendationOutcome.observed_at<=cutoff)))
        if len(rows)<10: return CalibrationResult(False,0,{},'样本不足：至少需要 10 条结果')
        validated=sum(r.outcome_status=='validated' for r in rows); invalid=sum(r.outcome_status=='invalidated' for r in rows)
        total=validated+invalid; weights={'validated_rate': validated/total if total else 0.0}
        return CalibrationResult(True,1,weights,'基于历史结果完成校准')

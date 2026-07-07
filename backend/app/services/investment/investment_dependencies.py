"""FastAPI dependency factories for the investment module."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.infrastructure.database import get_db_session
from app.services.investment.service import InvestmentService

DB_SESSION_DEPENDENCY = Depends(get_db_session)


def get_investment_service(
    session: Session = DB_SESSION_DEPENDENCY,
) -> InvestmentService:
    return InvestmentService(session=session)

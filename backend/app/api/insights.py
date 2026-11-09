"""
SHEM Backend — Insights & analytics (metered telemetry + simulated appliances)
GET /api/insights?period=week|month|year
GET /api/insights/today?date=YYYY-MM-DD        (date optional, local; defaults to today)
GET /api/insights/days?days=14&end=YYYY-MM-DD  (per-day totals for the day picker strip)
GET /api/insights/recommendations
"""

from __future__ import annotations

from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.schemas import DailyTotalsResponse, EnergyRecommendation, InsightsResponse, TodayInsightsResponse
from app.services.insights_service import (
    compute_daily_totals,
    compute_insights,
    compute_recommendations,
    compute_today_insights,
)

router = APIRouter()

_DATE = r"^\d{4}-\d{2}-\d{2}$"


@router.get("/insights", response_model=InsightsResponse, tags=["Insights"])
def get_insights(
    period: Literal["week", "month", "year"] = Query("week"),
    db: Session = Depends(get_db),
) -> InsightsResponse:
    return compute_insights(db, period)


@router.get("/insights/today", response_model=TodayInsightsResponse, tags=["Insights"])
def get_today_insights(
    date: Optional[str] = Query(None, pattern=_DATE, description="Local date YYYY-MM-DD (default: today)"),
    db: Session = Depends(get_db),
) -> TodayInsightsResponse:
    try:
        return compute_today_insights(db, date=date)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.get("/insights/days", response_model=DailyTotalsResponse, tags=["Insights"])
def get_daily_totals(
    days: int = Query(14, ge=1, le=62),
    end: Optional[str] = Query(None, pattern=_DATE, description="Last local date shown (default: today)"),
    db: Session = Depends(get_db),
) -> DailyTotalsResponse:
    try:
        return compute_daily_totals(db, days=days, end_date=end)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.get("/insights/recommendations", response_model=List[EnergyRecommendation], tags=["Insights"])
def get_recommendations(db: Session = Depends(get_db)) -> List[EnergyRecommendation]:
    return compute_recommendations(db)

"""
SHEM Backend — Energy target
GET /api/target   → {monthlyBudgetINR, targetType, isConfigured, monthlyTargetKWh, updatedAt}
PUT /api/target   {"monthlyBudgetINR": 1800, "targetType": "budget"}   (₹100 – ₹100 000)
DELETE /api/target → back to "not configured"
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.db_models import EnergyTarget
from app.models.schemas import EnergyTargetSchema, EnergyTargetUpdate
from app.services.insights_service import _tariff
from app.utils.timestamps import utcnow

router = APIRouter()


def _get_or_create(db: Session) -> EnergyTarget:
    target = db.get(EnergyTarget, 1)
    if target is None:
        now = utcnow()
        target = EnergyTarget(id=1, monthly_budget_inr=0.0, target_type="budget", is_configured=False,
                              created_at=now, updated_at=now)
        db.add(target)
        db.commit()
        db.refresh(target)
    return target


def _to_schema(db: Session, target: EnergyTarget) -> EnergyTargetSchema:
    out = EnergyTargetSchema.model_validate(target)
    if target.is_configured:
        out.monthly_target_kwh = round(target.monthly_budget_inr / _tariff(db), 2)
    return out


@router.get("/target", response_model=EnergyTargetSchema, tags=["Target"])
def get_target(db: Session = Depends(get_db)) -> EnergyTargetSchema:
    return _to_schema(db, _get_or_create(db))


@router.put("/target", response_model=EnergyTargetSchema, tags=["Target"])
def update_target(update_in: EnergyTargetUpdate, db: Session = Depends(get_db)) -> EnergyTargetSchema:
    target = _get_or_create(db)
    target.monthly_budget_inr = update_in.monthly_budget_inr
    target.target_type = update_in.target_type
    target.is_configured = True
    target.updated_at = utcnow()
    db.commit()
    db.refresh(target)
    return _to_schema(db, target)


@router.delete("/target", status_code=status.HTTP_204_NO_CONTENT, tags=["Target"])
def clear_target(db: Session = Depends(get_db)) -> Response:
    target = _get_or_create(db)
    target.monthly_budget_inr = 0.0
    target.target_type = "budget"
    target.is_configured = False
    target.updated_at = utcnow()
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

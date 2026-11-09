"""
SHEM Backend — Electricity bills (user-entered records; separate from meter data)
"""

from __future__ import annotations

import logging
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api._crud import apply_partial_update
from app.config import get_settings
from app.database import get_db
from app.models.db_models import ElectricityBill
from app.models.schemas import ElectricityBillCreate, ElectricityBillSchema, ElectricityBillUpdate
from app.utils.rate_limit import limiter
from app.utils.timestamps import utcnow

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


@router.get("/bills", response_model=List[ElectricityBillSchema], tags=["Bills"])
def list_bills(db: Session = Depends(get_db)) -> List[ElectricityBillSchema]:
    """Most recent billing period first (bills without a period last, newest entry first)."""
    stmt = select(ElectricityBill).order_by(
        ElectricityBill.billing_year.is_(None),
        desc(ElectricityBill.billing_year),
        desc(ElectricityBill.billing_month),
        desc(ElectricityBill.created_at),
    )
    return [ElectricityBillSchema.model_validate(b) for b in db.scalars(stmt).all()]


@router.post("/bills", response_model=ElectricityBillSchema, status_code=status.HTTP_201_CREATED, tags=["Bills"])
@limiter.limit(settings.rate_limit_bills_create)
def create_bill(request: Request, bill_in: ElectricityBillCreate, db: Session = Depends(get_db)) -> ElectricityBillSchema:
    bill_id = bill_in.id or f"bill-{uuid.uuid4().hex[:8]}"
    if db.get(ElectricityBill, bill_id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Bill '{bill_id}' already exists.")
    bill = ElectricityBill(**bill_in.model_dump(exclude={"id"}, by_alias=False), id=bill_id, created_at=utcnow())
    db.add(bill)
    db.commit()
    db.refresh(bill)
    return ElectricityBillSchema.model_validate(bill)


@router.put("/bills/{bill_id}", response_model=ElectricityBillSchema, tags=["Bills"])
def update_bill(bill_id: str, update_in: ElectricityBillUpdate, db: Session = Depends(get_db)) -> ElectricityBillSchema:
    bill = db.get(ElectricityBill, bill_id)
    if bill is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bill not found.")
    apply_partial_update(bill, update_in, non_nullable=("units_consumed_kwh", "bill_amount_inr"))
    db.commit()
    db.refresh(bill)
    return ElectricityBillSchema.model_validate(bill)


@router.delete("/bills/{bill_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Bills"])
def delete_bill(bill_id: str, db: Session = Depends(get_db)) -> Response:
    bill = db.get(ElectricityBill, bill_id)
    if bill is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bill not found.")
    db.delete(bill)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

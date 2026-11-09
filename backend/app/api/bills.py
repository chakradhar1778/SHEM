"""
SHEM Backend — Electricity bills (user-entered records; separate from meter data)
"""

from __future__ import annotations

import logging
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api._crud import apply_partial_update
from app.config import get_settings
from app.database import get_db
from app.models.db_models import ElectricityBill
from app.models.schemas import ElectricityBillCreate, ElectricityBillSchema, ElectricityBillUpdate
from app.services import document_store
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
    path = bill.document_path
    db.delete(bill)
    db.commit()
    document_store.delete(path)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Bill document (image / PDF kept for viewing; not parsed) ──────────────────

def _bill_or_404(db: Session, bill_id: str) -> ElectricityBill:
    bill = db.get(ElectricityBill, bill_id)
    if bill is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bill not found.")
    return bill


@router.put("/bills/{bill_id}/document", response_model=ElectricityBillSchema, tags=["Bills"])
@limiter.limit(settings.rate_limit_bills_create)
async def upload_bill_document(
    request: Request, bill_id: str,
    filename: str | None = Query(None, max_length=255, description="Original file name, for display"),
    db: Session = Depends(get_db),
) -> ElectricityBillSchema:
    """Raw file in the body (JPG, PNG, WebP or PDF; Content-Type set accordingly), max MAX_BILL_DOCUMENT_MB."""
    bill = _bill_or_404(db, bill_id)
    limit = int(settings.max_bill_document_mb * 1024 * 1024)
    declared_len = request.headers.get("content-length")
    if declared_len and declared_len.isdigit() and int(declared_len) > limit:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"File too large (max {settings.max_bill_document_mb:g} MB).")
    data = await request.body()
    try:
        ctype = document_store.validate(data, request.headers.get("content-type", ""))
    except document_store.DocumentError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    rel, size = document_store.save(bill.id, data, ctype, previous=bill.document_path)
    bill.document_path, bill.document_content_type, bill.document_size = rel, ctype, size
    bill.document_uploaded_at = utcnow()
    if filename:
        bill.document_filename = filename.replace("/", "_").replace("\\", "_").strip()[:255] or None
    db.commit()
    db.refresh(bill)
    return ElectricityBillSchema.model_validate(bill)


@router.get("/bills/{bill_id}/document", tags=["Bills"])
def get_bill_document(bill_id: str, db: Session = Depends(get_db)) -> FileResponse:
    bill = _bill_or_404(db, bill_id)
    path = document_store.resolve(bill.document_path) if bill.document_path else None
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No document stored for this bill.")
    name = bill.document_filename or f"bill-{bill.id}{path.suffix}"
    return FileResponse(path, media_type=bill.document_content_type or "application/octet-stream",
                        filename=name, content_disposition_type="inline",
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})


@router.delete("/bills/{bill_id}/document", response_model=ElectricityBillSchema, tags=["Bills"])
def delete_bill_document(bill_id: str, db: Session = Depends(get_db)) -> ElectricityBillSchema:
    bill = _bill_or_404(db, bill_id)
    document_store.delete(bill.document_path)
    bill.document_path = bill.document_content_type = bill.document_size = bill.document_uploaded_at = None
    db.commit()
    db.refresh(bill)
    return ElectricityBillSchema.model_validate(bill)

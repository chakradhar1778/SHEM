"""
SHEM Backend — Household configuration
GET /api/household/config   (seeds defaults on first call)
PUT /api/household/config   (partial update)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api._crud import apply_partial_update
from app.config import get_settings
from app.database import get_db
from app.models.db_models import HouseholdConfig
from app.models.schemas import HouseholdConfigSchema, HouseholdConfigUpdate
from app.utils.timestamps import utcnow

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


def get_or_create_config(db: Session) -> HouseholdConfig:
    cfg = db.get(HouseholdConfig, 1)
    if cfg is None:
        cfg = HouseholdConfig(
            id=1, home_name="My Home", home_type="Apartment", occupants=2,
            tariff_rate_inr_per_kwh=settings.default_tariff_rate_inr_per_kwh, updated_at=utcnow(),
        )
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
        logger.info("Seeded default household configuration")
    return cfg


@router.get("/household/config", response_model=HouseholdConfigSchema, tags=["Household"])
def get_household_config(db: Session = Depends(get_db)) -> HouseholdConfigSchema:
    return HouseholdConfigSchema.model_validate(get_or_create_config(db))


@router.put("/household/config", response_model=HouseholdConfigSchema, tags=["Household"])
def update_household_config(data: HouseholdConfigUpdate, db: Session = Depends(get_db)) -> HouseholdConfigSchema:
    cfg = get_or_create_config(db)
    apply_partial_update(cfg, data, non_nullable=("home_name", "home_type", "occupants", "tariff_rate_inr_per_kwh", "is_configured"))
    cfg.updated_at = utcnow()
    db.commit()
    db.refresh(cfg)
    return HouseholdConfigSchema.model_validate(cfg)

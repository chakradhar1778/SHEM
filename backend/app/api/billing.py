"""
SHEM Backend — Bill model
GET  /api/billing/tariff        tariff used for every cost figure (flat or slabs + fixed/fuel/duty + cycle day)
PUT  /api/billing/tariff        partial update
GET  /api/billing/projection    current billing cycle: usage and bill so far, projected bill, budget status
POST /api/billing/estimate      {"kwh": 250} → itemised bill for that many units in one cycle
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.household import get_or_create_config
from app.database import get_db
from app.models.schemas import (
    BillBreakdownSchema,
    BillEstimateRequest,
    BillLine,
    BillProjectionResponse,
    BudgetStatus,
    TariffSchema,
    TariffSlab,
    TariffUpdate,
)
from app.services import billing_service as bs
from app.utils.timestamps import utcnow

router = APIRouter()

DISCLAIMER = ("Estimate from your tariff settings and metered + simulated usage at the current pace. "
              "The utility bill may differ (meter reading date, arrears, rebates, rounding).")


def tariff_schema(cfg) -> TariffSchema:
    t = bs.tariff_from_config(cfg)
    return TariffSchema(
        mode=t.mode, flat_rate_inr=t.flat_rate,
        slabs=[TariffSlab(upto_kwh=s.upto_kwh, rate_inr=s.rate) for s in bs.parse_slabs(cfg.tariff_slabs_json)],
        fixed_charge_inr=t.fixed_charge, fuel_adjustment_inr_per_kwh=t.fuel_per_kwh,
        electricity_duty_percent=t.duty_percent, billing_cycle_day=t.cycle_day,
        utility_provider=cfg.utility_provider,
    )


def breakdown_schema(b: bs.BillBreakdown) -> BillBreakdownSchema:
    return BillBreakdownSchema(
        kwh=b.kwh,
        lines=[BillLine(label=ln.label, from_kwh=ln.from_kwh, to_kwh=ln.to_kwh, kwh=ln.kwh, rate_inr=ln.rate,
                        amount_inr=ln.amount) for ln in b.lines],
        energy_charge_inr=b.energy_charge, fuel_charge_inr=b.fuel_charge, duty_inr=b.duty,
        fixed_charge_inr=b.fixed_charge, total_inr=b.total, effective_rate_inr=b.effective_rate,
        variable_rate_inr=b.variable_rate, marginal_rate_inr=b.marginal_rate, slab_index=b.slab_index,
        kwh_to_next_slab=b.kwh_to_next_slab, next_slab_rate_inr=b.next_slab_rate,
    )


@router.get("/billing/tariff", response_model=TariffSchema, tags=["Billing"])
def get_tariff(db: Session = Depends(get_db)) -> TariffSchema:
    return tariff_schema(get_or_create_config(db))


@router.put("/billing/tariff", response_model=TariffSchema, tags=["Billing"])
def update_tariff(body: TariffUpdate, db: Session = Depends(get_db)) -> TariffSchema:
    cfg = get_or_create_config(db)
    fields = body.model_fields_set
    if body.slabs is not None:
        slabs = [bs.Slab(s.upto_kwh, s.rate_inr) for s in body.slabs]
        err = bs.validate_slabs(slabs)
        if err:
            raise HTTPException(422, err)
        cfg.tariff_slabs_json = bs.slabs_to_json(slabs)
    if "mode" in fields and body.mode:
        if body.mode == "slab" and not bs.parse_slabs(cfg.tariff_slabs_json):
            raise HTTPException(422, "Add slabs before switching to slab mode.")
        cfg.tariff_mode = body.mode
    for name, attr in (("flat_rate_inr", "tariff_rate_inr_per_kwh"), ("fixed_charge_inr", "fixed_charge_inr"),
                       ("fuel_adjustment_inr_per_kwh", "fuel_adjustment_inr_per_kwh"),
                       ("electricity_duty_percent", "electricity_duty_percent"),
                       ("billing_cycle_day", "billing_cycle_day")):
        value = getattr(body, name)
        if name in fields and value is not None:
            setattr(cfg, attr, value)
    cfg.updated_at = utcnow()
    db.commit()
    db.refresh(cfg)
    bs.clear_rate_cache()
    return tariff_schema(cfg)


def build_projection(db: Session) -> BillProjectionResponse:
    cfg = get_or_create_config(db)
    proj = bs.project_cycle(db, bs.tariff_from_config(cfg))
    budget = bs.budget_status(db, proj)
    return BillProjectionResponse(
        cycle_start=proj["cycle_start"].isoformat(), cycle_end=proj["cycle_end"].isoformat(),
        cycle_days=round(proj["total_days"]), elapsed_days=round(proj["elapsed_days"], 2),
        days_left=round(max(proj["total_days"] - proj["elapsed_days"], 0.0), 2),
        used_kwh=round(proj["used_kwh"], 3), metered_kwh=round(proj["metered_kwh"], 3),
        simulated_kwh=round(proj["simulated_kwh"], 3), daily_kwh=round(proj["daily_kwh"], 3),
        projected_kwh=round(proj["projected_kwh"], 3), pace_basis=proj["basis"], confidence=proj["confidence"],
        so_far=breakdown_schema(proj["so_far"]), projected=breakdown_schema(proj["projected"]),
        tariff=tariff_schema(cfg), budget=BudgetStatus(**budget) if budget else None, disclaimer=DISCLAIMER,
    )


@router.get("/billing/projection", response_model=BillProjectionResponse, tags=["Billing"])
def get_projection(db: Session = Depends(get_db)) -> BillProjectionResponse:
    return build_projection(db)


@router.post("/billing/estimate", response_model=BillBreakdownSchema, tags=["Billing"])
def estimate_bill(body: BillEstimateRequest, db: Session = Depends(get_db)) -> BillBreakdownSchema:
    return breakdown_schema(bs.compute_bill(body.kwh, bs.load_tariff(db)))

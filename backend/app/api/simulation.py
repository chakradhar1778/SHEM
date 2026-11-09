"""
SHEM Backend — Simulated appliances
GET  /api/simulation/status                         live power/state of every simulated appliance
POST /api/simulation/appliances/{id}/command        {"state": "ON" | "OFF"}  — the app's on/off switch
POST /api/simulation/appliances/{id}/auto           clear the manual override (back to the daily routine)

Appliances WITHOUT a relay channel are simulated (see services/simulation_service.py).
Unlike the physical relay, a simulated switch applies immediately (status 200, not 202).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.db_models import Appliance
from app.models.schemas import SimCommandRequest, SimStatusResponse
from app.services.broadcaster import broadcaster
from app.services.simulation_service import simulator

router = APIRouter()


def _simulated(db: Session, appliance_id: str) -> Appliance:
    item = db.get(Appliance, appliance_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Appliance not found.")
    if not item.is_simulated:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"'{item.name}' is wired to relay {item.relay_channel}; use the relay command instead.")
    return item


@router.get("/simulation/status", response_model=SimStatusResponse, tags=["Simulation"])
def simulation_status(db: Session = Depends(get_db)) -> SimStatusResponse:
    return SimStatusResponse.model_validate(simulator.tick(db))


@router.post("/simulation/appliances/{appliance_id}/command", response_model=SimStatusResponse, tags=["Simulation"])
def simulation_command(appliance_id: str, body: SimCommandRequest, db: Session = Depends(get_db)) -> SimStatusResponse:
    item = _simulated(db, appliance_id)
    payload = simulator.command(db, item, body.state)
    broadcaster.publish_from_thread("sim_update", payload)
    return SimStatusResponse.model_validate(payload)


@router.post("/simulation/appliances/{appliance_id}/auto", response_model=SimStatusResponse, tags=["Simulation"])
def simulation_auto(appliance_id: str, db: Session = Depends(get_db)) -> SimStatusResponse:
    item = _simulated(db, appliance_id)
    simulator.clear_override(db, item)
    payload = simulator.tick(db)
    broadcaster.publish_from_thread("sim_update", payload)
    return SimStatusResponse.model_validate(payload)

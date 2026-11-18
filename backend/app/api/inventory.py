"""
SHEM Backend — Inventory (rooms & appliances)
Deleting a room unassigns its appliances (room_id = null); it never deletes them.
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api._crud import apply_partial_update
from app.database import get_db
from app.models.db_models import Appliance, Room
from app.models.schemas import (
    ApplianceCreate,
    ApplianceSchema,
    ApplianceUpdate,
    RoomCreate,
    RoomSchema,
    RoomUpdate,
)
from app.utils.timestamps import utcnow

logger = logging.getLogger(__name__)
router = APIRouter()

# IDs match the frontend floor-plan layout (FloorPlanMap CSS classes).
DEFAULT_ROOMS = [
    {"id": "room-living", "name": "Living Room", "room_type": "living", "floor": 1},
    {"id": "room-kitchen", "name": "Kitchen", "room_type": "kitchen", "floor": 1},
    {"id": "room-master-bed", "name": "Master Bedroom", "room_type": "bedroom", "floor": 1},
    {"id": "room-bathroom", "name": "Bathroom", "room_type": "bathroom", "floor": 1},
    {"id": "room-balcony", "name": "Balcony", "room_type": "balcony", "floor": 1},
]


def _seed_rooms_if_empty(db: Session) -> None:
    if db.scalar(select(Room.id).limit(1)) is None:
        now = utcnow()
        # staggered created_at keeps the display order stable
        db.add_all(Room(created_at=now + timedelta(microseconds=i), **r) for i, r in enumerate(DEFAULT_ROOMS))
        db.commit()
        logger.info("Seeded %d default rooms", len(DEFAULT_ROOMS))


def _require_room(db: Session, room_id: Optional[str]) -> None:
    if room_id is not None and db.get(Room, room_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Room '{room_id}' does not exist.")


def _require_free_relay_channel(
    db: Session,
    channel: Optional[int],
    exclude_id: Optional[str] = None,
    replace_owner: bool = False,
) -> None:
    if channel is None:
        return
    stmt = select(Appliance).where(Appliance.relay_channel == channel)
    if exclude_id:
        stmt = stmt.where(Appliance.id != exclude_id)
    owners = list(db.scalars(stmt).all())
    if not owners:
        return
    if not replace_owner:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Relay channel {channel} is already assigned to '{owners[0].name}'.",
        )
    now = utcnow()
    for owner in owners:
        owner.relay_channel = None
        owner.last_relay_channel = channel
        owner.status = "off"
        owner.sim_manual_state = "OFF"
        owner.sim_override_until = None
        owner.updated_at = now
    # Any open mismatch notifications for this relay are now resolved.
    from app.models.db_models import Notification
    db.execute(
        update(Notification)
        .where(Notification.kind == "relay_mismatch", Notification.read_at.is_(None))
        .values(read_at=now)
    )


# ── Rooms ──────────────────────────────────────────────────────────────────────

@router.get("/inventory/rooms", response_model=List[RoomSchema], tags=["Inventory"])
def list_rooms(db: Session = Depends(get_db)) -> List[RoomSchema]:
    _seed_rooms_if_empty(db)
    rooms = db.scalars(select(Room).order_by(Room.created_at, Room.name)).all()
    return [RoomSchema.model_validate(r) for r in rooms]


@router.post("/inventory/rooms", response_model=RoomSchema, status_code=status.HTTP_201_CREATED, tags=["Inventory"])
def create_room(room_in: RoomCreate, db: Session = Depends(get_db)) -> RoomSchema:
    _seed_rooms_if_empty(db)  # so a first custom room doesn't suppress the defaults
    room_id = room_in.id or f"room-{uuid.uuid4().hex[:8]}"
    if db.get(Room, room_id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Room '{room_id}' already exists.")
    room = Room(id=room_id, name=room_in.name, room_type=room_in.room_type, floor=room_in.floor, created_at=utcnow())
    db.add(room)
    db.commit()
    db.refresh(room)
    return RoomSchema.model_validate(room)


@router.put("/inventory/rooms/{room_id}", response_model=RoomSchema, tags=["Inventory"])
def update_room(room_id: str, update_in: RoomUpdate, db: Session = Depends(get_db)) -> RoomSchema:
    room = db.get(Room, room_id)
    if room is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Room not found.")
    apply_partial_update(room, update_in, non_nullable=("name",))
    db.commit()
    db.refresh(room)
    return RoomSchema.model_validate(room)


@router.delete("/inventory/rooms/{room_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Inventory"])
def delete_room(room_id: str, db: Session = Depends(get_db)) -> Response:
    room = db.get(Room, room_id)
    if room is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Room not found.")
    db.execute(update(Appliance).where(Appliance.room_id == room_id).values(room_id=None, updated_at=utcnow()))
    db.delete(room)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Appliances ─────────────────────────────────────────────────────────────────

@router.get("/inventory/appliances", response_model=List[ApplianceSchema], tags=["Inventory"])
def list_appliances(
    room_id: Optional[str] = Query(None, alias="roomId", description="Optional room filter"),
    db: Session = Depends(get_db),
) -> List[ApplianceSchema]:
    stmt = select(Appliance)
    if room_id:
        stmt = stmt.where(Appliance.room_id == room_id)
    return [ApplianceSchema.model_validate(a) for a in db.scalars(stmt.order_by(Appliance.name)).all()]


@router.post("/inventory/appliances", response_model=ApplianceSchema,
             status_code=status.HTTP_201_CREATED, tags=["Inventory"])
def create_appliance(app_in: ApplianceCreate, db: Session = Depends(get_db)) -> ApplianceSchema:
    _require_room(db, app_in.room_id)
    _require_free_relay_channel(db, app_in.relay_channel, replace_owner=app_in.replace_relay_owner)
    app_id = app_in.id or f"app-{uuid.uuid4().hex[:8]}"
    if db.get(Appliance, app_id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Appliance '{app_id}' already exists.")
    now = utcnow()
    data = app_in.model_dump(exclude={"id", "replace_relay_owner"}, by_alias=False)
    if app_in.relay_channel is not None:
        data["last_relay_channel"] = app_in.relay_channel
        if app_in.replace_relay_owner:
            data["status"] = "on"
            data["sim_manual_state"] = None
            data["sim_override_until"] = None
            from app.config import get_settings
            from app.services.device_service import upsert_relay_channel
            upsert_relay_channel(db, get_settings().device_id, app_in.relay_channel, "ON", now)
    item = Appliance(**data, id=app_id, created_at=now, updated_at=now)
    db.add(item)
    db.commit()
    db.refresh(item)
    if app_in.replace_relay_owner and app_in.relay_channel is not None:
        try:
            from app.config import get_settings
            from app.services.broadcaster import broadcaster
            from app.services.simulation_service import simulation_service
            sim_payload = simulation_service.tick(db, now)
            broadcaster.publish_from_thread("sim_update", sim_payload)
            broadcaster.publish_from_thread("relay_state", {
                "deviceId": get_settings().device_id,
                "channel": app_in.relay_channel,
                "state": "ON",
            })
        except Exception:
            pass
    return ApplianceSchema.model_validate(item)


@router.put("/inventory/appliances/{appliance_id}", response_model=ApplianceSchema, tags=["Inventory"])
def update_appliance(appliance_id: str, update_in: ApplianceUpdate, db: Session = Depends(get_db)) -> ApplianceSchema:
    item = db.get(Appliance, appliance_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Appliance not found.")
    if "room_id" in update_in.model_fields_set:
        _require_room(db, update_in.room_id)
    prev_relay = item.relay_channel
    if "relay_channel" in update_in.model_fields_set:
        _require_free_relay_channel(
            db,
            update_in.relay_channel,
            exclude_id=appliance_id,
            replace_owner=update_in.replace_relay_owner,
        )
    was_simulated, was_auto = item.is_simulated, item.sim_auto
    apply_partial_update(
        item,
        update_in,
        non_nullable=("name", "quantity", "daily_hours", "status", "sim_auto"),
        exclude=("replace_relay_owner",),
    )
    if item.relay_channel is not None:
        item.last_relay_channel = item.relay_channel
    elif prev_relay is not None:
        item.last_relay_channel = prev_relay
    # Switching between relay and simulation, or toggling the routine, drops any manual override.
    if item.is_simulated != was_simulated or item.sim_auto != was_auto:
        item.sim_manual_state = None
        item.sim_override_until = None
        if not item.is_simulated:
            item.status = "off"
    if item.relay_channel is not None and update_in.replace_relay_owner:
        item.status = "on"
        item.sim_manual_state = None
        item.sim_override_until = None
        from app.config import get_settings
        from app.services.device_service import upsert_relay_channel
        upsert_relay_channel(db, get_settings().device_id, item.relay_channel, "ON", utcnow())
    item.updated_at = utcnow()
    db.commit()
    db.refresh(item)
    if item.relay_channel is not None and update_in.replace_relay_owner:
        try:
            from app.config import get_settings
            from app.services.broadcaster import broadcaster
            from app.services.simulation_service import simulation_service
            sim_payload = simulation_service.tick(db, item.updated_at)
            broadcaster.publish_from_thread("sim_update", sim_payload)
            broadcaster.publish_from_thread("relay_state", {
                "deviceId": get_settings().device_id,
                "channel": item.relay_channel,
                "state": "ON",
            })
        except Exception:
            pass
    return ApplianceSchema.model_validate(item)


@router.delete("/inventory/appliances/{appliance_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Inventory"])
def delete_appliance(appliance_id: str, db: Session = Depends(get_db)) -> Response:
    item = db.get(Appliance, appliance_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Appliance not found.")
    db.delete(item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

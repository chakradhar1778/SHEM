"""
SHEM Backend — Notifications (the app's bell) and the budget saver
GET  /api/notifications?limit=50          newest first + unread count
POST /api/notifications/{id}/read
POST /api/notifications/read-all
POST /api/notifications/check             run the alert checks now (also run every ALERTS_INTERVAL_SECONDS)
GET  /api/automation/budget-saver         mode, trigger, non-essential appliances, recent actions
PUT  /api/automation/budget-saver         {"mode": "off"|"suggest"|"auto", "trigger": "at_risk"|"over"}
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api.target import _get_or_create as get_target_row
from app.database import get_db
from app.models.db_models import AutomationLog, Notification
from app.models.schemas import (
    AutomationLogEntry,
    BudgetSaverSettings,
    BudgetSaverUpdate,
    NotificationList,
    NotificationSchema,
    SaverCandidate,
)
from app.services import alerts_service
from app.services.broadcaster import broadcaster
from app.utils.timestamps import utcnow

router = APIRouter()


def _list(db: Session, limit: int) -> NotificationList:
    items = db.scalars(select(Notification).order_by(Notification.created_at.desc(), Notification.id.desc())
                       .limit(limit)).all()
    unread = db.scalar(select(func.count()).select_from(Notification).where(Notification.read_at.is_(None))) or 0
    return NotificationList(items=[NotificationSchema.model_validate(n) for n in items], unread_count=unread)


@router.get("/notifications", response_model=NotificationList, tags=["Notifications"])
def list_notifications(limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)) -> NotificationList:
    return _list(db, limit)


@router.post("/notifications/read-all", response_model=NotificationList, tags=["Notifications"])
def read_all(db: Session = Depends(get_db)) -> NotificationList:
    db.execute(update(Notification).where(Notification.read_at.is_(None)).values(read_at=utcnow()))
    db.commit()
    return _list(db, 50)


@router.post("/notifications/check", response_model=NotificationList, tags=["Notifications"])
def check_now(request: Request, db: Session = Depends(get_db)) -> NotificationList:
    out = alerts_service.run_checks(db, getattr(request.app.state, "mqtt_client", None))
    for n in out["notifications"]:
        broadcaster.publish_from_thread("notification", alerts_service.notification_dict(n))
    if out["saver"]["sim_changed"]:
        from app.services.simulation_service import simulator
        broadcaster.publish_from_thread("sim_update", simulator.last_payload)
    return _list(db, 50)


@router.post("/notifications/{notification_id}/read", response_model=NotificationSchema, tags=["Notifications"])
def read_one(notification_id: int, db: Session = Depends(get_db)) -> NotificationSchema:
    n = db.get(Notification, notification_id)
    if n is None:
        raise HTTPException(404, "Notification not found.")
    if n.read_at is None:
        n.read_at = utcnow()
        db.commit()
        db.refresh(n)
    return NotificationSchema.model_validate(n)


def _saver(db: Session) -> BudgetSaverSettings:
    t = get_target_row(db)
    log = db.scalars(select(AutomationLog).order_by(AutomationLog.created_at.desc(), AutomationLog.id.desc())
                     .limit(20)).all()
    return BudgetSaverSettings(
        mode=t.saver_mode or "off", trigger=t.saver_trigger or "at_risk",
        budget_configured=bool(t.is_configured and t.monthly_budget_inr > 0),
        candidates=[SaverCandidate(appliance_id=a.id, name=a.name, icon_type=a.icon_type,
                                   is_on=alerts_service._is_on(db, a), simulated=a.relay_channel is None)
                    for a in alerts_service.saver_candidates(db)],
        log=[AutomationLogEntry.model_validate(e) for e in log],
    )


@router.get("/automation/budget-saver", response_model=BudgetSaverSettings, tags=["Automation"])
def get_budget_saver(db: Session = Depends(get_db)) -> BudgetSaverSettings:
    return _saver(db)


@router.put("/automation/budget-saver", response_model=BudgetSaverSettings, tags=["Automation"])
def update_budget_saver(body: BudgetSaverUpdate, db: Session = Depends(get_db)) -> BudgetSaverSettings:
    t = get_target_row(db)
    if body.mode is not None:
        t.saver_mode = body.mode
    if body.trigger is not None:
        t.saver_trigger = body.trigger
    t.updated_at = utcnow()
    db.commit()
    return _saver(db)

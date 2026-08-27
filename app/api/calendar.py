from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers.calendar_controller import calendar_controller
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.calendar import EventCreate, EventRead, EventUpdate

router = APIRouter(tags=["calendar"])


@router.post("/events", response_model=EventRead, status_code=201)
def create_event(
    payload: EventCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return calendar_controller.create(db, current_user.id, payload)


@router.get("/events", response_model=list[EventRead])
def list_events(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return calendar_controller.list(db, current_user.id)


@router.put("/events/{event_id}", response_model=EventRead)
def update_event(
    event_id: int,
    payload: EventUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return calendar_controller.update(db, event_id, current_user.id, payload)


@router.delete("/events/{event_id}")
def delete_event(
    event_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return calendar_controller.delete(db, event_id, current_user.id)

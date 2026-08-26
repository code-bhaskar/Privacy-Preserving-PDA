from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.controllers.calendar_controller import calendar_controller
from app.core.database import get_db
from app.schemas.calendar import EventCreate, EventRead, EventUpdate

router = APIRouter(tags=["calendar"])


@router.post("/events", response_model=EventRead, status_code=201)
def create_event(payload: EventCreate, db: Session = Depends(get_db)):
    return calendar_controller.create(db, payload)


@router.get("/events", response_model=list[EventRead])
def list_events(user_id: int = Query(...), db: Session = Depends(get_db)):
    return calendar_controller.list(db, user_id)


@router.put("/events/{event_id}", response_model=EventRead)
def update_event(event_id: int, payload: EventUpdate, db: Session = Depends(get_db)):
    return calendar_controller.update(db, event_id, payload)


@router.delete("/events/{event_id}")
def delete_event(event_id: int, db: Session = Depends(get_db)):
    return calendar_controller.delete(db, event_id)

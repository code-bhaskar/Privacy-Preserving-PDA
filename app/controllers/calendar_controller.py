from sqlalchemy.orm import Session
from app.schemas.calendar import EventCreate, EventUpdate
from app.services.scheduling_service import scheduling_service


class CalendarController:
    def create(self, db: Session, payload: EventCreate):
        return scheduling_service.create(db, payload)

    def list(self, db: Session, user_id: int):
        return scheduling_service.list(db, user_id)

    def update(self, db: Session, event_id: int, payload: EventUpdate):
        return scheduling_service.update(db, event_id, payload)

    def delete(self, db: Session, event_id: int):
        scheduling_service.delete(db, event_id)
        return {"deleted": event_id}


calendar_controller = CalendarController()

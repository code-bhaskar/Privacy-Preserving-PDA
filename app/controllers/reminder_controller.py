from sqlalchemy.orm import Session
from app.schemas.reminder import ReminderCreate, ReminderUpdate
from app.services.reminder_service import reminder_service


class ReminderController:
    def create(self, db: Session, payload: ReminderCreate):
        return reminder_service.create(db, payload)

    def list(self, db: Session, user_id: int):
        return reminder_service.list(db, user_id)

    def update(self, db: Session, reminder_id: int, payload: ReminderUpdate):
        return reminder_service.update(db, reminder_id, payload)

    def delete(self, db: Session, reminder_id: int):
        reminder_service.delete(db, reminder_id)
        return {"deleted": reminder_id}


reminder_controller = ReminderController()

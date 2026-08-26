from datetime import datetime
from sqlalchemy.orm import Session
from app.models.reminder import Reminder
from app.repositories.base_repository import BaseRepository


class ReminderRepository(BaseRepository[Reminder]):
    def __init__(self):
        super().__init__(Reminder)

    def due_before(self, db: Session, when: datetime) -> list[Reminder]:
        return (
            db.query(Reminder)
            .filter(Reminder.due_time <= when, Reminder.status == "pending")
            .all()
        )


reminder_repository = ReminderRepository()

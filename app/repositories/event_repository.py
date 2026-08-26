from sqlalchemy.orm import Session
from app.models.calendar_event import CalendarEvent
from app.repositories.base_repository import BaseRepository


class EventRepository(BaseRepository[CalendarEvent]):
    def __init__(self):
        super().__init__(CalendarEvent)

    def list_upcoming(self, db: Session, user_id: int, limit: int = 50):
        return (
            db.query(CalendarEvent)
            .filter(CalendarEvent.user_id == user_id)
            .order_by(CalendarEvent.start_time)
            .limit(limit)
            .all()
        )


event_repository = EventRepository()

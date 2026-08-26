from datetime import timedelta
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.calendar_event import CalendarEvent
from app.models.consent import ConsentCategory
from app.repositories.event_repository import event_repository
from app.schemas.calendar import EventCreate, EventUpdate
from app.services.audit_service import audit_service
from app.services.consent_service import consent_service


class SchedulingService:
    """FR-6: pure deterministic CRUD. No ML is invoked here."""
    CATEGORY = ConsentCategory.CALENDAR_DATA

    def create(self, db: Session, payload: EventCreate, via: str = "manual") -> CalendarEvent:
        consent_service.require(db, payload.user_id, self.CATEGORY)
        end = payload.end_time or payload.start_time + timedelta(hours=1)
        event = event_repository.save(db, CalendarEvent(
            user_id=payload.user_id, title=payload.title, participant=payload.participant,
            start_time=payload.start_time, end_time=end, created_via=via,
        ))
        audit_service.record(db, user_id=payload.user_id, action="EVENT_CREATED",
                             data_type="calendar",
                             reason=f"Event '{event.title}' created via {via}")
        return event

    def list(self, db: Session, user_id: int):
        consent_service.require(db, user_id, self.CATEGORY)
        audit_service.record(db, user_id=user_id, action="EVENTS_READ",
                             data_type="calendar", reason="User requested event list")
        return event_repository.list_upcoming(db, user_id)

    def update(self, db: Session, event_id: int, payload: EventUpdate) -> CalendarEvent:
        event = event_repository.get(db, event_id)
        if not event:
            raise NotFoundError("Event not found")
        consent_service.require(db, event.user_id, self.CATEGORY)
        for k, v in payload.model_dump(exclude_none=True).items():
            setattr(event, k, v)
        event = event_repository.save(db, event)
        audit_service.record(db, user_id=event.user_id, action="EVENT_UPDATED",
                             data_type="calendar", reason=f"Event {event_id} modified")
        return event

    def delete(self, db: Session, event_id: int) -> None:
        event = event_repository.get(db, event_id)
        if not event:
            raise NotFoundError("Event not found")
        consent_service.require(db, event.user_id, self.CATEGORY)
        uid = event.user_id
        event_repository.delete(db, event)
        audit_service.record(db, user_id=uid, action="EVENT_DELETED",
                             data_type="calendar", reason=f"Event {event_id} removed")


scheduling_service = SchedulingService()

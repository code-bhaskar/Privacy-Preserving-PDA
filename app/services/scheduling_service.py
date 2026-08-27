from datetime import timedelta
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.core.security import decrypt, encrypt
from app.models.calendar_event import CalendarEvent
from app.models.consent import ConsentCategory
from app.repositories.event_repository import event_repository
from app.schemas.calendar import EventCreate, EventUpdate
from app.services.audit_service import audit_service
from app.services.consent_service import consent_service


class SchedulingService:
    """FR-6: pure deterministic CRUD. Encrypted at rest via AES-256-GCM (FR-15)."""
    CATEGORY = ConsentCategory.CALENDAR_DATA

    def _decrypt_event(self, db: Session, event: CalendarEvent) -> CalendarEvent:
        if not event:
            return event
        # Eagerly access columns so detached object does not trigger lazy loading
        _ = (event.id, event.user_id, event.participant, event.start_time,
             event.end_time, event.created_via, event.created_at)
        db.expunge(event)
        try:
            event.title = decrypt(event.title, aad=str(event.user_id))
        except Exception:
            pass
        return event

    def create(self, db: Session, user_id: int, payload: EventCreate, via: str = "manual") -> CalendarEvent:
        consent_service.require(db, user_id, self.CATEGORY)
        end = payload.end_time or payload.start_time + timedelta(hours=1)

        # Encrypt title at rest with AES-256-GCM
        enc_title = encrypt(payload.title, aad=str(user_id))
        event = event_repository.save(db, CalendarEvent(
            user_id=user_id, title=enc_title, participant=payload.participant,
            start_time=payload.start_time, end_time=end, created_via=via,
        ))

        # Avoid leaking plaintext event title into audit logs
        audit_service.record(
            db, user_id=user_id, action="EVENT_CREATED",
            data_type="calendar",
            reason=f"Event {event.id} created via {via} (encrypted at rest)",
        )
        return self._decrypt_event(db, event)

    def list(self, db: Session, user_id: int):
        consent_service.require(db, user_id, self.CATEGORY)
        audit_service.record(
            db, user_id=user_id, action="EVENTS_READ",
            data_type="calendar", reason="User requested event list",
        )
        events = event_repository.list_upcoming(db, user_id)
        return [self._decrypt_event(db, ev) for ev in events]

    def update(self, db: Session, event_id: int, user_id: int, payload: EventUpdate) -> CalendarEvent:
        event = event_repository.get(db, event_id)
        if not event or event.user_id != user_id:
            raise NotFoundError("Event not found")
        consent_service.require(db, user_id, self.CATEGORY)

        updates = payload.model_dump(exclude_none=True)
        if "title" in updates:
            updates["title"] = encrypt(updates["title"], aad=str(user_id))

        for k, v in updates.items():
            setattr(event, k, v)
        event = event_repository.save(db, event)

        audit_service.record(
            db, user_id=user_id, action="EVENT_UPDATED",
            data_type="calendar", reason=f"Event {event_id} modified",
        )
        return self._decrypt_event(db, event)

    def delete(self, db: Session, event_id: int, user_id: int) -> None:
        event = event_repository.get(db, event_id)
        if not event or event.user_id != user_id:
            raise NotFoundError("Event not found")
        consent_service.require(db, user_id, self.CATEGORY)
        event_repository.delete(db, event)
        audit_service.record(
            db, user_id=user_id, action="EVENT_DELETED",
            data_type="calendar", reason=f"Event {event_id} removed",
        )


scheduling_service = SchedulingService()

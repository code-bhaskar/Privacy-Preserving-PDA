from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.core.security import decrypt, encrypt
from app.models.consent import ConsentCategory
from app.models.reminder import Reminder
from app.repositories.reminder_repository import reminder_repository
from app.schemas.reminder import ReminderCreate, ReminderUpdate
from app.services.audit_service import audit_service
from app.services.consent_service import consent_service


class ReminderService:
    """FR-6: deterministic CRUD only. Encrypted at rest via AES-256-GCM (FR-15)."""
    CATEGORY = ConsentCategory.CALENDAR_DATA

    def _decrypt_reminder(self, db: Session, r: Reminder) -> Reminder:
        if not r:
            return r
        _ = (r.id, r.user_id, r.due_time, r.status, r.created_at)
        db.expunge(r)
        try:
            r.text = decrypt(r.text, aad=str(r.user_id))
        except Exception:
            pass
        return r

    def create(self, db: Session, user_id: int, payload: ReminderCreate) -> Reminder:
        consent_service.require(db, user_id, self.CATEGORY)

        # Encrypt reminder text at rest with AES-256-GCM
        enc_text = encrypt(payload.text, aad=str(user_id))
        r = reminder_repository.save(db, Reminder(
            user_id=user_id,
            text=enc_text,
            due_time=payload.due_time,
        ))

        audit_service.record(
            db, user_id=user_id, action="REMINDER_CREATED",
            data_type="reminder", reason=f"Reminder {r.id} created (encrypted at rest)",
        )
        return self._decrypt_reminder(db, r)

    def list(self, db: Session, user_id: int):
        consent_service.require(db, user_id, self.CATEGORY)
        audit_service.record(
            db, user_id=user_id, action="REMINDERS_READ",
            data_type="reminder", reason="User requested reminder list",
        )
        reminders = reminder_repository.list_by_user(db, user_id)
        return [self._decrypt_reminder(db, r) for r in reminders]

    def update(self, db: Session, reminder_id: int, user_id: int, payload: ReminderUpdate) -> Reminder:
        r = reminder_repository.get(db, reminder_id)
        if not r or r.user_id != user_id:
            raise NotFoundError("Reminder not found")
        consent_service.require(db, user_id, self.CATEGORY)

        updates = payload.model_dump(exclude_none=True)
        if "text" in updates:
            updates["text"] = encrypt(updates["text"], aad=str(user_id))

        for k, v in updates.items():
            setattr(r, k, v)
        r = reminder_repository.save(db, r)

        audit_service.record(
            db, user_id=user_id, action="REMINDER_UPDATED",
            data_type="reminder", reason=f"Reminder {reminder_id} modified",
        )
        return self._decrypt_reminder(db, r)

    def delete(self, db: Session, reminder_id: int, user_id: int) -> None:
        r = reminder_repository.get(db, reminder_id)
        if not r or r.user_id != user_id:
            raise NotFoundError("Reminder not found")
        consent_service.require(db, user_id, self.CATEGORY)
        reminder_repository.delete(db, r)
        audit_service.record(
            db, user_id=user_id, action="REMINDER_DELETED",
            data_type="reminder", reason=f"Reminder {reminder_id} removed",
        )


reminder_service = ReminderService()

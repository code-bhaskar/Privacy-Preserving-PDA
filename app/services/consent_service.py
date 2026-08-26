from sqlalchemy.orm import Session
from app.core.exceptions import ConsentDeniedError
from app.models.consent import ConsentCategory
from app.repositories.consent_repository import consent_repository
from app.services.audit_service import audit_service


class ConsentService:
    def set(self, db: Session, user_id: int, category: ConsentCategory, granted: bool):
        row = consent_repository.upsert(db, user_id, str(category), granted)
        audit_service.record(
            db, user_id=user_id, action="CONSENT_UPDATED", data_type="consent",
            reason=f"User set '{category}' to {granted}",
        )
        return row

    def list(self, db: Session, user_id: int):
        return consent_repository.list_by_user(db, user_id)

    def require(self, db: Session, user_id: int, category: ConsentCategory) -> None:
        """FR-3 gate. Every sensitive service path calls this first."""
        row = consent_repository.get_one(db, user_id, str(category))
        if row is None or not row.granted:
            audit_service.record(
                db, user_id=user_id, action="CONSENT_BLOCKED", data_type=str(category),
                reason=f"Processing blocked — consent for '{category}' not granted",
            )
            raise ConsentDeniedError(str(category))


consent_service = ConsentService()

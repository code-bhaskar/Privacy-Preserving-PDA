from sqlalchemy.orm import Session
from app.repositories.audit_repository import audit_repository


class AuditService:
    def record(self, db: Session, *, user_id: int | None, action: str,
               data_type: str, reason: str, external_processing: bool = False,
               processing_location: str = "local"):
        return audit_repository.create(
            db, user_id=user_id, action=action, data_type=data_type,
            reason=reason, external_processing=external_processing,
            processing_location=processing_location,
        )

    def list(self, db: Session, user_id: int | None = None, limit: int = 200):
        return audit_repository.list(db, user_id, limit)

    def verify(self, db: Session):
        return audit_repository.verify_integrity(db)


audit_service = AuditService()

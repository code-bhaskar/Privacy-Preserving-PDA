from sqlalchemy.orm import Session
from app.services.audit_service import audit_service


class AuditController:
    def list(self, db: Session, user_id: int | None, limit: int):
        return audit_service.list(db, user_id, limit)

    def verify(self, db: Session):
        return audit_service.verify(db)


audit_controller = AuditController()

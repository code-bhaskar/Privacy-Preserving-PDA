from sqlalchemy.orm import Session
from app.models.audit_log import AuditLog


class AuditRepository:
    """Append-only: exposes create + read. No update/delete by design (FR-16)."""

    def create(self, db: Session, **kwargs) -> AuditLog:
        entry = AuditLog(**kwargs)
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry

    def list(self, db: Session, user_id: int | None = None, limit: int = 200):
        q = db.query(AuditLog)
        if user_id is not None:
            q = q.filter(AuditLog.user_id == user_id)
        return q.order_by(AuditLog.id.desc()).limit(limit).all()


audit_repository = AuditRepository()

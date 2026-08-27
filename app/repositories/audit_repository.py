from datetime import datetime
import hashlib
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.base import utcnow


def compute_audit_hash(
    prev_hash: str | None,
    user_id: int | None,
    action: str,
    data_type: str,
    reason: str,
    external_processing: bool,
    processing_location: str,
    created_at: datetime,
) -> str:
    # Normalize timestamp to integer seconds for deterministic hashing across DB engines
    ts = int(created_at.timestamp())
    payload = f"{prev_hash or 'GENESIS'}|{user_id}|{action}|{data_type}|{reason}|{external_processing}|{processing_location}|{ts}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AuditRepository:
    """Append-only: exposes create + read. No update/delete by design (FR-16)."""

    def create(self, db: Session, **kwargs) -> AuditLog:
        last = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
        prev = last.integrity_hash if last and last.integrity_hash else "GENESIS"
        dt = kwargs.pop("created_at", None) or utcnow()

        ih = compute_audit_hash(
            prev_hash=prev,
            user_id=kwargs.get("user_id"),
            action=kwargs.get("action", ""),
            data_type=kwargs.get("data_type", ""),
            reason=kwargs.get("reason", ""),
            external_processing=kwargs.get("external_processing", False),
            processing_location=kwargs.get("processing_location", "local"),
            created_at=dt,
        )

        entry = AuditLog(
            prev_hash=prev,
            integrity_hash=ih,
            created_at=dt,
            **kwargs,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry

    def list(self, db: Session, user_id: int | None = None, limit: int = 200) -> list[AuditLog]:
        q = db.query(AuditLog)
        if user_id is not None:
            q = q.filter(AuditLog.user_id == user_id)
        return q.order_by(AuditLog.id.desc()).limit(limit).all()

    def verify_integrity(self, db: Session) -> dict:
        records = db.query(AuditLog).order_by(AuditLog.id.asc()).all()
        expected_prev = "GENESIS"
        for r in records:
            if r.prev_hash != expected_prev:
                return {
                    "valid": False,
                    "total_records": len(records),
                    "broken_at_id": r.id,
                    "message": f"Broken chain at record {r.id}: expected prev_hash {expected_prev}, got {r.prev_hash}",
                }
            recomputed = compute_audit_hash(
                prev_hash=r.prev_hash,
                user_id=r.user_id,
                action=r.action,
                data_type=r.data_type,
                reason=r.reason,
                external_processing=r.external_processing,
                processing_location=r.processing_location,
                created_at=r.created_at,
            )
            if r.integrity_hash != recomputed:
                return {
                    "valid": False,
                    "total_records": len(records),
                    "broken_at_id": r.id,
                    "message": f"Tampering detected at record {r.id}: hash mismatch",
                }
            expected_prev = r.integrity_hash

        return {
            "valid": True,
            "total_records": len(records),
            "broken_at_id": None,
            "message": "Audit log hash chain verified: 0 tampered records",
        }


audit_repository = AuditRepository()

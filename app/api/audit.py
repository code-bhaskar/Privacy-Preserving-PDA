from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.controllers.audit_controller import audit_controller
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.audit import AuditRead, AuditVerifyResult

router = APIRouter(tags=["audit"])


@router.get("/audit/verify", response_model=AuditVerifyResult)
def verify_audit(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Verify cryptographic hash chain of audit records to detect tampering."""
    return audit_controller.verify(db)


@router.get("/audit", response_model=list[AuditRead])
def list_audit(
    limit: int = Query(200, le=1000),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return audit_controller.list(db, current_user.id, limit)

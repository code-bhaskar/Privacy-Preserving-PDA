from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.controllers.audit_controller import audit_controller
from app.core.database import get_db
from app.schemas.audit import AuditRead

router = APIRouter(tags=["audit"])


@router.get("/audit", response_model=list[AuditRead])
def list_audit(user_id: int | None = Query(None), limit: int = Query(200, le=1000),
               db: Session = Depends(get_db)):
    return audit_controller.list(db, user_id, limit)

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers.privacy_controller import privacy_controller
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.privacy import EncryptDemo, EncryptDemoResult, PrivacyPosture

router = APIRouter(tags=["privacy"])


@router.get("/privacy/posture", response_model=list[PrivacyPosture])
def posture(current_user: User = Depends(get_current_user)):
    """What is actually implemented vs. architecture-only (PRD §9)."""
    return privacy_controller.posture()


@router.post("/privacy/encrypt-demo", response_model=EncryptDemoResult)
def encrypt_demo(
    payload: EncryptDemo,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return privacy_controller.encrypt_demo(db, payload)

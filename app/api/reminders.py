from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers.reminder_controller import reminder_controller
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.reminder import ReminderCreate, ReminderRead, ReminderUpdate

router = APIRouter(tags=["reminders"])


@router.post("/reminders", response_model=ReminderRead, status_code=201)
def create_reminder(
    payload: ReminderCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return reminder_controller.create(db, current_user.id, payload)


@router.get("/reminders", response_model=list[ReminderRead])
def list_reminders(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return reminder_controller.list(db, current_user.id)


@router.put("/reminders/{reminder_id}", response_model=ReminderRead)
def update_reminder(
    reminder_id: int,
    payload: ReminderUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return reminder_controller.update(db, reminder_id, current_user.id, payload)


@router.delete("/reminders/{reminder_id}")
def delete_reminder(
    reminder_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return reminder_controller.delete(db, reminder_id, current_user.id)

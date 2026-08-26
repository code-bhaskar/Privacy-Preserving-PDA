from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.controllers.reminder_controller import reminder_controller
from app.core.database import get_db
from app.schemas.reminder import ReminderCreate, ReminderRead, ReminderUpdate

router = APIRouter(tags=["reminders"])


@router.post("/reminders", response_model=ReminderRead, status_code=201)
def create_reminder(payload: ReminderCreate, db: Session = Depends(get_db)):
    return reminder_controller.create(db, payload)


@router.get("/reminders", response_model=list[ReminderRead])
def list_reminders(user_id: int = Query(...), db: Session = Depends(get_db)):
    return reminder_controller.list(db, user_id)


@router.put("/reminders/{reminder_id}", response_model=ReminderRead)
def update_reminder(reminder_id: int, payload: ReminderUpdate, db: Session = Depends(get_db)):
    return reminder_controller.update(db, reminder_id, payload)


@router.delete("/reminders/{reminder_id}")
def delete_reminder(reminder_id: int, db: Session = Depends(get_db)):
    return reminder_controller.delete(db, reminder_id)

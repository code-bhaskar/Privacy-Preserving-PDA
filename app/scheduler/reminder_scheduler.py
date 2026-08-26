import logging
from apscheduler.schedulers.background import BackgroundScheduler

from app.core.database import SessionLocal
from app.repositories.reminder_repository import reminder_repository
from app.services.audit_service import audit_service
from app.utils.datetime_utils import now_utc

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler(timezone="UTC")


def fire_due_reminders() -> None:
    db = SessionLocal()
    try:
        for r in reminder_repository.due_before(db, now_utc()):
            r.status = "fired"
            reminder_repository.save(db, r)
            audit_service.record(db, user_id=r.user_id, action="REMINDER_FIRED",
                                 data_type="reminder",
                                 reason=f"Reminder {r.id} reached due time")
            logger.info("Reminder fired: %s", r.text)
    finally:
        db.close()


def start_scheduler() -> None:
    if not scheduler.running:
        scheduler.add_job(fire_due_reminders, "interval", seconds=60,
                          id="reminder_sweep", replace_existing=True)
        scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)

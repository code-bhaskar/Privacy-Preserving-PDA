from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.Data_sets.intent.intent_seed import NON_ML_EXECUTION_INTENTS
from app.models.consent import ConsentCategory
from app.ml_models import model_inference
from app.schemas.assistant import CommandRequest, CommandResponse, Explanation
from app.schemas.calendar import EventCreate
from app.schemas.reminder import ReminderCreate
from app.services.audit_service import audit_service
from app.services.consent_service import consent_service
from app.services.reminder_service import reminder_service
from app.services.scheduling_service import scheduling_service
from app.utils.datetime_utils import now_utc


class AssistantService:
    """
    Decision engine (PRD §6.2).
    Intent understanding uses ML; execution of CRUD intents is deterministic.
    """

    def handle(self, db: Session, user_id: int, payload: CommandRequest) -> CommandResponse:
        consent_service.require(db, user_id, ConsentCategory.ASSISTANT_NLU)

        intent, confidence = model_inference.classify(payload.text)
        entities = model_inference.extract(payload.text, intent)
        explanation = Explanation(**model_inference.explain(payload.text))
        requires_ml = intent not in NON_ML_EXECUTION_INTENTS

        audit_service.record(
            db, user_id=user_id, action="INTENT_CLASSIFIED",
            data_type="assistant_command",
            reason=f"Intent={intent} conf={confidence:.2f}; inference performed locally",
            external_processing=False, processing_location="local",
        )

        action, result = self._dispatch(db, user_id, payload, intent, entities)

        return CommandResponse(
            intent=intent, confidence=round(confidence, 4), requires_ml=requires_ml,
            entities=entities, action_taken=action, result=result,
            processing_location="local", explanation=explanation,
        )

    # ---------- deterministic dispatch ----------
    def _dispatch(self, db: Session, user_id: int, payload: CommandRequest,
                  intent: str, ent: dict):
        uid = user_id

        if intent == "SCHEDULE_EVENT":
            start = datetime.fromisoformat(ent["datetime"]) if ent.get("datetime") \
                else now_utc() + timedelta(days=1)
            ev = scheduling_service.create(db, uid, EventCreate(
                title=ent.get("title", "Meeting"),
                participant=ent.get("person"), start_time=start,
                end_time=start + timedelta(hours=1),
            ), via="assistant")
            return "event_created", {
                "id": ev.id, "title": ev.title, "participant": ev.participant,
                "start_time": ev.start_time.isoformat(),
            }

        if intent == "CREATE_REMINDER":
            due = datetime.fromisoformat(ent["datetime"]) if ent.get("datetime") \
                else now_utc() + timedelta(hours=1)
            r = reminder_service.create(db, uid, ReminderCreate(
                text=ent.get("task", payload.text), due_time=due,
            ))
            return "reminder_created", {
                "id": r.id, "text": r.text, "due_time": r.due_time.isoformat(),
            }

        if intent == "GET_EVENTS":
            evs = scheduling_service.list(db, uid)
            return "events_listed", [
                {"id": e.id, "title": e.title, "start_time": e.start_time.isoformat()}
                for e in evs
            ]

        if intent == "GET_REMINDERS":
            rs = reminder_service.list(db, uid)
            return "reminders_listed", [
                {"id": r.id, "text": r.text, "due_time": r.due_time.isoformat(),
                 "status": r.status} for r in rs
            ]

        if intent in ("DELETE_EVENT", "DELETE_REMINDER"):
            return "confirmation_required", {
                "message": "Specify the item id to delete via "
                           "DELETE /events/{id} or DELETE /reminders/{id}."
            }

        if intent == "SUMMARIZE_MESSAGES":
            return "summarization_ready", {
                "message": "Send messages to POST /messages/summarize "
                           "— they are processed locally and never sent externally."
            }

        if intent == "GREETING":
            return "greeting", {"message": "Hello. How can I help?"}

        return "unhandled", None


assistant_service = AssistantService()

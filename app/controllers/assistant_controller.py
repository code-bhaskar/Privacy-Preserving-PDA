from sqlalchemy.orm import Session
from app.schemas.assistant import CommandRequest, SummarizeRequest
from app.services.assistant_service import assistant_service
from app.services.summarization_service import summarization_service


class AssistantController:
    def command(self, db: Session, user_id: int, payload: CommandRequest):
        return assistant_service.handle(db, user_id, payload)

    def summarize(self, db: Session, user_id: int, payload: SummarizeRequest):
        return summarization_service.summarize(db, user_id, payload)


assistant_controller = AssistantController()

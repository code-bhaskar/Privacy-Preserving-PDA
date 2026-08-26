from sqlalchemy.orm import Session
from app.schemas.assistant import CommandRequest, SummarizeRequest
from app.services.assistant_service import assistant_service
from app.services.summarization_service import summarization_service


class AssistantController:
    def command(self, db: Session, payload: CommandRequest):
        return assistant_service.handle(db, payload)

    def summarize(self, db: Session, payload: SummarizeRequest):
        return summarization_service.summarize(db, payload)


assistant_controller = AssistantController()

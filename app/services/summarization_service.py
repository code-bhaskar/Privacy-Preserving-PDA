from sqlalchemy.orm import Session

from app.core.security import encrypt
from app.models.consent import ConsentCategory
from app.models.message import Message
from app.ml_models import model_inference
from app.repositories.message_repository import message_repository
from app.schemas.assistant import SummarizeRequest, SummarizeResponse
from app.services.audit_service import audit_service
from app.services.consent_service import consent_service


class SummarizationService:
    CATEGORY = ConsentCategory.MESSAGE_SUMMARIZATION

    def summarize(self, db: Session, user_id: int, payload: SummarizeRequest) -> SummarizeResponse:
        consent_service.require(db, user_id, self.CATEGORY)

        texts = [m.content for m in payload.messages]
        summary = model_inference.summarize(texts, payload.max_sentences)  # local only

        if payload.persist:
            for m in payload.messages:
                message_repository.save(db, Message(
                    user_id=user_id,
                    sender=m.sender,
                    content_encrypted=encrypt(m.content, aad=str(user_id)),
                ))

        audit_service.record(
            db, user_id=user_id, action="MESSAGES_SUMMARIZED",
            data_type="private_messages",
            reason=f"Summarized {len(texts)} messages with local extractive model; "
                   f"raw content encrypted at rest (AES-256-GCM)",
            external_processing=False, processing_location="local",
        )
        return SummarizeResponse(
            summary=summary, n_messages=len(texts),
            processing_location="local", raw_content_transmitted_externally=False,
        )


summarization_service = SummarizationService()

from enum import StrEnum
from sqlalchemy import String, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin


class ConsentCategory(StrEnum):
    ASSISTANT_NLU = "assistant_nlu"
    CALENDAR_DATA = "calendar_data"
    MESSAGE_SUMMARIZATION = "message_summarization"
    FEDERATED_TRAINING = "federated_training"


class Consent(Base, TimestampMixin):
    __tablename__ = "consents"
    __table_args__ = (UniqueConstraint("user_id", "category", name="uq_user_category"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(64))
    granted: Mapped[bool] = mapped_column(Boolean, default=False)

    user = relationship("User", back_populates="consents")

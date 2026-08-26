from datetime import datetime
from sqlalchemy import Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin, utcnow


class Message(Base, TimestampMixin):
    """content is stored AES-GCM encrypted at rest (FR-15)."""
    __tablename__ = "messages"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    content_encrypted: Mapped[str] = mapped_column(Text)
    sender: Mapped[str] = mapped_column(Text, default="unknown")
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

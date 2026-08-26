from sqlalchemy import String, Boolean, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class AuditLog(Base, TimestampMixin):
    """Append-only. Never updated or deleted (FR-16)."""
    __tablename__ = "audit_logs"

    user_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    data_type: Mapped[str] = mapped_column(String(60))
    reason: Mapped[str] = mapped_column(Text)
    external_processing: Mapped[bool] = mapped_column(Boolean, default=False)
    processing_location: Mapped[str] = mapped_column(String(20), default="local")

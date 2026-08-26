from sqlalchemy import String, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)

    consents = relationship("Consent", back_populates="user", cascade="all, delete-orphan")

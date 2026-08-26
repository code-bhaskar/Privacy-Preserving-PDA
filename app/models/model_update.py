from sqlalchemy import String, Integer, Float, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class ModelUpdate(Base, TimestampMixin):
    """Metadata only — no raw client data, no unmasked client vectors."""
    __tablename__ = "model_updates"

    round_id: Mapped[int] = mapped_column(Integer, index=True)
    client_id: Mapped[str] = mapped_column(String(40))
    dp_epsilon: Mapped[float | None] = mapped_column(Float, nullable=True)
    dp_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    clip_norm: Mapped[float] = mapped_column(Float, default=1.0)
    payload_bytes: Mapped[int] = mapped_column(Integer, default=0)
    masked: Mapped[bool] = mapped_column(Boolean, default=True)
    n_local_samples: Mapped[int] = mapped_column(Integer, default=0)


class FederatedRound(Base, TimestampMixin):
    __tablename__ = "federated_rounds"

    round_id: Mapped[int] = mapped_column(Integer, index=True)
    n_clients: Mapped[int] = mapped_column(Integer)
    dp_epsilon: Mapped[float | None] = mapped_column(Float, nullable=True)
    global_accuracy: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    comm_bytes_total: Mapped[int] = mapped_column(Integer, default=0)
    model_size_bytes: Mapped[int] = mapped_column(Integer, default=0)

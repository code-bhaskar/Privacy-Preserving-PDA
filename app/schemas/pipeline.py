"""Request schemas for the single-pipeline federated learning controls.

These drive ``fl/pipeline/supervisor.py`` so the Angular frontend can run the
whole FL demo (dataset -> clients -> rounds -> epsilon sweep -> ONNX) through the
same FastAPI app that serves the rest of the product.
"""
from pydantic import BaseModel, Field


class DatasetPrepareRequest(BaseModel):
    clients: int = Field(6, ge=2, le=8)
    alpha: float = Field(0.5, gt=0.0, le=10.0, description="lower = more non-IID")


class ClientsSpawnRequest(BaseModel):
    count: int = Field(3, ge=1, le=8)
    start_id: int = Field(0, ge=0, le=32)
    drop_at: str | None = Field(
        None, pattern="^COLLECT$",
        description="Set to 'COLLECT' on one spawn to demo Shamir dropout recovery.",
    )
    rounds: int = Field(1000, ge=1, le=100000)


class ClientsStopRequest(BaseModel):
    client_ids: list[int] | None = None


class SweepRequest(BaseModel):
    """Accuracy-vs-epsilon sweep, run in-process with live progress."""
    epsilons: list[float | None] = Field(
        default_factory=lambda: [None, 10.0, 5.0, 1.0],
        description="null entry means no differential privacy (ε=∞).",
    )
    rounds: int = Field(3, ge=1, le=50)
    clients_per_round: int = Field(3, ge=2, le=8)
    local_epochs: int = Field(1, ge=1, le=10)
    clip_norm: float = Field(20.0, gt=0.0)
    lr: float = Field(0.5, gt=0.0, le=5.0)


class OnnxExportRequest(BaseModel):
    benchmark: bool = True

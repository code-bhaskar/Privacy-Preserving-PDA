from typing import Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from fl.server.coordinator import coordinator

router = APIRouter(prefix="/api/v1/fl", tags=["Federated Learning (real)"])


class RegisterReq(BaseModel):
    client_id: int
    num_samples: int


class StartRoundReq(BaseModel):
    clients_per_round: int = 5
    local_epochs: int = 2
    lr: float = 0.5
    clip_norm: float = 1.0
    target_epsilon: Optional[float] = None
    total_rounds_planned: int = 20
    delta: float = 1e-5


class PubKeyReq(BaseModel):
    client_id: int
    c_pk: str
    s_pk: str


class SharesReq(BaseModel):
    client_id: int
    shares: Dict[str, str]


class MaskedReq(BaseModel):
    client_id: int
    vector_hex: str
    num_samples: int


class RevealReq(BaseModel):
    client_id: int
    b_shares: dict = Field(default_factory=dict)
    s_shares: dict = Field(default_factory=dict)


def _guard(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except RuntimeError as e:
        raise HTTPException(409, str(e))


@router.post("/register")
def register(r: RegisterReq):
    return coordinator.register(r.client_id, r.num_samples)


@router.post("/round/start")
def start_round(r: StartRoundReq):
    return _guard(coordinator.start_round, r.clients_per_round, r.local_epochs,
                  r.lr, r.clip_norm, r.target_epsilon,
                  r.total_rounds_planned, r.delta)


@router.get("/round/status")
def status():
    return coordinator.status()


@router.get("/model/weights")
def weights():
    return {"weights_hex": coordinator.global_weights_hex(),
            "dim": coordinator.dim, "round_id": coordinator.round_id}


@router.post("/keys/advertise")
def advertise(r: PubKeyReq):
    _guard(coordinator.submit_pubkeys, r.client_id, r.c_pk, r.s_pk)
    return {"ok": True}


@router.post("/keys/share")
def share(r: SharesReq):
    _guard(coordinator.submit_shares, r.client_id, r.shares)
    return {"ok": True}


@router.get("/keys/inbox/{client_id}")
def inbox(client_id: int):
    return {"shares": coordinator.inbox_for(client_id)}


@router.post("/update/masked")
def masked(r: MaskedReq):
    _guard(coordinator.submit_masked, r.client_id, r.vector_hex, r.num_samples)
    return {"ok": True}


@router.post("/update/reveal")
def reveal(r: RevealReq):
    _guard(coordinator.submit_reveal, r.client_id, r.b_shares, r.s_shares)
    return {"ok": True}


@router.post("/round/close-collection")
def close_collection():
    """Trigger dropout recovery path manually (or from a timeout job)."""
    return {"closed": coordinator.force_close_collection(),
            "dropped": coordinator.dropped}


@router.post("/experiment/reset")
def reset(drop_registrations: bool = False):
    """Reset model + privacy ledger. Pass drop_registrations=true to also
    forget clients from a previous topology."""
    return coordinator.reset_experiment(drop_registrations)


@router.get("/history")
def history():
    return {"rounds": coordinator.history,
            "cumulative_privacy": coordinator.accountant.spent()
            if coordinator.accountant else None}

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers.federated_controller import federated_controller
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.federated import (
    RoundRequest, RoundResult, ExperimentRequest, ExperimentResult,
)

router = APIRouter(tags=["federated"])


@router.post("/federated/round", response_model=list[RoundResult])
def run_round(
    payload: RoundRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return federated_controller.run_round(db, payload, current_user.id)


@router.post("/federated/experiment", response_model=ExperimentResult)
def experiment(
    payload: ExperimentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """FR-18: accuracy vs privacy budget (ε)."""
    return federated_controller.experiment(db, payload)


@router.get("/federated/results")
def results(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return federated_controller.history(db)

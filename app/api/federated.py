from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.controllers.federated_controller import federated_controller
from app.controllers.pipeline_controller import pipeline_controller
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.federated import (
    RoundRequest, RoundResult, ExperimentRequest, ExperimentResult,
)
from app.schemas.pipeline import (
    ClientsSpawnRequest, ClientsStopRequest, DatasetPrepareRequest,
    OnnxExportRequest, SweepRequest,
)

router = APIRouter(tags=["federated"])

# Single-pipeline controls: dataset -> clients -> rounds -> sweep -> ONNX export.
# Everything below runs inside the SAME FastAPI process that serves /api/v1/*,
# so the demo needs one backend, not a separate coordinator server.
pipeline = APIRouter(prefix="/federated/pipeline", tags=["federated pipeline (single)"])


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


# --------------------------------------------------------------------------- #
# single-pipeline FL controls
# --------------------------------------------------------------------------- #

@pipeline.get("/status")
def pipeline_status(current_user: User = Depends(get_current_user)):
    """One call with everything the FL dashboard renders.

    Dataset readiness, supervised client processes, coordinator phase machine,
    registered clients, privacy budget spent, round history and sweep progress.
    """
    return pipeline_controller.status()


@pipeline.get("/dataset/status")
def dataset_status(current_user: User = Depends(get_current_user)):
    return pipeline_controller.dataset_status()


@pipeline.post("/dataset/prepare")
def dataset_prepare(
    payload: DatasetPrepareRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Download SNIPS + non-IID Dirichlet partition, in the background.

    Replaces the standalone ``python -m fl.data.prepare`` step.
    """
    return pipeline_controller.prepare_dataset(db, payload)


@pipeline.get("/clients")
def list_clients(current_user: User = Depends(get_current_user)):
    return pipeline_controller.clients()


@pipeline.post("/clients/spawn")
def spawn_clients(
    payload: ClientsSpawnRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Spawn independent FL client OS processes attached to this coordinator.

    The clients stay separate processes on purpose: their private shards never
    enter the API process, and the server only ever receives masked uint32
    vectors. Replaces ``for i in {0..5}; do python -m fl.client.run ... & done``.
    """
    return pipeline_controller.spawn_clients(db, payload)


@pipeline.post("/clients/stop")
def stop_clients(
    payload: ClientsStopRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return pipeline_controller.stop_clients(db, payload)


@pipeline.get("/clients/{client_id}/log")
def client_log(
    client_id: int,
    lines: int = Query(40, ge=1, le=500),
    current_user: User = Depends(get_current_user),
):
    return pipeline_controller.client_log(client_id, lines)


@pipeline.get("/sweep/status")
def sweep_status(current_user: User = Depends(get_current_user)):
    return pipeline_controller.sweep_status()


@pipeline.post("/sweep/start")
def sweep_start(
    payload: SweepRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Accuracy-vs-epsilon sweep with live progress.

    Replaces ``python -m fl.experiments.run_sweep``: same protocol, same Rényi DP
    accounting, same ``fl_results.json`` artifact — but pollable from the UI.
    """
    return pipeline_controller.start_sweep(db, payload)


@pipeline.post("/onnx/export")
def onnx_export(
    payload: OnnxExportRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Export the aggregated global model to ``deployed_models/intent_model.onnx``."""
    return pipeline_controller.export_onnx(db, payload)


router.include_router(pipeline)

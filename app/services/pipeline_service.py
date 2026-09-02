"""Service layer for the single-pipeline FL controls.

Thin wrapper over ``fl.pipeline.supervisor`` that keeps the controller free of
process/OS details and records an audit entry for pipeline operations that change
system state (spawning clients, running a sweep, exporting the model).
"""
import json
import os
import subprocess
import sys

from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.services.audit_service import audit_service
from fl.pipeline.supervisor import (
    REPO_ROOT,
    dataset_job,
    dataset_status,
    pipeline_status,
    supervisor,
    sweep_runner,
)

_LOG_ROOT = os.path.join(REPO_ROOT, "logs")


class PipelineService:
    # ---------------- dataset ---------------- #

    def dataset_status(self) -> dict:
        return dataset_job.status()

    def prepare_dataset(self, db: Session, clients: int, alpha: float) -> dict:
        result = dataset_job.start(clients, alpha)
        if result.get("started"):
            audit_service.record(
                db,
                user_id=None,
                action="FL_DATASET_PREPARE_STARTED",
                data_type="model_metrics",
                reason=f"SNIPS partition requested: {clients} clients, Dirichlet alpha={alpha}",
            )
        return result

    # ---------------- clients ---------------- #

    def clients(self) -> list[dict]:
        return supervisor.list()

    def spawn_clients(self, db: Session, count: int, start_id: int,
                      drop_at: str | None, rounds: int) -> dict:
        if not dataset_status()["ready"]:
            raise ValidationError(
                "fl_data is not prepared. Prepare the dataset first "
                "(POST /api/v1/federated/pipeline/dataset/prepare)."
            )
        result = supervisor.spawn(count=count, start_id=start_id,
                                  drop_at=drop_at, rounds=rounds)
        if result.get("spawned"):
            ids = [c["client_id"] for c in result["spawned"]]
            audit_service.record(
                db,
                user_id=None,
                action="FL_CLIENTS_SPAWNED",
                data_type="model_update",
                reason=(
                    f"{len(ids)} independent client process(es) {ids} attached to the "
                    f"in-process coordinator; private shards stay on the client side"
                    + (f"; dropout simulated at {drop_at}" if drop_at else "")
                ),
            )
        return result

    def stop_clients(self, db: Session, client_ids: list[int] | None) -> dict:
        result = supervisor.stop(client_ids)
        if result.get("stopped"):
            audit_service.record(
                db,
                user_id=None,
                action="FL_CLIENTS_STOPPED",
                data_type="model_update",
                reason=f"stopped client process(es) {result['stopped']}",
            )
        return result

    def client_log(self, client_id: int, lines: int) -> dict:
        return supervisor.log_tail(client_id, lines)

    # ---------------- sweep ---------------- #

    def sweep_status(self) -> dict:
        return sweep_runner.status()

    def start_sweep(self, db: Session, req) -> dict:
        result = sweep_runner.start(
            epsilons=req.epsilons,
            rounds=req.rounds,
            clients_per_round=req.clients_per_round,
            local_epochs=req.local_epochs,
            clip_norm=req.clip_norm,
            lr=req.lr,
            delta=_delta(),
        )
        if result.get("started"):
            labels = ", ".join("∞" if e is None else f"{e:g}" for e in req.epsilons)
            audit_service.record(
                db,
                user_id=None,
                action="FL_SWEEP_STARTED",
                data_type="model_metrics",
                reason=(
                    f"epsilon sweep [{labels}] x {req.rounds} rounds, "
                    f"{req.clients_per_round} clients/round, secure aggregation on"
                ),
            )
        return result

    # ---------------- model export ---------------- #

    def export_onnx(self, db: Session, benchmark: bool) -> dict:
        """Export the aggregated global model to its own ONNX artifact.

        Written to ``deployed_models/intent_model_federated.onnx`` — NOT to the
        artifact the assistant serves. The federated model is trained on SNIPS
        (7 intents) while ``POST /assistant/command`` labels against the 8
        assistant intents; swapping them would make the assistant confidently
        return the wrong intent names. ``fl.deploy.export_onnx --target live``
        exists for the day FL runs on the assistant's own label space, and it
        refuses unless the class counts match.
        """
        if not coordinator_has_model():
            raise ValidationError(
                "No aggregated global model yet — run at least one federated round first."
            )
        os.makedirs(_LOG_ROOT, exist_ok=True)
        export_log = os.path.join(_LOG_ROOT, "onnx_export.log")
        out: dict = {"steps": [], "target": "federated",
                     "live_assistant_model_modified": False,
                     "artifact": "deployed_models/intent_model_federated.onnx"}
        modules = ["fl.deploy.export_onnx"] + (["fl.deploy.benchmark"] if benchmark else [])
        for mod in modules:
            try:
                proc = subprocess.run(
                    [sys.executable, "-m", mod], cwd=REPO_ROOT,
                    capture_output=True, text=True, timeout=900,
                )
                out["steps"].append({
                    "module": mod,
                    "exit_code": proc.returncode,
                    "stdout": (proc.stdout or "")[-4000:],
                    "stderr": (proc.stderr or "")[-2000:],
                })
            except Exception as exc:
                out["steps"].append({"module": mod, "exit_code": -1,
                                     "stdout": "", "stderr": f"{type(exc).__name__}: {exc}"})
        with open(export_log, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2)
        out["ok"] = all(s["exit_code"] == 0 for s in out["steps"])
        out["log_path"] = os.path.relpath(export_log, REPO_ROOT)
        out["sizes"] = _read_json_card("deployed_models", "model_card_federated.json")
        # `fl.deploy.benchmark` times the SERVED assistant model, not the
        # federated artifact just written - label it so nobody reads these
        # latency numbers as belonging to the export.
        out["benchmark"] = _read_json_card("deployed_models", "benchmark.json") if benchmark else None
        out["benchmark_target"] = "deployed_models/intent_model.onnx" if benchmark else None
        out["note"] = (
            "Exported the federated (SNIPS, "
            f"{coordinator_num_classes()}-class) global model to "
            "deployed_models/intent_model_federated.onnx. The model served by "
            "/assistant/command was NOT modified - it uses a different label "
            "space. Latency figures below are for that served model."
        )
        if out["ok"]:
            audit_service.record(
                db,
                user_id=None,
                action="FL_MODEL_EXPORTED",
                data_type="model_update",
                reason=(
                    "Federated global model exported to "
                    "deployed_models/intent_model_federated.onnx; the served assistant "
                    "model was left untouched (different label space)"
                ),
            )
        return out

    # ---------------- aggregate ---------------- #

    def status(self) -> dict:
        return pipeline_status()


def _delta() -> float:
    from app.core.config import settings
    return settings.FL_DP_DELTA


def coordinator_has_model() -> bool:
    from fl.server.coordinator import coordinator
    return coordinator.round_id > 0 and bool(coordinator.history)


def coordinator_num_classes() -> int:
    """Class count of the federated global model (SNIPS = 7)."""
    from fl.server.coordinator import coordinator
    return int(getattr(coordinator, "num_classes", 0) or 0)


def _read_json_card(*rel_parts: str) -> dict | None:
    """Best-effort read of a JSON artifact written by an `fl.deploy.*` module."""
    try:
        with open(os.path.join(REPO_ROOT, *rel_parts), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


pipeline_service = PipelineService()

import numpy as np
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.consent import ConsentCategory
from app.ml_models.federated_core import federated_simulator
from app.repositories.federated_repository import federated_repository
from app.schemas.federated import (
    RoundRequest, RoundResult, ClientContribution,
    ExperimentRequest, ExperimentResult, ExperimentPoint,
)
from app.services.audit_service import audit_service
from app.services.consent_service import consent_service


class FederatedService:
    def __init__(self):
        self._global_weights: np.ndarray | None = None

    def _weights(self) -> np.ndarray:
        if self._global_weights is None:
            self._global_weights = federated_simulator.initial_weights()
        return self._global_weights

    def run(self, db: Session, req: RoundRequest,
            user_id: int | None = None) -> list[RoundResult]:
        if user_id is not None:
            consent_service.require(db, user_id, ConsentCategory.FEDERATED_TRAINING)

        if req.n_clients:
            federated_simulator._partition(req.n_clients)

        results: list[RoundResult] = []
        w = self._weights()

        for _ in range(req.rounds):
            rid = federated_repository.next_round_id(db)
            out = federated_simulator.run_round(rid, w, req.epsilon, req.secure_aggregation)
            w = out["weights"]
            acc = federated_simulator.evaluate(w)

            federated_repository.save_round(
                db, round_id=rid, n_clients=len(out["contributions"]),
                dp_epsilon=req.epsilon, global_accuracy=acc,
                latency_ms=out["latency_ms"], comm_bytes_total=out["comm_bytes_total"],
                model_size_bytes=out["model_size_bytes"],
            )
            for c in out["contributions"]:
                federated_repository.save_update(
                    db, round_id=rid, client_id=c["client_id"],
                    dp_epsilon=c["dp_epsilon"], dp_delta=settings.FL_DP_DELTA,
                    clip_norm=settings.FL_CLIP_NORM, payload_bytes=c["payload_bytes"],
                    masked=c["masked"], n_local_samples=c["n_local_samples"],
                )

            audit_service.record(
                db, user_id=user_id, action="FEDERATED_ROUND_COMPLETED",
                data_type="model_update",
                reason=(f"Round {rid}: {len(out['contributions'])} clients, "
                        f"eps={req.epsilon}, secure_agg={req.secure_aggregation}. "
                        f"Coordinator received masked DP updates only — no raw data."),
                external_processing=False, processing_location="local-coordinator",
            )

            results.append(RoundResult(
                round_id=rid, n_clients=len(out["contributions"]),
                dp_epsilon=req.epsilon, global_accuracy=round(acc, 4),
                latency_ms=round(out["latency_ms"], 2),
                comm_bytes_total=out["comm_bytes_total"],
                model_size_bytes=out["model_size_bytes"],
                contributions=[ClientContribution(**c) for c in out["contributions"]],
            ))

        self._global_weights = w
        return results

    # ---------- FR-18: accuracy vs epsilon ----------
    def experiment(self, db: Session, req: ExperimentRequest) -> ExperimentResult:
        federated_simulator._partition(req.n_clients)
        baseline = federated_simulator.centralized_baseline()
        points: list[ExperimentPoint] = []

        for eps in req.epsilons:
            w = federated_simulator.initial_weights()
            lats, comm = [], 0
            for r in range(1, req.rounds + 1):
                out = federated_simulator.run_round(r, w, eps, secure_agg=True)
                w = out["weights"]
                lats.append(out["latency_ms"])
                comm = out["comm_bytes_total"] // len(out["contributions"])
            acc = federated_simulator.evaluate(w)
            points.append(ExperimentPoint(
                epsilon=eps,
                epsilon_label="no DP (ε=∞)" if eps is None else f"ε={eps:g}",
                accuracy=round(acc, 4),
                avg_round_latency_ms=round(sum(lats) / len(lats), 2),
                comm_bytes_per_client=comm,
                model_size_bytes=int(w.nbytes),
            ))

        audit_service.record(
            db, user_id=None, action="DP_EXPERIMENT_RUN", data_type="model_metrics",
            reason=f"Accuracy-vs-epsilon sweep over {req.epsilons}, {req.rounds} rounds",
        )
        return ExperimentResult(
            baseline_centralized_accuracy=round(baseline, 4), points=points
        )

    def history(self, db: Session):
        return federated_repository.list_rounds(db)


federated_service = FederatedService()

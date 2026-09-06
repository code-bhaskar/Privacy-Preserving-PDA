import time
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ValidationError
from app.models.consent import ConsentCategory
from app.repositories.federated_repository import federated_repository
from app.schemas.federated import (
    ClientContribution,
    ExperimentPoint,
    ExperimentRequest,
    ExperimentResult,
    RoundRequest,
    RoundResult,
)
from app.services.audit_service import audit_service
from app.services.consent_service import consent_service
from fl.server.coordinator import Phase, coordinator


class FederatedService:
    def run(
        self,
        db: Session,
        req: RoundRequest,
        user_id: int | None = None,
    ) -> list[RoundResult]:
        if user_id is not None:
            consent_service.require(db, user_id, ConsentCategory.FEDERATED_TRAINING)
        if not req.secure_aggregation:
            raise ValidationError(
                "Secure aggregation is required for federated rounds; plaintext updates are not accepted."
            )
        # The UI exposes both a one-off round and a background sweep, but they
        # share one coordinator state machine. Refuse overlap instead of
        # resetting a round that another operation is waiting on.
        from fl.pipeline.supervisor import supervisor, sweep_runner
        supervisor.reap_dead()
        if sweep_runner.status().get("running"):
            raise ValidationError("An epsilon sweep is already running; wait for it to finish before starting a round.")

        registered_count = len(coordinator.registered)
        target_clients = req.n_clients or registered_count

        if registered_count == 0 or target_clients < 2 or registered_count < target_clients:
            raise ValidationError(
                f"No federated learning clients connected (have {registered_count}, need {target_clients}). "
                f"Start client processes with 'python -m fl.client.run --client-id <id>' before running a round."
            )

        results: list[RoundResult] = []

        for _ in range(req.rounds):
            try:
                coordinator.start_round(
                    clients_per_round=target_clients,
                    local_epochs=settings.FL_LOCAL_EPOCHS,
                    lr=0.5,
                    clip_norm=settings.FL_CLIP_NORM,
                    target_epsilon=req.epsilon,
                    total_rounds_planned=req.rounds,
                    delta=settings.FL_DP_DELTA,
                )
            except RuntimeError as exc:
                raise ValidationError(str(exc)) from exc

            # Wait for round completion. If collection times out but the
            # threshold of masked updates is present, close COLLECT and let the
            # real protocol recover the missing client's pairwise masks. Without
            # this transition the UI's dropout demo would sit in COLLECT until
            # the request failed, even though the secure-aggregation state
            # machine already has a recovery path.
            try:
                last_rec = self._wait_for_round()
            except RuntimeError as exc:
                raise ValidationError(str(exc)) from exc

            if not last_rec:
                raise ValidationError("Round failed to generate history record")

            # `last_rec` is the record for the round just completed. Do not use
            # a stale history entry if a future coordinator implementation ever
            # allows concurrent jobs.
            rid = federated_repository.next_round_id(db)

            n_survivors = len(last_rec.get("survivors", []))
            comm_bytes = last_rec.get("total_uplink_bytes", 0)
            model_size = coordinator.dim * 4
            latency_ms = round(last_rec.get("round_wall_time_s", 0) * 1000.0, 2)
            acc = last_rec.get("test_accuracy", 0.0)

            federated_repository.save_round(
                db,
                round_id=rid,
                n_clients=n_survivors,
                dp_epsilon=req.epsilon,
                global_accuracy=acc,
                latency_ms=latency_ms,
                comm_bytes_total=comm_bytes,
                model_size_bytes=model_size,
            )

            contributions: list[ClientContribution] = []
            for cid in last_rec.get("participants", []):
                survived = cid in last_rec.get("survivors", [])
                n_samples = coordinator.sample_counts.get(cid, 0)
                payload_bytes = coordinator.dim * 4 if survived else 0
                federated_repository.save_update(
                    db,
                    round_id=rid,
                    client_id=str(cid),
                    dp_epsilon=req.epsilon,
                    dp_delta=settings.FL_DP_DELTA,
                    clip_norm=settings.FL_CLIP_NORM,
                    payload_bytes=payload_bytes,
                    masked=True,
                    n_local_samples=n_samples,
                )
                contributions.append(
                    ClientContribution(
                        client_id=str(cid),
                        n_local_samples=n_samples,
                        payload_bytes=payload_bytes,
                        dp_epsilon=req.epsilon,
                        masked=True,
                        raw_data_transmitted=False,
                    )
                )

            audit_service.record(
                db,
                user_id=user_id,
                action="FEDERATED_ROUND_COMPLETED",
                data_type="model_update",
                reason=(
                    f"Round {rid}: {n_survivors} clients, eps={req.epsilon}, "
                    f"Bonawitz secure aggregation. Coordinator handled masked uint32 vectors only."
                ),
                external_processing=False,
                processing_location="local-coordinator",
            )

            results.append(
                RoundResult(
                    round_id=rid,
                    n_clients=n_survivors,
                    dp_epsilon=req.epsilon,
                    global_accuracy=round(acc, 4),
                    latency_ms=latency_ms,
                    comm_bytes_total=comm_bytes,
                    model_size_bytes=model_size,
                    contributions=contributions,
                )
            )

        return results

    @staticmethod
    def _wait_for_round() -> dict:
        """Wait for DONE and perform threshold-based collection recovery.

        A client that disappears in ``COLLECT`` cannot call the close endpoint
        itself. The authenticated product endpoint therefore owns the timeout:
        it closes collection once, only when the coordinator has enough masked
        vectors to recover, and then waits for survivor reveals.
        """
        timeout = max(1.0, float(settings.FL_ROUND_TIMEOUT_SECONDS))
        deadline = time.time() + timeout
        recovery_requested = False
        while True:
            with coordinator.lock:
                phase = coordinator.phase
                history = list(coordinator.history)
                collected = len(coordinator.masked)
                participants = len(coordinator.participants)

            if phase == Phase.DONE and history:
                return history[-1]
            if phase == Phase.IDLE:
                raise RuntimeError("Federated learning coordinator became idle before the round completed")

            if time.time() >= deadline:
                if (
                    not recovery_requested
                    and phase == Phase.COLLECT
                    and coordinator.force_close_collection()
                ):
                    recovery_requested = True
                    # Give survivors a fresh full timeout to reveal shares and
                    # complete the aggregate after collection was closed.
                    deadline = time.time() + timeout
                    continue
                raise RuntimeError(
                    f"Federated learning round timed out after {timeout:.0f}s waiting for "
                    f"client contributions (phase={phase.value}, collected "
                    f"{collected}/{participants} masked vectors). Are the client "
                    "processes still running?"
                )
            time.sleep(0.1)

    def experiment(self, db: Session, req: ExperimentRequest) -> ExperimentResult:
        registered_count = len(coordinator.registered)
        target_clients = req.n_clients or registered_count

        if registered_count == 0 or target_clients < 2 or registered_count < target_clients:
            raise ValidationError(
                f"No federated learning clients connected (have {registered_count}, need {target_clients}). "
                f"Start client processes before running an experiment."
            )

        points: list[ExperimentPoint] = []
        for eps in req.epsilons:
            coordinator.reset_experiment(drop_registrations=False)
            round_req = RoundRequest(
                n_clients=target_clients,
                rounds=req.rounds,
                epsilon=eps,
                secure_aggregation=True,
            )
            r_results = self.run(db, round_req)
            last_round = r_results[-1]
            avg_lat = sum(r.latency_ms for r in r_results) / len(r_results)
            comm_per_client = last_round.comm_bytes_total // max(1, last_round.n_clients)
            points.append(
                ExperimentPoint(
                    epsilon=eps,
                    epsilon_label="no DP (ε=∞)" if eps is None else f"ε={eps:g}",
                    accuracy=last_round.global_accuracy,
                    avg_round_latency_ms=round(avg_lat, 2),
                    comm_bytes_per_client=comm_per_client,
                    model_size_bytes=last_round.model_size_bytes,
                )
            )

        audit_service.record(
            db,
            user_id=None,
            action="DP_EXPERIMENT_RUN",
            data_type="model_metrics",
            reason=f"Accuracy-vs-epsilon sweep over {req.epsilons}, {req.rounds} rounds",
        )
        # Note: Centralized baseline intentionally omitted (0.0) — pooling raw client
        # data on the server violates the privacy-preserving design.
        return ExperimentResult(
            baseline_centralized_accuracy=0.0,
            points=points,
        )

    def history(self, db: Session):
        return federated_repository.list_rounds(db)


federated_service = FederatedService()

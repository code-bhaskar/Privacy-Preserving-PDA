"""Offline runner: python -m app.jobs.federated_job"""
from app.core.database import SessionLocal, init_db
from app.schemas.federated import ExperimentRequest
from app.services.federated_service import federated_service


def main():
    init_db()
    db = SessionLocal()
    try:
        res = federated_service.experiment(
            db, ExperimentRequest(epsilons=[None, 10.0, 5.0, 1.0], rounds=5, n_clients=5)
        )
        print(f"\nCentralized baseline: {res.baseline_centralized_accuracy:.4f}\n")
        print(f"{'Privacy budget':<16}{'Accuracy':>10}{'Latency(ms)':>14}{'Bytes/client':>14}")
        print("-" * 54)
        for p in res.points:
            print(f"{p.epsilon_label:<16}{p.accuracy:>10.4f}"
                  f"{p.avg_round_latency_ms:>14.2f}{p.comm_bytes_per_client:>14}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

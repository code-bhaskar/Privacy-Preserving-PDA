from sqlalchemy.orm import Session
from app.schemas.federated import RoundRequest, ExperimentRequest
from app.services.federated_service import federated_service


class FederatedController:
    def run_round(self, db: Session, payload: RoundRequest, user_id: int | None):
        return federated_service.run(db, payload, user_id)

    def experiment(self, db: Session, payload: ExperimentRequest):
        return federated_service.experiment(db, payload)

    def history(self, db: Session):
        return federated_service.history(db)


federated_controller = FederatedController()

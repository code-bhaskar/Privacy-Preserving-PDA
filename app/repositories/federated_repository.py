from sqlalchemy.orm import Session
from app.models.model_update import ModelUpdate, FederatedRound


class FederatedRepository:
    def next_round_id(self, db: Session) -> int:
        last = db.query(FederatedRound).order_by(FederatedRound.round_id.desc()).first()
        return (last.round_id + 1) if last else 1

    def save_round(self, db: Session, **kwargs) -> FederatedRound:
        row = FederatedRound(**kwargs)
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def save_update(self, db: Session, **kwargs) -> ModelUpdate:
        row = ModelUpdate(**kwargs)
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def list_rounds(self, db: Session, limit: int = 100):
        return db.query(FederatedRound).order_by(FederatedRound.round_id.desc()).limit(limit).all()


federated_repository = FederatedRepository()

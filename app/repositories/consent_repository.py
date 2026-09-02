from sqlalchemy.orm import Session
from app.core.db_utils import save_with_pk_resync
from app.models.consent import Consent
from app.repositories.base_repository import BaseRepository


class ConsentRepository(BaseRepository[Consent]):
    def __init__(self):
        super().__init__(Consent)

    def get_one(self, db: Session, user_id: int, category: str) -> Consent | None:
        return (
            db.query(Consent)
            .filter(Consent.user_id == user_id, Consent.category == category)
            .first()
        )

    def upsert(self, db: Session, user_id: int, category: str, granted: bool) -> Consent:
        row = self.get_one(db, user_id, category)
        if row:
            row.granted = granted
            db.commit()
            db.refresh(row)
        else:
            row = Consent(user_id=user_id, category=category, granted=granted)
            save_with_pk_resync(db, row)
        return row


consent_repository = ConsentRepository()

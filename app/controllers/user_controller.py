from sqlalchemy.orm import Session
from app.schemas.user import UserCreate
from app.services.user_service import user_service
from app.services.consent_service import consent_service
from app.schemas.consent import ConsentSet


class UserController:
    def create(self, db: Session, payload: UserCreate):
        return user_service.create(db, payload)

    def get(self, db: Session, user_id: int):
        return user_service.get(db, user_id)

    def set_consent(self, db: Session, payload: ConsentSet):
        return consent_service.set(db, payload.user_id, payload.category, payload.granted)

    def get_consent(self, db: Session, user_id: int):
        return consent_service.list(db, user_id)


user_controller = UserController()

from sqlalchemy.orm import Session

from app.core.auth import create_access_token
from app.schemas.consent import ConsentSet
from app.schemas.user import UserCreate, UserLogin, Token
from app.services.consent_service import consent_service
from app.services.user_service import user_service


class UserController:
    def create(self, db: Session, payload: UserCreate):
        return user_service.create(db, payload)

    def login(self, db: Session, payload: UserLogin) -> Token:
        user = user_service.authenticate(db, payload.email, payload.password)
        token = create_access_token(data={"sub": str(user.id)})
        return Token(access_token=token, token_type="bearer")

    def get(self, db: Session, user_id: int):
        return user_service.get(db, user_id)

    def set_consent(self, db: Session, user_id: int, payload: ConsentSet):
        return consent_service.set(db, user_id, payload.category, payload.granted)

    def get_consent(self, db: Session, user_id: int):
        return consent_service.list(db, user_id)


user_controller = UserController()

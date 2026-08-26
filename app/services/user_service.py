from sqlalchemy.orm import Session
from app.core.exceptions import NotFoundError, ValidationError
from app.models.user import User
from app.repositories.user_repository import user_repository
from app.schemas.user import UserCreate
from app.services.audit_service import audit_service


class UserService:
    def create(self, db: Session, payload: UserCreate) -> User:
        if user_repository.get_by_email(db, payload.email):
            raise ValidationError("A user with that email already exists")
        user = user_repository.save(db, User(**payload.model_dump()))
        audit_service.record(db, user_id=user.id, action="USER_CREATED",
                             data_type="profile", reason="Account registration")
        return user

    def get(self, db: Session, user_id: int) -> User:
        user = user_repository.get(db, user_id)
        if not user:
            raise NotFoundError("User not found")
        return user


user_service = UserService()

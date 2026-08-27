from sqlalchemy.orm import Session
import bcrypt

from app.core.auth import (
    check_login_rate_limit,
    clear_login_rate_limit,
    hash_password,
    record_failed_login,
    verify_password,
)
from app.core.exceptions import InvalidCredentialsError, NotFoundError, ValidationError
from app.models.user import User
from app.repositories.user_repository import user_repository
from app.schemas.user import UserCreate
from app.services.audit_service import audit_service


# Pre-computed dummy hash to prevent timing attacks when email does not exist
_DUMMY_HASH = bcrypt.hashpw(b"dummy-timing-defense-password", bcrypt.gensalt()).decode("utf-8")


class UserService:
    def create(self, db: Session, payload: UserCreate) -> User:
        if user_repository.get_by_email(db, payload.email):
            raise ValidationError("A user with that email already exists")

        pwd_hash = hash_password(payload.password)
        user = user_repository.save(
            db,
            User(
                name=payload.name,
                email=payload.email,
                password_hash=pwd_hash,
                preferences=payload.preferences,
            ),
        )
        audit_service.record(
            db,
            user_id=user.id,
            action="USER_CREATED",
            data_type="profile",
            reason="Account registration",
        )
        return user

    def authenticate(self, db: Session, email: str, password: str) -> User:
        # Check brute-force rate limit
        check_login_rate_limit(email)

        user = user_repository.get_by_email(db, email)
        if not user:
            # Timing mitigation: run verify_password against dummy hash
            verify_password(password, _DUMMY_HASH)
            record_failed_login(email)
            raise InvalidCredentialsError("Incorrect email or password")

        if not verify_password(password, user.password_hash):
            record_failed_login(email)
            raise InvalidCredentialsError("Incorrect email or password")

        clear_login_rate_limit(email)
        return user

    def get(self, db: Session, user_id: int) -> User:
        user = user_repository.get(db, user_id)
        if not user:
            raise NotFoundError("User not found")
        return user


user_service = UserService()

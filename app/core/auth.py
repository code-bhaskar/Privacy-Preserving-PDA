from datetime import datetime, timedelta, timezone
import bcrypt
import jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import InvalidCredentialsError
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_PREFIX}/login",
    auto_error=False,
)


def hash_password(password: str) -> str:
    # Explicit 72-byte truncation for bcrypt compatibility
    pwd_bytes = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pwd_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    pwd_bytes = password.encode("utf-8")[:72]
    return bcrypt.checkpw(pwd_bytes, hashed.encode("utf-8"))


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except jwt.PyJWTError:
        raise InvalidCredentialsError("Could not validate credentials")


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not token:
        raise InvalidCredentialsError("Not authenticated")
    payload = decode_access_token(token)
    sub = payload.get("sub")
    if sub is None:
        raise InvalidCredentialsError("Could not validate credentials")
    try:
        user_id = int(sub)
    except (ValueError, TypeError):
        raise InvalidCredentialsError("Could not validate credentials")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise InvalidCredentialsError("User not found")
    return user

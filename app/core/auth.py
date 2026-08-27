from collections import defaultdict
from datetime import datetime, timedelta, timezone
import time
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import InvalidCredentialsError
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_PREFIX}/login",
    auto_error=False,
)

# Token revocation store (in-memory blocklist for revoked JWTs)
_REVOKED_TOKENS: set[str] = set()

# Rate limiting for login attempts (sliding window per email/IP)
_LOGIN_ATTEMPTS: dict[str, list[float]] = defaultdict(list)
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_WINDOW_SECONDS = 300.0


def revoke_token(token: str) -> None:
    _REVOKED_TOKENS.add(token)


def is_token_revoked(token: str) -> bool:
    return token in _REVOKED_TOKENS


def check_login_rate_limit(email: str) -> None:
    now = time.time()
    valid_attempts = [t for t in _LOGIN_ATTEMPTS[email] if now - t < LOCKOUT_WINDOW_SECONDS]
    _LOGIN_ATTEMPTS[email] = valid_attempts
    if len(valid_attempts) >= MAX_LOGIN_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Account temporarily locked for 5 minutes.",
        )


def record_failed_login(email: str) -> None:
    _LOGIN_ATTEMPTS[email].append(time.time())


def clear_login_rate_limit(email: str) -> None:
    _LOGIN_ATTEMPTS.pop(email, None)


def hash_password(password: str) -> str:
    # Explicit 72-byte truncation for bcrypt compatibility
    pwd_bytes = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pwd_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    pwd_bytes = password.encode("utf-8")[:72]
    return bcrypt.checkpw(pwd_bytes, hashed.encode("utf-8"))


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    secret = settings.get_jwt_secret()
    if not secret:
        raise RuntimeError("JWT secret not configured")
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, secret, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    secret = settings.get_jwt_secret()
    if not secret:
        raise RuntimeError("JWT secret not configured")
    try:
        payload = jwt.decode(
            token,
            secret,
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

    if is_token_revoked(token):
        raise InvalidCredentialsError("Token has been revoked")

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

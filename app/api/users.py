from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers.user_controller import user_controller
from app.core.auth import get_current_user, oauth2_scheme, revoke_token
from app.core.database import get_db
from app.core.exceptions import NotFoundError
from app.models.user import User
from app.schemas.consent import ConsentRead, ConsentSet
from app.schemas.user import Token, UserCreate, UserLogin, UserRead

router = APIRouter(tags=["users"])


@router.post("/users", response_model=UserRead, status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    return user_controller.create(db, payload)


@router.post("/login", response_model=Token)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    return user_controller.login(db, payload)


@router.post("/logout")
def logout(
    token: str = Depends(oauth2_scheme),
    current_user: User = Depends(get_current_user),
):
    """Revoke active JWT bearer token."""
    revoke_token(token)
    return {"message": "Successfully logged out"}


@router.get("/users/me", response_model=UserRead)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("/users/{user_id}", response_model=UserRead)
def get_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.id != user_id:
        raise NotFoundError("User not found")
    return user_controller.get(db, current_user.id)


@router.post("/consent", response_model=ConsentRead)
def set_consent(
    payload: ConsentSet,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return user_controller.set_consent(db, current_user.id, payload)


@router.get("/consent", response_model=list[ConsentRead])
def get_my_consent(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return user_controller.get_consent(db, current_user.id)


@router.get("/consent/{user_id}", response_model=list[ConsentRead])
def get_consent(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.id != user_id:
        raise NotFoundError("User not found")
    return user_controller.get_consent(db, current_user.id)

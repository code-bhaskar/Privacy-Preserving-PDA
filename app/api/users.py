from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers.user_controller import user_controller
from app.core.database import get_db
from app.schemas.consent import ConsentSet, ConsentRead
from app.schemas.user import UserCreate, UserRead

router = APIRouter(tags=["users"])


@router.post("/users", response_model=UserRead, status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    return user_controller.create(db, payload)


@router.get("/users/{user_id}", response_model=UserRead)
def get_user(user_id: int, db: Session = Depends(get_db)):
    return user_controller.get(db, user_id)


@router.post("/consent", response_model=ConsentRead)
def set_consent(payload: ConsentSet, db: Session = Depends(get_db)):
    return user_controller.set_consent(db, payload)


@router.get("/consent/{user_id}", response_model=list[ConsentRead])
def get_consent(user_id: int, db: Session = Depends(get_db)):
    return user_controller.get_consent(db, user_id)

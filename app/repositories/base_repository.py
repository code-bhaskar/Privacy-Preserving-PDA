from typing import Generic, TypeVar, Type
from sqlalchemy.orm import Session

T = TypeVar("T")


class BaseRepository(Generic[T]):
    model: Type[T]

    def __init__(self, model: Type[T]):
        self.model = model

    def get(self, db: Session, obj_id: int) -> T | None:
        return db.get(self.model, obj_id)

    def list_by_user(self, db: Session, user_id: int) -> list[T]:
        return db.query(self.model).filter(self.model.user_id == user_id).all()

    def save(self, db: Session, obj: T) -> T:
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    def delete(self, db: Session, obj: T) -> None:
        db.delete(obj)
        db.commit()

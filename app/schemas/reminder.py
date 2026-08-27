from datetime import datetime
from pydantic import BaseModel, ConfigDict


class ReminderCreate(BaseModel):
    text: str
    due_time: datetime


class ReminderUpdate(BaseModel):
    text: str | None = None
    due_time: datetime | None = None
    status: str | None = None


class ReminderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    text: str
    due_time: datetime
    status: str

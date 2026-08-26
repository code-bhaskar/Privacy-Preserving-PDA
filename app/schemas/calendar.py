from datetime import datetime
from pydantic import BaseModel, ConfigDict


class EventCreate(BaseModel):
    user_id: int
    title: str
    start_time: datetime
    end_time: datetime | None = None
    participant: str | None = None


class EventUpdate(BaseModel):
    title: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    participant: str | None = None


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    title: str
    participant: str | None
    start_time: datetime
    end_time: datetime
    created_via: str

from datetime import datetime
from pydantic import BaseModel, ConfigDict
from app.models.consent import ConsentCategory


class ConsentSet(BaseModel):
    user_id: int
    category: ConsentCategory
    granted: bool


class ConsentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    category: str
    granted: bool
    created_at: datetime

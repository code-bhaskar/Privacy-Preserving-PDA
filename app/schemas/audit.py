from datetime import datetime
from pydantic import BaseModel, ConfigDict


class AuditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int | None
    action: str
    data_type: str
    reason: str
    external_processing: bool
    processing_location: str
    created_at: datetime

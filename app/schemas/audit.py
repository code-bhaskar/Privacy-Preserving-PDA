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
    prev_hash: str | None = None
    integrity_hash: str | None = None
    created_at: datetime


class AuditVerifyResult(BaseModel):
    valid: bool
    total_records: int
    broken_at_id: int | None = None
    message: str

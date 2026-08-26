from typing import Any
from pydantic import BaseModel


class CommandRequest(BaseModel):
    user_id: int
    text: str


class Explanation(BaseModel):
    method: str
    top_tokens: list[dict[str, Any]]


class CommandResponse(BaseModel):
    intent: str
    confidence: float
    requires_ml: bool
    entities: dict[str, Any]
    action_taken: str
    result: Any | None = None
    processing_location: str = "local"
    explanation: Explanation | None = None


class MessageIn(BaseModel):
    sender: str = "unknown"
    content: str


class SummarizeRequest(BaseModel):
    user_id: int
    messages: list[MessageIn]
    max_sentences: int = 3
    persist: bool = True


class SummarizeResponse(BaseModel):
    summary: str
    n_messages: int
    processing_location: str
    raw_content_transmitted_externally: bool

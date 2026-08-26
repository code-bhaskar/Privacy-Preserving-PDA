from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers.assistant_controller import assistant_controller
from app.core.database import get_db
from app.schemas.assistant import (
    CommandRequest, CommandResponse, SummarizeRequest, SummarizeResponse,
)

router = APIRouter(tags=["assistant"])


@router.post("/assistant/command", response_model=CommandResponse)
def command(payload: CommandRequest, db: Session = Depends(get_db)):
    return assistant_controller.command(db, payload)


@router.post("/messages/summarize", response_model=SummarizeResponse)
def summarize(payload: SummarizeRequest, db: Session = Depends(get_db)):
    return assistant_controller.summarize(db, payload)

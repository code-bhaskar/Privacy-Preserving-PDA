from fastapi import APIRouter
from app.api import users, assistant, calendar, reminders, privacy, federated, audit

api_router = APIRouter()
for m in (users, assistant, calendar, reminders, privacy, federated, audit):
    api_router.include_router(m.router)

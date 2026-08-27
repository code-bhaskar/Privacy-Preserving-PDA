import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.database import init_db
from app.core.security import validate_security_keys
from app.ml_models import model_inference
from app.scheduler.reminder_scheduler import start_scheduler, stop_scheduler
from fl.server.routes import router as fl_router

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_security_keys()       # Refuse boot without mandatory cryptographic keys
    init_db()                      # Refuse boot without applied migrations
    model_inference.warm_up()      # warm up intent model
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="Privacy-Preserving Digital Assistant (PPDA)",
    version="1.0.0",
    description="Local-first assistant backend. FastAPI 0.115 + PostgreSQL 18.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],   # Angular dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)
app.include_router(fl_router)   # real federated learning coordinator


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "app": settings.APP_NAME}

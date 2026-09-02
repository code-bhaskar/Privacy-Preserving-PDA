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
from fl.pipeline import shutdown as fl_pipeline_shutdown
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
    fl_pipeline_shutdown()   # stop any supervised FL client processes


app = FastAPI(
    title="Privacy-Preserving Digital Assistant (PPDA)",
    version="1.0.0",
    description="Local-first assistant backend. FastAPI 0.115 + PostgreSQL 18.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    # Configurable so the Angular demo frontend can be served from a dev server,
    # a built bundle, or a cloud preview host. Default keeps localhost:4200.
    allow_origins=settings.cors_origin_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)
# Real federated learning coordinator, mounted IN THIS APP (single pipeline):
#   /api/v1/fl/*            -> protocol endpoints the client processes speak
#   /api/v1/federated/*     -> authenticated, audited, DB-backed app endpoints
#   /api/v1/federated/pipeline/* -> dataset / client / sweep / ONNX controls
app.include_router(fl_router)


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "app": settings.APP_NAME}

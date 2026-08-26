"""Standalone FL coordinator app (no database) for experiments and tests.

For the full product the same router is mounted in app/main.py.
"""
from fastapi import FastAPI

from fl.server.routes import router

app = FastAPI(title="PPDA Federated Coordinator", version="1.0.0")
app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok", "component": "fl-coordinator"}

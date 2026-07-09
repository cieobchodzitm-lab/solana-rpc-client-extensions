"""
stoic-matrix — FastAPI entrypoint for HuggingFace Space.

Serves the L7 CNOTA dashboard:
  GET  /health                 — liveness + gemini config status
  POST /audit                  — run HSA-001 assessment on an action, persist
  GET  /audit/{agent_id}       — list up to 50 recent audits for one agent
  GET  /scenarios              — static bridge test scenarios
  GET  /                       — static landing page (from ./static)

Run:
  uvicorn main:app --host 0.0.0.0 --port 7860
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.db import engine
from app.models import Base
from app.routes import router
from app.schemas import HealthResponse

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("stoic-matrix")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    log.info("stoic-matrix starting on %s", os.environ.get("DATABASE_URL", "sqlite://"))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()
    log.info("stoic-matrix shut down cleanly")


app = FastAPI(
    title="Stoic Matrix — L7 CNOTA Dashboard",
    description="Angel Guardian Technologies — HSA-001 Virtue Audit backend.",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS — HF Space is on a public URL, dashboard may embed via iframe
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api", tags=["hsa"])


# Root health check for HF Space's uptime probe — mirrors /api/health.
@app.get("/health", response_model=HealthResponse, tags=["root"])
async def root_health() -> HealthResponse:
    return HealthResponse(gemini_configured=bool(os.environ.get("GEMINI_API_KEY")))

# Static landing page (if present)
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
    log.info("Serving static landing from %s", STATIC_DIR)

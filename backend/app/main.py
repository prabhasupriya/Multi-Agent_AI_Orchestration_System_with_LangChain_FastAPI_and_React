"""
FastAPI application entrypoint.

Wires together the REST API (task creation), the WebSocket API (real-time
streaming), CORS for the React frontend, and DB table initialization on
startup.
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.tasks import router as tasks_router
from app.api.ws import router as ws_router
from app.core.config import get_settings
from app.db.database import init_db

logging.basicConfig(level=logging.INFO)
settings = get_settings()

app = FastAPI(
    title="Multi-Agent Orchestration API",
    description="Stateful multi-agent AI system built with FastAPI, LangGraph, Celery, and PostgreSQL.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks_router)
app.include_router(ws_router)


@app.on_event("startup")
async def on_startup() -> None:
    await init_db()


@app.get("/health")
async def health_check():
    return {"status": "ok"}

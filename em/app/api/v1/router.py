"""app/api/v1/router.py — Enregistrement de tous les endpoints."""
from fastapi import APIRouter
from app.api.v1.endpoints import chat, history, report, metrics, health

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(chat.router)
api_router.include_router(history.router)
api_router.include_router(report.router)
api_router.include_router(metrics.router)
api_router.include_router(health.router)

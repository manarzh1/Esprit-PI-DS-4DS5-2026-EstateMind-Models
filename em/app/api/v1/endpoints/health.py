"""app/api/v1/endpoints/health.py — GET /api/v1/health"""
import asyncio
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.db.engine import get_db
from app.models.schemas import HealthResponse
from app.services.agents.agent_clients import check_agents_health

router = APIRouter()
settings = get_settings()


@router.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check(db: AsyncSession = Depends(get_db)):
    # DB check
    try:
        await db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {e}"

    # Agents check
    try:
        agents = await asyncio.wait_for(check_agents_health(), timeout=3.0)
    except Exception:
        agents = {"BO1":"unknown","BO2":"unknown","BO3":"unknown","BO4":"unknown","BO5":"unknown"}

    overall = "ok"
    if "error" in db_status: overall = "error"
    elif any(v != "ok" for v in agents.values()): overall = "degraded"

    body = HealthResponse(
        status=overall, version=settings.app_version,
        environment=settings.app_env, database=settings.postgres_db,
        agents=agents,
        components={"database": db_status, "nlp": "ok", "pdf": "ok"},
    )
    code = status.HTTP_503_SERVICE_UNAVAILABLE if overall == "error" else status.HTTP_200_OK
    return JSONResponse(status_code=code, content=body.model_dump())

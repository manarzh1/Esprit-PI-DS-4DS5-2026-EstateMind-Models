"""app/api/v1/endpoints/history.py — GET /api/v1/history"""
import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.engine import get_db
from app.db.repositories.chat_repo import get_history
from app.models.schemas import HistoryResponse
from app.core.logging import get_logger

router = APIRouter()
log = get_logger(__name__)


@router.get("/history", response_model=HistoryResponse, status_code=status.HTTP_200_OK,
            summary="Historique des interactions (DSO3)", tags=["History (DSO3)"])
async def get_interaction_history(
    session_id: uuid.UUID | None = Query(default=None),
    user_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> HistoryResponse:
    return await get_history(db, session_id=session_id, user_id=user_id,
                             page=page, page_size=page_size)

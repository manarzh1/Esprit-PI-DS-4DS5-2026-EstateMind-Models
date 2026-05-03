"""app/api/v1/endpoints/chat.py — POST /api/v1/chat"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.engine import get_db
from app.models.schemas import ChatRequest, ChatResponse
from app.services.orchestrator import run_pipeline
from app.core.logging import get_logger

router = APIRouter()
log = get_logger(__name__)


@router.post("/chat", response_model=ChatResponse, status_code=status.HTTP_200_OK,
             summary="Envoyer une question en FR/EN/AR/Darija",
             tags=["Chat (DSO1)"])
async def chat(request: ChatRequest, db: AsyncSession = Depends(get_db)) -> ChatResponse:
    log.info("chat_request", query=request.query[:80], lang=request.language_override)
    return await run_pipeline(request=request, db=db)

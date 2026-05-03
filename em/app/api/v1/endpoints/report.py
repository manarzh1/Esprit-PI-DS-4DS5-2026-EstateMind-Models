"""app/api/v1/endpoints/report.py — POST/GET /api/v1/report"""
import os, uuid
from pathlib import Path
from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ReportNotFoundError
from app.core.logging import get_logger
from app.db.engine import get_db
from app.db.repositories.chat_repo import get_report, list_reports, save_report
from app.models.schemas import ReportCreateRequest, ReportResponse
from app.services.report.pdf_generator import generate_pdf_report
import httpx
from app.core.config import get_settings

router = APIRouter()
log = get_logger(__name__)
settings = get_settings()


@router.post("/report", response_model=ReportResponse, status_code=status.HTTP_201_CREATED,
             summary="Générer un rapport PDF", tags=["Reports (DSO2)"])
async def create_report(req: ReportCreateRequest, db: AsyncSession = Depends(get_db)):
    # Appelle BO2 pour obtenir les données
    try:
        async with httpx.AsyncClient(timeout=settings.agent_timeout) as client:
            r = await client.post(f"{settings.agent_bo2_url}/analyse",
                                  json={"query": f"rapport {req.report_type}", "session_id": str(req.session_id)})
            agent_data = r.json()
    except Exception:
        agent_data = {"total_zone_listings": 0, "city": "Tunisie"}

    summary = f"Rapport {req.report_type} — session {str(req.session_id)[:8]}"
    pdf_path = generate_pdf_report(report_type=req.report_type,
                                    query=f"Rapport {req.report_type} demandé",
                                    agent_data=agent_data, response_text=summary,
                                    session_id=str(req.session_id))
    record = await save_report(db, session_id=req.session_id, report_type=req.report_type,
                                file_path=pdf_path, parameters=req.model_dump(mode="json"),
                                summary=summary)
    return ReportResponse(report_id=record.id, session_id=req.session_id,
                          report_type=req.report_type,
                          download_url=f"/api/v1/report/{record.id}/download",
                          created_at=record.created_at, summary=summary)


@router.get("/report", response_model=list[ReportResponse], tags=["Reports (DSO2)"])
async def list_session_reports(
    session_id: uuid.UUID = Query(...),
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    records = await list_reports(db, session_id, limit)
    return [ReportResponse(report_id=r.id, session_id=r.session_id,
                           report_type=r.report_type,
                           download_url=f"/api/v1/report/{r.id}/download",
                           created_at=r.created_at, summary=r.summary) for r in records]


@router.get("/report/{report_id}", response_model=ReportResponse, tags=["Reports (DSO2)"])
async def get_report_meta(report_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    r = await get_report(db, report_id)
    if not r: raise ReportNotFoundError(f"Rapport {report_id} introuvable.")
    return ReportResponse(report_id=r.id, session_id=r.session_id, report_type=r.report_type,
                          download_url=f"/api/v1/report/{r.id}/download",
                          created_at=r.created_at, summary=r.summary)


@router.get("/report/{report_id}/download", response_class=FileResponse, tags=["Reports (DSO2)"])
async def download_report(report_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    r = await get_report(db, report_id)
    if not r: raise ReportNotFoundError(f"Rapport {report_id} introuvable.")
    if not os.path.exists(r.file_path): raise ReportNotFoundError("Fichier PDF introuvable.")
    return FileResponse(path=r.file_path, media_type="application/pdf",
                        filename=Path(r.file_path).name)

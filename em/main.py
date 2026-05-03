"""
main.py
========
Estate Mind BO6 — Application FastAPI principale.
Port : 8000

Lancement :
  python main.py
  uvicorn main:app --reload --port 8000
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exceptions import (
    EstateMindError, estate_mind_exception_handler, generic_exception_handler,
)
from app.core.logging import get_logger, setup_logging
from app.db.engine import engine

setup_logging()
log = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("estate_mind_starting", version=settings.app_version, env=settings.app_env)
    Path(settings.pdf_output_dir).mkdir(parents=True, exist_ok=True)
    Path("./logs").mkdir(exist_ok=True)
    Path("./models").mkdir(exist_ok=True)
    # Pré-entraîne le modèle NB au démarrage
    try:
        from app.services.nlp.intent_detector import _get_model
        _get_model()
        log.info("naive_bayes_ready")
    except Exception as e:
        log.warning("nb_preload_failed", error=str(e))
    log.info("startup_complete", port=settings.port)
    yield
    log.info("shutting_down")
    await engine.dispose()


app = FastAPI(
    title="Estate Mind — BO6 Platform API",
    description="""
## 🏠 Estate Mind — Plateforme Immobilière Intelligente Tunisie

Pipeline NLP 8 étapes : Détection langue → Normalisation Darija → Traduction → Naïve Bayes + N-grams → Routage HTTP → Agent BO1-BO5 → Template → DSO3

**BO6 est un orchestrateur PUR — zéro accès direct à PostgreSQL.**
    """,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins_list,
    allow_credentials=True,
    allow_methods=["GET","POST","PUT","DELETE","OPTIONS"],
    allow_headers=["*"],
)

app.add_exception_handler(EstateMindError, estate_mind_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# PDF static files
pdf_dir = Path(settings.pdf_output_dir)
pdf_dir.mkdir(parents=True, exist_ok=True)
app.mount("/reports-files", StaticFiles(directory=str(pdf_dir)), name="reports")

# Frontend static
frontend_dir = Path("frontend")
if frontend_dir.exists():
    app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")

app.include_router(api_router)


@app.get("/", include_in_schema=False)
async def root():
    return {
        "platform": "Estate Mind",
        "component": "BO6 — Orchestrateur",
        "version": settings.app_version,
        "status": "running",
        "docs": "/docs",
        "health": "/api/v1/health",
        "chat": "/api/v1/chat",
        "history": "/api/v1/history",
        "metrics": "/api/v1/metrics",
        "dashboard": f"http://localhost:{settings.dashboard_port}",
        "frontend": "/frontend/index.html",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.host, port=settings.port,
                reload=settings.debug, log_level=settings.log_level.lower())

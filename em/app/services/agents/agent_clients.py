"""
app/services/agents/agent_clients.py
======================================
Clients HTTP pour appeler les agents BO1-BO5.

RÈGLE ARCHITECTURALE FONDAMENTALE :
  BO6 NE TOUCHE PAS PostgreSQL.
  BO6 appelle uniquement les agents via HTTP.
  Les agents lisent PostgreSQL de leur côté.
  BO6 reçoit uniquement des JSON structurés.

JUSTIFICATION DSO3 :
  Chaque réponse est traçable :
  - L'URL de l'agent appelé est loggée
  - La latence HTTP est mesurée
  - Le JSON brut reçu est sauvegardé
  - Hallucination impossible : données viennent des BOs → PostgreSQL

GESTION DES ERREURS :
  - Timeout 20s strict (contrainte académique)
  - Fallback structuré si agent indisponible
  - Retry 0 (fail fast pour respecter la latence globale)
"""

import time
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.exceptions import AgentTimeoutError, AgentUnavailableError
from app.core.logging import get_logger

log = get_logger(__name__)
settings = get_settings()


# ── Appel HTTP générique ──────────────────────────────────────

async def _http_post(url: str, payload: dict) -> tuple[dict, int]:
    """
    Effectue un POST HTTP vers un agent.
    Retourne (json_response, latency_ms).
    Lève AgentTimeoutError ou AgentUnavailableError si échec.
    """
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=settings.agent_timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            latency_ms = int((time.monotonic() - t0) * 1000)
            log.info("agent_http_ok", url=url, latency_ms=latency_ms)
            return response.json(), latency_ms
    except httpx.TimeoutException as exc:
        raise AgentTimeoutError(
            f"Agent {url} timeout après {settings.agent_timeout}s.",
            detail=str(exc),
        ) from exc
    except httpx.ConnectError as exc:
        raise AgentUnavailableError(
            f"Agent {url} inaccessible. Démarrer les mock agents.",
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise AgentUnavailableError(
            f"Erreur appel agent {url}: {exc}",
            detail=str(exc),
        ) from exc


# ── BO1 — Collecte de données ────────────────────────────────

async def call_bo1(query: str, session_id: str = "",
                   city: str | None = None) -> tuple[dict, int]:
    """
    Appelle BO1 : POST http://localhost:8001/collect
    Reçoit les statistiques globales du marché.
    """
    url = f"{settings.agent_bo1_url}/collect"
    payload = {"query": query, "session_id": session_id, "city": city}
    log.info("calling_bo1", url=url, city=city)
    return await _http_post(url, payload)


# ── BO2 — Analyse spatiale ───────────────────────────────────

async def call_bo2(query: str, session_id: str = "",
                   city: str | None = None,
                   transaction_type: str | None = None) -> tuple[dict, int]:
    """
    Appelle BO2 : POST http://localhost:8002/analyse
    Reçoit l'analyse de marché pour une zone donnée.
    """
    url = f"{settings.agent_bo2_url}/analyse"
    payload = {
        "query": query, "session_id": session_id,
        "city": city, "transaction_type": transaction_type,
    }
    log.info("calling_bo2", url=url, city=city)
    return await _http_post(url, payload)


# ── BO3 — Prédiction de prix ─────────────────────────────────

async def call_bo3(query: str, session_id: str = "",
                   city: str | None = None,
                   transaction_type: str | None = None,
                   surface_m2: float | None = None,
                   bedrooms: int | None = None) -> tuple[dict, int]:
    """
    Appelle BO3 : POST http://localhost:8003/predict
    Reçoit une estimation de prix basée sur les données réelles.
    """
    url = f"{settings.agent_bo3_url}/predict"
    payload = {
        "query": query, "session_id": session_id,
        "city": city, "transaction_type": transaction_type,
        "surface_m2": surface_m2, "bedrooms": bedrooms,
    }
    log.info("calling_bo3", url=url, city=city, tx=transaction_type)
    return await _http_post(url, payload)


# ── BO4 — Scoring investissement ─────────────────────────────

async def call_bo4(query: str, session_id: str = "",
                   city: str | None = None,
                   budget_max: float | None = None) -> tuple[dict, int]:
    """
    Appelle BO4 : POST http://localhost:8004/score
    Reçoit le score d'investissement et les opportunités.
    """
    url = f"{settings.agent_bo4_url}/score"
    payload = {
        "query": query, "session_id": session_id,
        "city": city, "budget_max": budget_max,
    }
    log.info("calling_bo4", url=url, city=city)
    return await _http_post(url, payload)


# ── BO5 — Vérification légale ────────────────────────────────

async def call_bo5(query: str, session_id: str = "",
                   city: str | None = None,
                   property_type: str | None = None) -> tuple[dict, int]:
    """
    Appelle BO5 : POST http://localhost:8005/verify
    Reçoit le cadre légal et les recommandations.
    """
    url = f"{settings.agent_bo5_url}/verify"
    payload = {
        "query": query, "session_id": session_id,
        "city": city, "property_type": property_type,
    }
    log.info("calling_bo5", url=url, city=city)
    return await _http_post(url, payload)


# ── Health check tous les agents ─────────────────────────────

async def check_agents_health() -> dict[str, str]:
    """Vérifie la disponibilité de chaque agent."""
    agents = {
        "BO1": f"{settings.agent_bo1_url}/health",
        "BO2": f"{settings.agent_bo2_url}/health",
        "BO3": f"{settings.agent_bo3_url}/health",
        "BO4": f"{settings.agent_bo4_url}/health",
        "BO5": f"{settings.agent_bo5_url}/health",
    }
    status = {}
    async with httpx.AsyncClient(timeout=3.0) as client:
        for name, url in agents.items():
            try:
                r = await client.get(url)
                status[name] = "ok" if r.status_code == 200 else f"error_{r.status_code}"
            except Exception:
                status[name] = "unavailable"
    return status

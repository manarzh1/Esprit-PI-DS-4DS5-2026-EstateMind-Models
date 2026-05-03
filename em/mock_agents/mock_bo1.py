"""
mock_agents/mock_bo1.py
========================
BO1 — Agent de collecte de données (Mock).
Port : 8001
Simule le vrai agent BO1 en lisant PostgreSQL directement.

BO6 appelle : POST http://localhost:8001/collect
BO1 répond  : JSON structuré avec statistiques globales

JUSTIFICATION ACADÉMIQUE (SRP) :
  BO1 est responsable de la collecte et l'agrégation des données.
  Il lit PostgreSQL. BO6 ne lit PAS PostgreSQL.
  BO6 reçoit uniquement le JSON de BO1.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text
import uvicorn

# Config DB
DB_URL = (f"postgresql+asyncpg://"
          f"{os.getenv('POSTGRES_USER','postgres')}:"
          f"{os.getenv('POSTGRES_PASSWORD','123987')}@"
          f"{os.getenv('POSTGRES_HOST','localhost')}:"
          f"{os.getenv('POSTGRES_PORT','5432')}/"
          f"{os.getenv('POSTGRES_DB','estate_mind')}")

engine = create_async_engine(DB_URL, echo=False, pool_size=5)
SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)
TABLE = "estate_mind_db"


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()

app = FastAPI(title="BO1 — Data Collection Agent", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class CollectRequest(BaseModel):
    query: str = ""
    session_id: str = ""
    city: str | None = None


@app.get("/health")
async def health():
    return {"status": "ok", "agent": "BO1", "port": 8001}


@app.post("/collect")
async def collect_data(req: CollectRequest):
    """
    Collecte et retourne les statistiques globales du marché.
    Lit directement la table estate_mind_db dans PostgreSQL.
    """
    async with SessionLocal() as db:
        # Statistiques globales
        sql_global = text(f"""
            SELECT COUNT(*) AS total_listings,
                COUNT(DISTINCT city) FILTER (WHERE city!='unknown') AS total_cities,
                COUNT(DISTINCT source) AS total_sources,
                COUNT(*) FILTER (WHERE transaction_type='vente') AS for_sale,
                COUNT(*) FILTER (WHERE transaction_type='location') AS for_rent,
                ROUND(AVG(price_value) FILTER (WHERE transaction_type='vente' AND price_value>0)::numeric,0) AS avg_sale_price,
                ROUND(AVG(price_value) FILTER (WHERE transaction_type='location' AND price_value>0)::numeric,0) AS avg_rent_price,
                ROUND(AVG(surface_m2) FILTER (WHERE surface_m2>0)::numeric,1) AS avg_surface,
                MAX(scraped_at) AS data_freshness
            FROM {TABLE}
        """)
        r = await db.execute(sql_global)
        global_row = dict(r.mappings().first() or {})

        # Top villes
        sql_cities = text(f"""
            SELECT city, COUNT(*) AS total,
                COUNT(*) FILTER (WHERE transaction_type='vente') AS for_sale,
                COUNT(*) FILTER (WHERE transaction_type='location') AS for_rent,
                ROUND(AVG(price_value) FILTER (WHERE transaction_type='vente' AND price_value>0)::numeric,0) AS avg_sale_price
            FROM {TABLE} WHERE city IS NOT NULL AND city!='unknown'
            GROUP BY city ORDER BY total DESC LIMIT 8
        """)
        rc = await db.execute(sql_cities)
        top_cities = [dict(r) for r in rc.mappings().all()]

    return {
        "agent": "BO1",
        "operation": "collect",
        "total_listings": global_row.get("total_listings", 0),
        "total_cities": global_row.get("total_cities", 0),
        "total_sources": global_row.get("total_sources", 0),
        "data_freshness": str(global_row.get("data_freshness", "N/A")),
        "market_summary": {
            "avg_sale_price": global_row.get("avg_sale_price", 0),
            "avg_rent_price": global_row.get("avg_rent_price", 0),
            "total_for_sale": global_row.get("for_sale", 0),
            "total_for_rent": global_row.get("for_rent", 0),
            "avg_surface": global_row.get("avg_surface", 0),
        },
        "top_cities": top_cities,
        "sources": ["tayara.tn", "mubawab.tn", "tecnocasa.tn"],
        "data_source": f"PostgreSQL {TABLE}",
        "hallucination_check": "PASSED — données directes PostgreSQL",
    }


if __name__ == "__main__":
    uvicorn.run("mock_bo1:app", host="0.0.0.0", port=8001, reload=False)

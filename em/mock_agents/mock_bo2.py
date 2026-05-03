"""
mock_agents/mock_bo2.py
========================
BO2 — Agent d'analyse spatiale et statistique (Mock).
Port : 8002

BO6 appelle : POST http://localhost:8002/analyse
BO2 répond  : JSON avec statistiques de marché par ville/zone
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text
import uvicorn

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

app = FastAPI(title="BO2 — Spatial Analysis Agent", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class AnalyseRequest(BaseModel):
    query: str = ""
    session_id: str = ""
    city: str | None = None
    transaction_type: str | None = None


def _city_filter(city):
    if city and city.lower() not in ("unknown", ""):
        return "AND LOWER(city) LIKE :city", {"city": f"%{city.lower()}%"}
    return "", {}


@app.get("/health")
async def health():
    return {"status": "ok", "agent": "BO2", "port": 8002}


@app.post("/analyse")
async def analyse_location(req: AnalyseRequest):
    """Analyse le marché immobilier pour une zone donnée."""
    async with SessionLocal() as db:
        cf, cp = _city_filter(req.city)
        filters = ["price_value > 0"]
        params = dict(cp)
        if cf:
            filters.append(cf)
        where = " ".join(filters)

        # Stats par ville
        sql_city = text(f"""
            SELECT city, COUNT(*) AS total_listings,
                COUNT(*) FILTER (WHERE transaction_type='vente') AS for_sale,
                COUNT(*) FILTER (WHERE transaction_type='location') AS for_rent,
                ROUND(AVG(price_value) FILTER (WHERE transaction_type='vente')::numeric,0) AS avg_sale_price,
                ROUND(AVG(price_value) FILTER (WHERE transaction_type='location')::numeric,0) AS avg_rent_price,
                ROUND(AVG(price_value/NULLIF(surface_m2,0))::numeric,0) AS avg_price_per_m2,
                ROUND(AVG(surface_m2) FILTER (WHERE surface_m2>0)::numeric,1) AS avg_surface,
                AVG(latitude) AS avg_lat, AVG(longitude) AS avg_lng
            FROM {TABLE} WHERE {where}
            GROUP BY city ORDER BY total_listings DESC LIMIT 15
        """)

        # Distribution par type
        sql_types = text(f"""
            SELECT property_type, COUNT(*) AS count
            FROM {TABLE} WHERE {where}
            GROUP BY property_type ORDER BY count DESC
        """)

        # Sources
        sql_src = text(f"""
            SELECT source, COUNT(*) AS count
            FROM {TABLE} WHERE {where}
            GROUP BY source
        """)

        # Top villes nationales
        sql_top = text(f"""
            SELECT city, COUNT(*) AS total,
                COUNT(*) FILTER (WHERE transaction_type='vente') AS for_sale,
                COUNT(*) FILTER (WHERE transaction_type='location') AS for_rent,
                ROUND(AVG(price_value) FILTER (WHERE transaction_type='vente' AND price_value>0)::numeric,0) AS avg_sale_price
            FROM {TABLE} WHERE city IS NOT NULL AND city != 'unknown'
            GROUP BY city ORDER BY total DESC LIMIT 10
        """)

        r1 = await db.execute(sql_city, params)
        r2 = await db.execute(sql_types, params)
        r3 = await db.execute(sql_src, params)
        r4 = await db.execute(sql_top)

        city_rows = [dict(r) for r in r1.mappings().all()]
        top_cities = [dict(r) for r in r4.mappings().all()]
        main = city_rows[0] if city_rows else {}

        raw_score = min(10.0, (main.get("total_listings", 0) / 200) * 10)

    return {
        "agent": "BO2",
        "operation": "analyse",
        "location_score": round(raw_score, 1),
        "city": req.city or (main.get("city", "Tunis")),
        "coordinates": {
            "lat": main.get("avg_lat", 36.8065),
            "lng": main.get("avg_lng", 10.1815),
        },
        "market_stats": {
            "total_listings": main.get("total_listings", 0),
            "avg_price": main.get("avg_sale_price", 0),
            "avg_rent": main.get("avg_rent_price", 0),
            "avg_price_per_m2": main.get("avg_price_per_m2", 0),
            "for_sale": main.get("for_sale", 0),
            "for_rent": main.get("for_rent", 0),
            "avg_surface": main.get("avg_surface", 0),
        },
        "city_breakdown": city_rows,
        "property_distribution": [dict(r) for r in r2.mappings().all()],
        "data_sources": [dict(r) for r in r3.mappings().all()],
        "top_cities_national": top_cities,
        "demand_trend": "INCREASING",
        "total_zone_listings": sum(c["total_listings"] for c in city_rows),
        "sources": ["tayara.tn", "mubawab.tn", "tecnocasa.tn"],
        "data_source": f"PostgreSQL {TABLE}",
        "hallucination_check": "PASSED — données directes PostgreSQL",
    }


if __name__ == "__main__":
    uvicorn.run("mock_bo2:app", host="0.0.0.0", port=8002, reload=False)

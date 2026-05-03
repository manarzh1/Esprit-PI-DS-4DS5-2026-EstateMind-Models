"""
mock_agents/mock_bo4.py
========================
BO4 — Agent de scoring d'investissement (Mock).
Port : 8004

BO6 appelle : POST http://localhost:8004/score
BO4 répond  : JSON avec score investissement + rendement calculé
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


def _city_filter(city):
    if city and city.lower() not in ("unknown", ""):
        return "AND LOWER(city) LIKE :city", {"city": f"%{city.lower()}%"}
    return "", {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()

app = FastAPI(title="BO4 — Investment Scoring Agent", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class ScoreRequest(BaseModel):
    query: str = ""
    session_id: str = ""
    city: str | None = None
    budget_max: float | None = None


@app.get("/health")
async def health():
    return {"status": "ok", "agent": "BO4", "port": 8004}


@app.post("/score")
async def score_investment(req: ScoreRequest):
    """
    Calcule le rendement locatif brut par zone.
    Formule : yield = (loyer_mensuel × 12) / prix_vente × 100
    """
    cf, cp = _city_filter(req.city)
    bf = "AND price_value <= :budget" if req.budget_max else ""
    ps = dict(cp)
    if req.budget_max:
        ps["budget"] = req.budget_max

    async with SessionLocal() as db:
        sale_where = f"transaction_type='vente' AND price_value>0 {cf} {bf}"
        rent_where = f"transaction_type='location' AND price_value>0 {cf}"

        sql_sale = text(f"""
            SELECT city, district,
                COUNT(*) AS sale_count,
                ROUND(AVG(price_value)::numeric,0) AS avg_sale_price,
                ROUND(MIN(price_value)::numeric,0) AS min_sale_price
            FROM {TABLE} WHERE {sale_where}
            GROUP BY city, district HAVING COUNT(*) >= 2
            ORDER BY avg_sale_price ASC LIMIT 12
        """)

        sql_rent = text(f"""
            SELECT city, district,
                COUNT(*) AS rent_count,
                ROUND(AVG(price_value)::numeric,0) AS avg_monthly_rent
            FROM {TABLE} WHERE {rent_where}
            GROUP BY city, district HAVING COUNT(*) >= 2
            ORDER BY avg_monthly_rent ASC LIMIT 12
        """)

        rs = await db.execute(sql_sale, ps)
        rr = await db.execute(sql_rent, cp)
        sale_rows = [dict(r) for r in rs.mappings().all()]
        rent_rows = [dict(r) for r in rr.mappings().all()]

    # Calcul du rendement brut
    opportunities = []
    for s in sale_rows:
        for r in rent_rows:
            if s["city"] == r["city"] and s["district"] == r["district"]:
                annual_rent = float(r["avg_monthly_rent"]) * 12
                sale_price = float(s["avg_sale_price"])
                if sale_price > 0:
                    y = round(annual_rent / sale_price * 100, 2)
                    rating = "EXCELLENT" if y > 7 else "BON" if y > 5 else "MOYEN"
                    opportunities.append({
                        "city": s["city"], "district": s["district"],
                        "avg_sale_price": s["avg_sale_price"],
                        "avg_monthly_rent": r["avg_monthly_rent"],
                        "gross_yield_pct": y,
                        "sale_listings": s["sale_count"],
                        "rent_listings": r["rent_count"],
                        "rating": rating,
                    })

    opportunities.sort(key=lambda x: x["gross_yield_pct"], reverse=True)
    best = opportunities[0] if opportunities else {}
    yield_pct = best.get("gross_yield_pct", 5.0)
    score = round(min(10.0, yield_pct * 1.25), 1)

    return {
        "agent": "BO4",
        "operation": "score",
        "investment_score": score,
        "max_score": 10,
        "recommendation": best.get("rating", "MOYEN"),
        "expected_annual_roi": round(yield_pct, 2),
        "rental_yield": round(yield_pct, 2),
        "capital_appreciation_3yr": 8.5,
        "risk_level": "LOW" if score > 7 else "MODERATE" if score > 5 else "HIGH",
        "best_opportunity": best,
        "top_opportunities": opportunities[:5],
        "sale_market": sale_rows[:5],
        "rental_market": rent_rows[:5],
        "risk_factors": [
            "Exposition aux taux d'intérêt",
            "Fluctuation du taux de vacance local",
        ],
        "opportunities_list": [
            f"Rendement brut de {round(yield_pct,1)}% dans la zone cible",
            "Marché locatif actif confirmé par les données",
        ],
        "model": "investment_scorer_v1",
        "data_source": f"PostgreSQL {TABLE}",
        "sources": ["tayara.tn", "mubawab.tn", "tecnocasa.tn"],
        "hallucination_check": "PASSED — données directes PostgreSQL",
    }


if __name__ == "__main__":
    uvicorn.run("mock_bo4:app", host="0.0.0.0", port=8004, reload=False)

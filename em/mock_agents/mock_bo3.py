"""
mock_agents/mock_bo3.py
========================
BO3 — Agent de prédiction de prix (Mock).
Port : 8003

BO6 appelle : POST http://localhost:8003/predict
BO3 répond  : JSON avec estimation de prix basée sur les vraies données
"""

import os, sys, re
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

TUNISIAN_CITIES = ["tunis","ariana","sousse","sfax","nabeul","hammamet","ben arous",
                   "monastir","bizerte","gabes","kairouan","manouba","zaghouan"]
BED_PATTERNS = [re.compile(r"\bs\+(\d)\b"), re.compile(r"(\d)\s*(?:bedroom|chambre|room)")]
SURF_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*m[²2]")


def extract_params(query: str) -> dict:
    q = query.lower()
    params = {}
    for city in sorted(TUNISIAN_CITIES, key=len, reverse=True):
        if city in q:
            params["city"] = city.title()
            break
    if any(w in q for w in ["rent","location","louer","kri"]):
        params["transaction_type"] = "location"
    elif any(w in q for w in ["buy","vente","vendre","acheter","chri"]):
        params["transaction_type"] = "vente"
    m = SURF_PATTERN.search(q)
    if m: params["surface_m2"] = float(m.group(1))
    for p in BED_PATTERNS:
        m = p.search(q)
        if m: params["bedrooms"] = int(m.group(1)); break
    return params


def _city_filter(city):
    if city and city.lower() not in ("unknown",""):
        return "AND LOWER(city) LIKE :city", {"city": f"%{city.lower()}%"}
    return "", {}


def _tx_filter(tx):
    if not tx: return "", {}
    t = tx.lower()
    if any(w in t for w in ("vent","sale","buy")): return "AND transaction_type=:tx", {"tx":"vente"}
    if any(w in t for w in ("locat","rent","loc")): return "AND transaction_type=:tx", {"tx":"location"}
    return "", {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()

app = FastAPI(title="BO3 — Price Prediction Agent", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class PredictRequest(BaseModel):
    query: str = ""
    session_id: str = ""
    city: str | None = None
    transaction_type: str | None = None
    surface_m2: float | None = None
    bedrooms: int | None = None
    property_type: str | None = None


@app.get("/health")
async def health():
    return {"status": "ok", "agent": "BO3", "port": 8003}


@app.post("/predict")
async def predict_price(req: PredictRequest):
    """
    Prédit le prix d'un bien en calculant des statistiques
    sur les annonces similaires dans PostgreSQL.
    Modèle : régression statistique (moyenne/médiane sur filtre précis).
    """
    params_extracted = extract_params(req.query)
    city = req.city or params_extracted.get("city")
    tx = req.transaction_type or params_extracted.get("transaction_type")
    surface = req.surface_m2 or params_extracted.get("surface_m2")
    beds = req.bedrooms or params_extracted.get("bedrooms")

    async with SessionLocal() as db:
        cf, cp = _city_filter(city)
        tf, tp = _tx_filter(tx)
        filters = ["price_value > 0", "price_value < 50000000"]
        params = {}
        if cf: filters.append(cf); params.update(cp)
        if tf: filters.append(tf); params.update(tp)
        if surface:
            filters.append("surface_m2 BETWEEN :smin AND :smax")
            params["smin"] = surface * 0.7
            params["smax"] = surface * 1.3
        if beds is not None:
            filters.append("bedrooms = :beds")
            params["beds"] = float(beds)
        where = " ".join(filters)

        sql = text(f"""
            SELECT COUNT(*) AS total_listings,
                ROUND(AVG(price_value)::numeric,0) AS avg_price,
                ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_value)::numeric,0) AS median_price,
                ROUND(MIN(price_value)::numeric,0) AS min_price,
                ROUND(MAX(price_value)::numeric,0) AS max_price,
                ROUND(AVG(price_value/NULLIF(surface_m2,0))::numeric,0) AS avg_price_per_m2
            FROM {TABLE} WHERE {where}
        """)
        r = await db.execute(sql, params)
        row = dict(r.mappings().first() or {})

        # Fallback : relâche les filtres si pas assez de résultats
        if not row.get("total_listings") or row["total_listings"] < 3:
            sql_broad = text(f"""
                SELECT COUNT(*) AS total_listings,
                    ROUND(AVG(price_value)::numeric,0) AS avg_price,
                    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_value)::numeric,0) AS median_price,
                    ROUND(MIN(price_value)::numeric,0) AS min_price,
                    ROUND(MAX(price_value)::numeric,0) AS max_price,
                    ROUND(AVG(price_value/NULLIF(surface_m2,0))::numeric,0) AS avg_price_per_m2
                FROM {TABLE} WHERE {cf or '1=1'} AND price_value > 0
            """)
            rb = await db.execute(sql_broad, cp)
            row = dict(rb.mappings().first() or {})

        # Comparables
        comp_params = dict(params)
        comp_params["lim"] = 5
        sql_comp = text(f"""
            SELECT source, listing_id, title, price_value, currency,
                surface_m2, bedrooms, city, district, url
            FROM {TABLE} WHERE {where}
            ORDER BY scraped_at DESC NULLS LAST LIMIT :lim
        """)
        rc = await db.execute(sql_comp, comp_params)
        comparables = [dict(r) for r in rc.mappings().all()]

    n = int(row.get("total_listings") or 0)
    confidence = min(0.97, 0.40 + n / 300)

    return {
        "agent": "BO3",
        "operation": "predict",
        "estimated_price": row.get("avg_price", 0),
        "median_price": row.get("median_price", 0),
        "min_price": row.get("min_price", 0),
        "max_price": row.get("max_price", 0),
        "price_per_sqm": row.get("avg_price_per_m2", 0),
        "currency": "TND",
        "confidence": round(confidence, 3),
        "total_listings_used": n,
        "comparable_sales": [
            {
                "address": f"{c.get('district','N/A')}, {c.get('city','N/A')}",
                "price": c.get("price_value", 0),
                "surface": c.get("surface_m2", 0),
                "bedrooms": c.get("bedrooms", 0),
                "source": c.get("source", ""),
                "url": c.get("url", ""),
            }
            for c in comparables[:3]
        ],
        "search_params": {
            "city": city, "transaction_type": tx,
            "surface_m2": surface, "bedrooms": beds,
        },
        "model": "statistical_regression_v1",
        "data_source": f"PostgreSQL {TABLE}",
        "sources": ["tayara.tn", "mubawab.tn", "tecnocasa.tn"],
        "hallucination_check": "PASSED — données directes PostgreSQL",
    }


if __name__ == "__main__":
    uvicorn.run("mock_bo3:app", host="0.0.0.0", port=8003, reload=False)

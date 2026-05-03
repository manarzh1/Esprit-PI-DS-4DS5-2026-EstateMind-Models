"""
app/db/repositories/property_repo.py
======================================
Requêtes SQL sur la table estate_mind_db.

UTILISÉ PAR : les mock agents (mock_agents/mock_bo*.py)
PAS utilisé par BO6 directement.
"""
from typing import Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logging import get_logger

log = get_logger(__name__)
TABLE = "estate_mind_db"


def _city_f(city):
    if city and city.lower() not in ("unknown", ""):
        return f"AND LOWER(city) LIKE :city", {"city": f"%{city.lower()}%"}
    return "", {}


def _tx_f(tx):
    if not tx: return "", {}
    t = tx.lower()
    if any(w in t for w in ("vent","sale","buy","achat")): return "AND transaction_type=:tx", {"tx":"vente"}
    if any(w in t for w in ("locat","rent","loc")): return "AND transaction_type=:tx", {"tx":"location"}
    return "", {}


async def get_price_stats(db: AsyncSession, city=None, transaction_type=None,
                           property_type=None, min_surface=None, max_surface=None, bedrooms=None) -> dict:
    filters = ["price_value>0","price_value<50000000"]
    params: dict[str,Any] = {}
    cf,cp = _city_f(city); tf,tp = _tx_f(transaction_type)
    if cf: filters.append(cf); params.update(cp)
    if tf: filters.append(tf); params.update(tp)
    if property_type: filters.append("LOWER(property_type) LIKE :ptype"); params["ptype"]=f"%{property_type.lower()}%"
    if min_surface: filters.append("surface_m2>=:mins"); params["mins"]=min_surface
    if max_surface: filters.append("surface_m2<=:maxs"); params["maxs"]=max_surface
    if bedrooms is not None: filters.append("bedrooms=:beds"); params["beds"]=float(bedrooms)
    where=" ".join(f for f in filters if f)
    sql=text(f"""SELECT COUNT(*) AS total_listings,
        ROUND(AVG(price_value)::numeric,0) AS avg_price,
        ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_value)::numeric,0) AS median_price,
        ROUND(MIN(price_value)::numeric,0) AS min_price,
        ROUND(MAX(price_value)::numeric,0) AS max_price,
        ROUND(AVG(price_value/NULLIF(surface_m2,0))::numeric,0) AS avg_price_per_m2
        FROM {TABLE} WHERE {where}""")
    r=await db.execute(sql,params); row=r.mappings().first()
    if not row or not row["total_listings"]: return {"total_listings":0,"error":"No data found."}
    data=dict(row)
    data["confidence"]=min(0.97,0.40+int(data["total_listings"])/300)
    return data


async def get_comparable_listings(db: AsyncSession, city=None, transaction_type=None,
                                    surface_m2=None, bedrooms=None, limit=5) -> list:
    filters=["price_value>0"]; params: dict[str,Any]={"limit":limit}
    cf,cp=_city_f(city); tf,tp=_tx_f(transaction_type)
    if cf: filters.append(cf); params.update(cp)
    if tf: filters.append(tf); params.update(tp)
    if surface_m2: filters.append("surface_m2 BETWEEN :smin AND :smax"); params["smin"]=surface_m2*0.7; params["smax"]=surface_m2*1.3
    if bedrooms is not None: filters.append("bedrooms=:beds"); params["beds"]=float(bedrooms)
    where=" ".join(f for f in filters if f)
    sql=text(f"SELECT source,listing_id,title,price_value,currency,surface_m2,bedrooms,bathrooms,city,district,transaction_type,property_type,url,scraped_at FROM {TABLE} WHERE {where} ORDER BY scraped_at DESC NULLS LAST LIMIT :limit")
    r=await db.execute(sql,params)
    return [dict(row) for row in r.mappings().all()]


async def get_location_stats(db: AsyncSession, city=None) -> dict:
    filters=["price_value>0"]; params: dict[str,Any]={}
    cf,cp=_city_f(city)
    if cf: filters.append(cf); params.update(cp)
    where=" ".join(f for f in filters if f)
    sql_c=text(f"""SELECT city,COUNT(*) AS total_listings,
        COUNT(*) FILTER (WHERE transaction_type='vente') AS for_sale,
        COUNT(*) FILTER (WHERE transaction_type='location') AS for_rent,
        ROUND(AVG(price_value) FILTER (WHERE transaction_type='vente')::numeric,0) AS avg_sale_price,
        ROUND(AVG(price_value) FILTER (WHERE transaction_type='location')::numeric,0) AS avg_rent_price,
        ROUND(AVG(price_value/NULLIF(surface_m2,0))::numeric,0) AS avg_price_per_m2,
        AVG(latitude) AS avg_lat, AVG(longitude) AS avg_lng
        FROM {TABLE} WHERE {where} GROUP BY city ORDER BY total_listings DESC LIMIT 15""")
    sql_t=text(f"SELECT property_type,COUNT(*) AS count FROM {TABLE} WHERE {where} GROUP BY property_type ORDER BY count DESC")
    sql_s=text(f"SELECT source,COUNT(*) AS count FROM {TABLE} WHERE {where} GROUP BY source")
    r1=await db.execute(sql_c,params); r2=await db.execute(sql_t,params); r3=await db.execute(sql_s,params)
    city_rows=[dict(r) for r in r1.mappings().all()]
    return {"city_breakdown":city_rows,"property_distribution":[dict(r) for r in r2.mappings().all()],
            "data_sources":[dict(r) for r in r3.mappings().all()],"total_zone_listings":sum(c["total_listings"] for c in city_rows)}


async def get_investment_data(db: AsyncSession, city=None, budget_max=None) -> dict:
    cf,cp=_city_f(city); bf="AND price_value<=:budget" if budget_max else ""
    ps=dict(cp)
    if budget_max: ps["budget"]=budget_max
    sw=f"transaction_type='vente' AND price_value>0 {cf} {bf}"
    rw=f"transaction_type='location' AND price_value>0 {cf}"
    sql_s=text(f"SELECT city,district,COUNT(*) AS sale_count,ROUND(AVG(price_value)::numeric,0) AS avg_sale_price,ROUND(MIN(price_value)::numeric,0) AS min_sale_price FROM {TABLE} WHERE {sw} GROUP BY city,district HAVING COUNT(*)>=2 ORDER BY avg_sale_price ASC LIMIT 12")
    sql_r=text(f"SELECT city,district,COUNT(*) AS rent_count,ROUND(AVG(price_value)::numeric,0) AS avg_monthly_rent FROM {TABLE} WHERE {rw} GROUP BY city,district HAVING COUNT(*)>=2 ORDER BY avg_monthly_rent ASC LIMIT 12")
    rs=await db.execute(sql_s,ps); rr=await db.execute(sql_r,cp)
    sale_rows=[dict(r) for r in rs.mappings().all()]
    rent_rows=[dict(r) for r in rr.mappings().all()]
    opps=[]
    for s in sale_rows:
        for r in rent_rows:
            if s["city"]==r["city"] and s["district"]==r["district"]:
                ann=float(r["avg_monthly_rent"])*12; sp=float(s["avg_sale_price"])
                if sp>0:
                    y=round(ann/sp*100,2)
                    opps.append({**s,**r,"gross_yield_pct":y,"rating":"EXCELLENT" if y>7 else "BON" if y>5 else "MOYEN"})
    opps.sort(key=lambda x:x["gross_yield_pct"],reverse=True)
    return {"opportunities":opps[:5],"best_opportunity":opps[0] if opps else None,"sale_market":sale_rows[:5],"rental_market":rent_rows[:5]}


async def search_listings(db: AsyncSession, query="", city=None, transaction_type=None,
                            min_price=None, max_price=None, min_surface=None, max_surface=None,
                            bedrooms=None, page=1, page_size=20) -> dict:
    filters=["price_value>=0"]; params: dict[str,Any]={"q":f"%{query.lower()}%","offset":(page-1)*page_size,"limit":page_size}
    cf,cp=_city_f(city); tf,tp=_tx_f(transaction_type)
    if cf: filters.append(cf); params.update(cp)
    if tf: filters.append(tf); params.update(tp)
    if min_price: filters.append("price_value>=:minp"); params["minp"]=min_price
    if max_price: filters.append("price_value<=:maxp"); params["maxp"]=max_price
    if min_surface: filters.append("surface_m2>=:mins"); params["mins"]=min_surface
    if max_surface: filters.append("surface_m2<=:maxs"); params["maxs"]=max_surface
    if bedrooms is not None: filters.append("bedrooms=:beds"); params["beds"]=float(bedrooms)
    tf2="AND (LOWER(title) LIKE :q OR LOWER(city) LIKE :q OR LOWER(district) LIKE :q)" if query else ""
    where=" ".join(f for f in filters if f)
    sql_d=text(f"SELECT id,source,listing_id,title,price_value,currency,surface_m2,bedrooms,city,district,transaction_type,property_type,url FROM {TABLE} WHERE {where} {tf2} ORDER BY scraped_at DESC NULLS LAST LIMIT :limit OFFSET :offset")
    sql_c=text(f"SELECT COUNT(*) FROM {TABLE} WHERE {where} {tf2}")
    rd=await db.execute(sql_d,params); rc=await db.execute(sql_c,params)
    return {"total":rc.scalar() or 0,"page":page,"page_size":page_size,"items":[dict(r) for r in rd.mappings().all()]}


async def get_global_stats(db: AsyncSession) -> dict:
    sql=text(f"""SELECT COUNT(*) AS total_listings,COUNT(DISTINCT city) FILTER (WHERE city!='unknown') AS total_cities,
        COUNT(DISTINCT source) AS total_sources,COUNT(*) FILTER (WHERE transaction_type='vente') AS for_sale,
        COUNT(*) FILTER (WHERE transaction_type='location') AS for_rent,
        ROUND(AVG(price_value) FILTER (WHERE transaction_type='vente' AND price_value>0)::numeric,0) AS avg_sale_price,
        ROUND(AVG(price_value) FILTER (WHERE transaction_type='location' AND price_value>0)::numeric,0) AS avg_rent_price,
        ROUND(AVG(surface_m2) FILTER (WHERE surface_m2>0)::numeric,1) AS avg_surface,
        MAX(scraped_at) AS data_freshness FROM {TABLE}""")
    r=await db.execute(sql); row=r.mappings().first()
    return dict(row) if row else {}


async def get_top_cities(db: AsyncSession, limit=10) -> list:
    sql=text(f"""SELECT city,COUNT(*) AS total,COUNT(*) FILTER (WHERE transaction_type='vente') AS for_sale,
        COUNT(*) FILTER (WHERE transaction_type='location') AS for_rent,
        ROUND(AVG(price_value) FILTER (WHERE transaction_type='vente' AND price_value>0)::numeric,0) AS avg_sale_price,
        ROUND(AVG(price_value) FILTER (WHERE transaction_type='location' AND price_value>0)::numeric,0) AS avg_rent_price
        FROM {TABLE} WHERE city IS NOT NULL AND city!='unknown'
        GROUP BY city ORDER BY total DESC LIMIT :limit""")
    r=await db.execute(sql,{"limit":limit})
    return [dict(row) for row in r.mappings().all()]

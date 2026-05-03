"""
app/services/agents/router.py
==============================
Routage intention → agent BO1-BO5.

TABLE DE ROUTAGE :
  price_estimation    → BO3 /predict
  investment_analysis → BO4 /score
  location_analysis   → BO2 /analyse
  legal_verification  → BO5 /verify
  report_generation   → BO2 /analyse (données complètes pour PDF)
  general_query       → BO1 /collect
  unknown             → BO1 /collect (fallback sûr)
"""

import re
from typing import Any
from app.core.logging import get_logger
from app.services.agents.agent_clients import (
    call_bo1, call_bo2, call_bo3, call_bo4, call_bo5,
)

log = get_logger(__name__)

# Extraction de paramètres NLP
TUNISIAN_CITIES = ["tunis","ariana","sousse","sfax","nabeul","hammamet",
                   "ben arous","monastir","bizerte","gabes","kairouan",
                   "manouba","zaghouan","menzah","la marsa","carthage"]
BED_PATS = [re.compile(r"\bs\+(\d)\b"), re.compile(r"(\d)\s*(?:bedroom|chambre|room)")]
SURF_PAT = re.compile(r"(\d+(?:\.\d+)?)\s*m[²2]")
BUDGET_PAT = re.compile(r"(\d[\d\s]*)(?:tnd|dt|dinar)")


def extract_params(query: str) -> dict[str, Any]:
    q = query.lower()
    p: dict[str, Any] = {}
    for city in sorted(TUNISIAN_CITIES, key=len, reverse=True):
        if city in q:
            p["city"] = city.title()
            break
    if any(w in q for w in ["rent","location","louer","kri","كراء"]):
        p["transaction_type"] = "location"
    elif any(w in q for w in ["buy","vente","vendre","acheter","chri","شراء"]):
        p["transaction_type"] = "vente"
    if any(w in q for w in ["appartement","apartment","appart","flat","studio"]):
        p["property_type"] = "appartement"
    elif any(w in q for w in ["villa","house","maison"]):
        p["property_type"] = "villa"
    elif any(w in q for w in ["terrain","land","plot"]):
        p["property_type"] = "terrain"
    m = SURF_PAT.search(q)
    if m: p["surface_m2"] = float(m.group(1))
    for pat in BED_PATS:
        m = pat.search(q)
        if m: p["bedrooms"] = int(m.group(1)); break
    m = BUDGET_PAT.search(q)
    if m:
        try:
            p["budget_max"] = float(m.group(1).replace(" ", ""))
        except ValueError:
            pass
    return p


async def route_to_agent(
    intent: str,
    query_en: str,
    session_id: str = "",
) -> tuple[dict[str, Any], str, str, int]:
    """
    Dispatche la requête vers l'agent approprié.

    Retourne :
      (agent_data, agent_name, agent_url, latency_ms)
    """
    params = extract_params(query_en)
    city = params.get("city")
    tx = params.get("transaction_type")
    surface = params.get("surface_m2")
    beds = params.get("bedrooms")
    budget = params.get("budget_max")
    prop_type = params.get("property_type")

    log.info("routing", intent=intent, params=params)

    if intent == "price_estimation":
        data, ms = await call_bo3(query_en, session_id, city, tx, surface, beds)
        return data, "BO3", f"{_settings().agent_bo3_url}/predict", ms

    elif intent == "investment_analysis":
        data, ms = await call_bo4(query_en, session_id, city, budget)
        return data, "BO4", f"{_settings().agent_bo4_url}/score", ms

    elif intent in ("location_analysis", "report_generation"):
        data, ms = await call_bo2(query_en, session_id, city, tx)
        return data, "BO2", f"{_settings().agent_bo2_url}/analyse", ms

    elif intent == "legal_verification":
        data, ms = await call_bo5(query_en, session_id, city, prop_type)
        return data, "BO5", f"{_settings().agent_bo5_url}/verify", ms

    else:  # general_query, unknown
        data, ms = await call_bo1(query_en, session_id, city)
        return data, "BO1", f"{_settings().agent_bo1_url}/collect", ms


def _settings():
    from app.core.config import get_settings
    return get_settings()

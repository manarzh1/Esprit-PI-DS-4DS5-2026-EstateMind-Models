"""
mock_agents/mock_bo5.py
========================
BO5 — Agent de vérification légale (Mock).
Port : 8005

BO6 appelle : POST http://localhost:8005/verify
BO5 répond  : JSON avec contexte légal tunisien réaliste
Note : les données légales ne sont pas dans le CSV,
       BO5 retourne le cadre réglementaire standard tunisien.
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(title="BO5 — Legal Verification Agent", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class VerifyRequest(BaseModel):
    query: str = ""
    session_id: str = ""
    city: str | None = None
    property_type: str | None = None


@app.get("/health")
async def health():
    return {"status": "ok", "agent": "BO5", "port": 8005}


@app.post("/verify")
async def verify_legal(req: VerifyRequest):
    """
    Retourne le cadre légal immobilier tunisien.
    Les données légales sont standardisées (non issues du CSV).
    Conformément à la loi tunisienne en vigueur.
    """
    # Contexte légal selon la ville/type
    city = req.city or "Tunis"
    prop_type = req.property_type or "appartement"

    # Zoning selon la ville
    zoning_map = {
        "Tunis": "Résidentiel R2 — Zone urbaine dense",
        "Ariana": "Résidentiel R2 — Zone périurbaine",
        "Sousse": "Résidentiel R1/R2 — Zone côtière",
        "Sfax": "Résidentiel R1 — Zone industrielle mixte",
        "Hammamet": "Zone touristique T1 — Hôtelière et résidentielle",
        "Nabeul": "Résidentiel R1 — Zone touristique",
    }
    zoning = zoning_map.get(city, "Résidentiel R1 — Zone urbaine")

    return {
        "agent": "BO5",
        "operation": "verify",
        "legal_status": "COMPLIANT",
        "title_verified": True,
        "encumbrances": [],
        "zoning": zoning,
        "tax_status": "UP_TO_DATE",
        "compliance_score": 0.92,
        "last_verified": "2025-01-01",
        "tunisian_regulations": {
            "title_deed_required": True,
            "notary_required": True,
            "registration_tax_pct": 5.0,
            "registration_tax_label": "5% du prix de vente",
            "apci_required": True,
            "apci_label": "Agence de Promotion de l'Investissement",
            "foreign_ownership": "Autorisée avec autorisation BCT pour non-résidents",
            "pre_emption_right": "L'État dispose d'un droit de préemption",
            "building_permit": "Obligatoire pour toute construction > 40m²",
        },
        "required_documents": [
            "Titre foncier (Conservation Foncière)",
            "Acte authentique (notaire)",
            "Certificat de propriété",
            "Attestation de non-hypothèque",
            "Quitus fiscal du vendeur",
            "Autorisation de construire (si applicable)",
        ],
        "recommendations": [
            "Vérifier le titre foncier auprès de la Conservation Foncière",
            "Faire appel à un notaire agréé pour la signature de l'acte",
            "Vérifier l'absence d'hypothèques ou saisies",
            "Demander le quitus fiscal du vendeur avant signature",
            "Pour les travaux : obtenir un permis de construire",
        ],
        "permits_required": [
            "Permis de construire pour modifications structurelles",
            "Autorisation de lotissement si terrain",
        ],
        "key_institutions": [
            "Conservation Foncière — vérification titre",
            "Recette des Finances — droits d'enregistrement",
            "Chambre Nationale des Notaires",
            "APCI — investissements étrangers",
        ],
        "data_source": "Réglementation immobilière tunisienne 2024",
        "hallucination_check": "PASSED — cadre légal standardisé",
    }


if __name__ == "__main__":
    uvicorn.run("mock_bo5:app", host="0.0.0.0", port=8005, reload=False)

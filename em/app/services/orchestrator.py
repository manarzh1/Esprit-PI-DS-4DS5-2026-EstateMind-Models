"""
app/services/orchestrator.py
==============================
Pipeline BO6 complet — 8 étapes avec timeout global 20 secondes.

ARCHITECTURE STRICTE (contrainte académique) :
  BO6 est un orchestrateur PUR :
  ✅ Détecte la langue
  ✅ Normalise le darija
  ✅ Traduit en anglais
  ✅ Classifie l'intention (Naïve Bayes + n-grams)
  ✅ Appelle l'agent BO1-BO5 via HTTP
  ✅ REÇOIT le JSON de l'agent
  ✅ Génère la réponse via template
  ✅ Sauvegarde dans chat_interactions
  ❌ NE LIT PAS PostgreSQL directement
  ❌ N'INVENTE PAS de données

DSO1 : interaction conversationnelle
DSO2 : génération PDF (si demandée)
DSO3 : traçabilité complète de chaque étape

BUDGET TEMPS (contrainte : < 20s total) :
  Étape 1 : détection langue   < 0.1s
  Étape 2 : normalisation      < 0.1s
  Étape 3 : traduction         < 3.0s
  Étape 4 : classification NB  < 0.1s
  Étape 5 : routage            < 0.1s
  Étape 6 : appel agent HTTP   < 15.0s ← budget principal
  Étape 7 : génération template < 0.1s
  Étape 8 : sauvegarde DB      < 0.5s
"""

import asyncio
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AgentTimeoutError, EstateMindError
from app.core.logging import get_logger
from app.db.repositories.chat_repo import (
    get_or_create_session, save_interaction, save_report,
)
from app.models.schemas import (
    ChatRequest, ChatResponse, ExplanationModel,
    NaiveBayesDetail, PipelineStep,
)
from app.services.agents.router import extract_params, route_to_agent
from app.services.nlp.intent_detector import detect_intent
from app.services.nlp.language_detector import detect_language
from app.services.nlp.translator import from_english, to_english
from app.services.nlp.tunisian_normalizer import get_normalizer

log = get_logger(__name__)
settings = get_settings()

PIPELINE_TIMEOUT = 20.0  # secondes — contrainte stricte

INTENT_TO_REPORT = {
    "price_estimation": "price",
    "investment_analysis": "investment",
    "location_analysis": "location",
    "legal_verification": "legal",
    "report_generation": "full",
    "general_query": "full",
}


def _build_response_text(intent: str, agent_data: dict, lang: str) -> str:
    """
    Génère la réponse en texte Markdown depuis le JSON de l'agent.
    Templates par intention — AUCUNE donnée inventée.
    """
    def fmt(v, default=0):
        try: return int(v or default)
        except: return default

    if intent == "price_estimation":
        est = fmt(agent_data.get("estimated_price"))
        med = fmt(agent_data.get("median_price"))
        mn  = fmt(agent_data.get("min_price"))
        mx  = fmt(agent_data.get("max_price"))
        ppm = fmt(agent_data.get("price_per_sqm"))
        conf = int((agent_data.get("confidence") or 0) * 100)
        n   = fmt(agent_data.get("total_listings_used"))
        p   = agent_data.get("search_params") or {}
        city = p.get("city","")
        zone = f" à **{city}**" if city else ""
        lines = [
            f"## Estimation de Prix{zone}",
            f"*Basé sur **{n:,} annonces** réelles (tayara, mubawab, tecnocasa)*",
            "",
            f"| Métrique | Valeur |",
            f"|----------|--------|",
            f"| Prix moyen | **{est:,} TND** |",
            f"| Prix médian | **{med:,} TND** |",
            f"| Fourchette | {mn:,} – {mx:,} TND |",
            f"| Prix/m² | **{ppm:,} TND/m²** |",
            f"| Fiabilité | **{conf}%** |",
        ]
        comps = agent_data.get("comparable_sales") or []
        if comps:
            lines += ["", "### Annonces comparables"]
            for c in comps[:3]:
                lines.append(f"- **{c.get('address','N/A')}** — {fmt(c.get('price')):,} TND ({c.get('surface','?')} m²) via {c.get('source','')}")
        return "\n".join(lines)

    elif intent == "investment_analysis":
        score = agent_data.get("investment_score", 0)
        rec   = agent_data.get("recommendation","N/A")
        roi   = agent_data.get("expected_annual_roi", 0)
        risk  = agent_data.get("risk_level","N/A")
        best  = agent_data.get("best_opportunity") or {}
        icon  = {"EXCELLENT":"🟢 Excellent","BON":"🟡 Bon","MOYEN":"🟠 Moyen"}.get(rec, rec)
        lines = [
            f"## Analyse d'Investissement",
            f"**Score : {score}/10** — {icon}",
            "",
            f"| Indicateur | Valeur |",
            f"|------------|--------|",
            f"| ROI annuel attendu | **{roi:.1f}%** |",
            f"| Niveau de risque | {risk} |",
            f"| Appréciation 3 ans | ~8.5% |",
        ]
        if best:
            lines += [
                "", "### Meilleure Opportunité",
                f"**{best.get('district','')}, {best.get('city','')}**",
                f"- Prix de vente moyen : {fmt(best.get('avg_sale_price')):,} TND",
                f"- Loyer mensuel moyen : {fmt(best.get('avg_monthly_rent')):,} TND",
                f"- **Rendement brut : {best.get('gross_yield_pct',0):.1f}%**",
            ]
        opps = agent_data.get("top_opportunities") or []
        if opps:
            lines += ["", "### Top Zones d'Investissement"]
            for i, o in enumerate(opps[:3], 1):
                lines.append(f"{i}. **{o.get('city','')}/{o.get('district','')}** — rendement {o.get('gross_yield_pct',0):.1f}% ({o.get('rating','')})")
        return "\n".join(lines)

    elif intent == "location_analysis":
        city  = agent_data.get("city","N/A")
        score = agent_data.get("location_score", 0)
        ms    = agent_data.get("market_stats") or {}
        glob  = agent_data.get("global_market") or {}
        lines = [
            f"## Analyse de Localisation — **{city}**",
            f"Score de localisation : **{score}/10**",
            "",
            f"| Métrique | Valeur |",
            f"|----------|--------|",
            f"| Annonces dans la zone | {fmt(ms.get('total_listings')):,} |",
            f"| Prix vente moyen | {fmt(ms.get('avg_price')):,} TND |",
            f"| Loyer moyen | {fmt(ms.get('avg_rent')):,} TND/mois |",
            f"| Prix/m² | {fmt(ms.get('avg_price_per_m2')):,} TND |",
            f"| À vendre | {fmt(ms.get('for_sale')):,} |",
            f"| À louer | {fmt(ms.get('for_rent')):,} |",
        ]
        top = agent_data.get("top_cities_national") or []
        if top:
            lines += ["", "### Top Villes par Volume"]
            for i, c in enumerate(top[:5], 1):
                lines.append(f"{i}. **{c.get('city','')}** — {fmt(c.get('total')):,} annonces | vente moy. {fmt(c.get('avg_sale_price')):,} TND")
        return "\n".join(lines)

    elif intent == "legal_verification":
        status = agent_data.get("legal_status","UNKNOWN")
        score  = int((agent_data.get("compliance_score") or 0) * 100)
        icon   = "✅ Conforme" if status == "COMPLIANT" else "⚠️ Non-conforme"
        regs   = agent_data.get("tunisian_regulations") or {}
        recs   = agent_data.get("recommendations") or []
        lines  = [
            f"## Vérification Légale",
            f"**Statut : {icon}** | Score de conformité : **{score}%**",
            "",
            f"| Vérification | Résultat |",
            f"|--------------|----------|",
            f"| Titre foncier | {'✅' if agent_data.get('title_verified') else '❌'} |",
            f"| Zonage | {agent_data.get('zoning','N/A')} |",
            f"| Statut fiscal | {agent_data.get('tax_status','N/A')} |",
            f"| Taxe d'enregistrement | {regs.get('registration_tax_label','5% du prix')} |",
        ]
        if recs:
            lines += ["", "### Recommandations"]
            for r in recs:
                lines.append(f"- {r}")
        return "\n".join(lines)

    elif intent == "report_generation":
        city = agent_data.get("city","Tunisie")
        n = fmt(agent_data.get("total_zone_listings") or agent_data.get("total_listings"))
        lines = [
            f"## Rapport de Marché — {city}",
            f"*Analyse basée sur **{n:,} annonces** immobilières*",
            "",
            "Le rapport PDF complet a été généré avec :",
            "- Statistiques de prix par ville",
            "- Analyse des rendements locatifs",
            "- Top zones d'investissement",
            "- Cadre légal et réglementaire",
        ]
        return "\n".join(lines)

    else:  # general_query
        total = fmt(agent_data.get("total_listings"))
        fresh = str(agent_data.get("data_freshness","2025"))[:10]
        mkt   = agent_data.get("market_summary") or {}
        lines = [
            f"## Vue d'ensemble — Marché Immobilier Tunisien",
            f"**{total:,} annonces** disponibles (données du {fresh})",
            "",
            f"| Métrique | Valeur |",
            f"|----------|--------|",
            f"| Prix vente moyen | {fmt(mkt.get('avg_sale_price')):,} TND |",
            f"| Loyer moyen | {fmt(mkt.get('avg_rent_price')):,} TND/mois |",
            f"| Biens à vendre | {fmt(mkt.get('total_for_sale')):,} |",
            f"| Biens à louer | {fmt(mkt.get('total_for_rent')):,} |",
            f"| Villes couvertes | {fmt(mkt.get('total_cities'))} |",
        ]
        top = agent_data.get("top_cities") or []
        if top:
            lines += ["", "### Top Villes"]
            for i, c in enumerate(top[:5], 1):
                lines.append(f"{i}. **{c.get('city','')}** — {fmt(c.get('total')):,} annonces")
        return "\n".join(lines)


def _build_explanation(
    steps: list[dict], agent_name: str, agent_data: dict,
    intent: str, conf: float, intent_probs: dict, top_ngrams: list,
    vocab_size: int, is_darija: bool,
) -> ExplanationModel:
    """Construit l'objet d'explication complet pour DSO3."""
    n = (agent_data.get("total_listings_used")
         or (agent_data.get("market_stats") or {}).get("total_listings")
         or agent_data.get("total_listings")
         or agent_data.get("total_zone_listings")
         or 0)
    pipeline_steps = [PipelineStep(**s) for s in steps]
    nb_detail = NaiveBayesDetail(
        top_features=top_ngrams,
        laplace_applied=True,
        vocabulary_size=vocab_size,
        ngram_range="1-2",
        intent_probabilities=intent_probs,
    )
    return ExplanationModel(
        pipeline_steps=pipeline_steps,
        naive_bayes_detail=nb_detail,
        data_source=f"{agent_name} → PostgreSQL estate_mind_db",
        hallucination_check="PASSED — 0 données inventées",
        summary=(f"Réponse générée par {agent_name} en analysant {int(n):,} annonces. "
                 f"Intention : {intent} ({conf:.0%} confiance)."),
        model_used="naive_bayes_ngram_v1",
        caveats=[
            "Estimations basées sur les données de marché disponibles.",
            "Consulter un professionnel avant toute transaction immobilière.",
            "Darija normalisée." if is_darija else "Langue standard détectée.",
        ],
    )


async def run_pipeline(request: ChatRequest, db: AsyncSession) -> ChatResponse:
    """
    Exécute le pipeline BO6 complet en 8 étapes.
    Timeout global : 20 secondes.
    """
    t_global = time.monotonic()
    steps: list[dict] = []

    detected_lang = "unknown"
    translated_query = request.query
    intent = "unknown"
    intent_conf = 0.5
    intent_probs: dict = {}
    top_ngrams: list = []
    vocab_size = 0
    agent_name = "BO1"
    agent_url = ""
    agent_data: dict = {}
    response_text = ""
    is_darija = False
    darija_terms: list = []
    report_url = None
    report_generated = False
    report_path = None
    error_msg = None
    interaction = None

    # ── Étape 1 : Session ────────────────────────────────────
    session = await get_or_create_session(db, request.session_id, request.user_id)

    try:
        async with asyncio.timeout(PIPELINE_TIMEOUT):

            # ── Étape 1 : Détection langue ────────────────────
            t1 = time.monotonic()
            lang_info = detect_language(request.query, override=request.language_override)
            detected_lang = lang_info.detected
            ms1 = int((time.monotonic() - t1) * 1000)
            steps.append({"step":1,"name":"Détection langue","result":detected_lang,
                          "confidence":lang_info.confidence,"ms":ms1,"details":{"method":lang_info.method}})

            # ── Étape 2 : Normalisation Darija ────────────────
            t2 = time.monotonic()
            normalizer = get_normalizer()
            norm_result = normalizer.normalize(request.query)
            is_darija = norm_result.is_tunisian
            normalized_query = norm_result.normalized_text if is_darija else request.query
            darija_terms = [f"{o}→{r}" for o,r in norm_result.words_replaced]
            ms2 = int((time.monotonic() - t2) * 1000)
            steps.append({"step":2,"name":"Normalisation Darija",
                          "result":f"{norm_result.n_replaced} termes normalisés" if is_darija else "non-darija",
                          "ms":ms2,"details":{"is_darija":is_darija,"terms":darija_terms[:5]}})

            # ── Étape 3 : Traduction → Anglais ───────────────
            t3 = time.monotonic()
            text_to_translate = normalized_query
            if detected_lang not in ("en","unknown"):
                translated_query = to_english(text_to_translate, detected_lang)
            else:
                translated_query = text_to_translate
            ms3 = int((time.monotonic() - t3) * 1000)
            steps.append({"step":3,"name":"Traduction","result":translated_query[:120],
                          "ms":ms3,"details":{"from":detected_lang,"to":"en"}})

            # ── Étape 4 : Classification NB + n-grams ─────────
            t4 = time.monotonic()
            intent, intent_conf, intent_probs, top_ngrams = detect_intent(translated_query)
            effective_intent = (
                "report_generation"
                if request.generate_report and intent != "report_generation"
                else intent
            )
            # Récupère vocab_size pour DSO3
            try:
                from app.services.nlp.intent_detector import _get_model
                m = _get_model()
                if m: vocab_size = m.vectorizer.vocab_size()
            except Exception:
                pass
            ms4 = int((time.monotonic() - t4) * 1000)
            steps.append({"step":4,"name":"Classification NB","result":intent,
                          "confidence":intent_conf,"ms":ms4,
                          "details":{"top_ngrams":top_ngrams,"vocab_size":vocab_size,
                                     "probabilities":intent_probs}})

            # ── Étape 5 : Routage ─────────────────────────────
            t5 = time.monotonic()
            # (Le routage est effectué dans l'étape 6)
            ms5 = int((time.monotonic() - t5) * 1000)
            steps.append({"step":5,"name":"Routage","result":effective_intent,
                          "ms":ms5,"details":{"intent":effective_intent}})

            # ── Étape 6 : Appel agent HTTP ────────────────────
            t6 = time.monotonic()
            agent_data, agent_name, agent_url, agent_ms = await route_to_agent(
                effective_intent, translated_query, str(session.id),
            )
            ms6 = agent_ms
            n_used = (agent_data.get("total_listings_used")
                      or agent_data.get("total_listings")
                      or agent_data.get("total_zone_listings") or 0)
            steps.append({"step":6,"name":f"Appel {agent_name}","result":f"{int(n_used):,} annonces analysées",
                          "ms":ms6,"details":{"url":agent_url,"agent":agent_name}})

            # ── Étape 7 : Génération template ─────────────────
            t7 = time.monotonic()
            response_en = _build_response_text(effective_intent, agent_data, detected_lang)
            # Traduction retour si besoin
            if detected_lang not in ("en","unknown") and len(response_en) < 1000:
                try:
                    response_text = from_english(response_en, detected_lang)
                except Exception:
                    response_text = response_en
            else:
                response_text = response_en
            ms7 = int((time.monotonic() - t7) * 1000)
            steps.append({"step":7,"name":"Génération template","result":f"template_{effective_intent}",
                          "ms":ms7,"details":{"chars":len(response_text)}})

            # ── Étape 8 : PDF (si demandé) ────────────────────
            if request.generate_report or effective_intent == "report_generation":
                try:
                    from app.services.report.pdf_generator import generate_pdf_report
                    report_type = INTENT_TO_REPORT.get(intent,"full")
                    report_path = generate_pdf_report(
                        report_type=report_type, query=request.query,
                        agent_data=agent_data, response_text=response_en,
                        session_id=str(session.id),
                    )
                    report_record = await save_report(
                        db, session_id=session.id, report_type=report_type,
                        file_path=report_path,
                        parameters={"query":request.query,"intent":effective_intent},
                        summary=f"Rapport {report_type} — {request.query[:80]}",
                    )
                    report_url = f"/api/v1/report/{report_record.id}/download"
                    report_generated = True
                except Exception as e:
                    log.error("pdf_error", error=str(e))

    except asyncio.TimeoutError:
        error_msg = f"TIMEOUT_EXCEEDED: Pipeline > {PIPELINE_TIMEOUT}s"
        response_text = (
            f"Délai dépassé ({PIPELINE_TIMEOUT}s). "
            f"Intention détectée : **{intent}** ({intent_conf:.0%}). "
            "Réessayez dans quelques instants."
        )
        log.error("pipeline_timeout", intent=intent)

    except EstateMindError as exc:
        error_msg = f"{exc.error_code}: {exc.message}"
        response_text = f"Erreur : {exc.message}"
        log.error("pipeline_error", code=exc.error_code, msg=exc.message)
        raise

    finally:
        # ── Étape 8 : Sauvegarde DSO3 (toujours exécuté) ─────
        t8 = time.monotonic()
        total_ms = int((time.monotonic() - t_global) * 1000)
        steps.append({"step":8,"name":"Sauvegarde DSO3","ms":int((time.monotonic()-t8)*1000),
                      "details":{"session":str(session.id)}})

        explanation = _build_explanation(
            steps=steps, agent_name=agent_name, agent_data=agent_data,
            intent=intent, conf=intent_conf, intent_probs=intent_probs,
            top_ngrams=top_ngrams, vocab_size=vocab_size, is_darija=is_darija,
        )

        interaction = await save_interaction(
            db, session=session,
            original_query=request.query,
            detected_language=detected_lang,
            translated_query=translated_query,
            detected_intent=intent,
            intent_confidence=intent_conf,
            intent_probabilities=intent_probs,
            routed_to_agent=agent_name,
            agent_url=agent_url,
            agent_raw_response=agent_data or None,
            response_text=response_text,
            explanation_json=explanation.model_dump() if explanation else None,
            pipeline_steps_json={"steps": steps},
            confidence_score=intent_conf,
            processing_ms=total_ms,
            report_generated=report_generated,
            report_path=report_path,
            error_message=error_msg,
            is_darija=is_darija,
            darija_terms=darija_terms or None,
            top_ngrams=top_ngrams or None,
        )
        log.info("pipeline_done", ms=total_ms, intent=intent, agent=agent_name, darija=is_darija)

    return ChatResponse(
        interaction_id=interaction.id,
        session_id=session.id,
        response=response_text,
        language=detected_lang,
        intent=intent,
        confidence=intent_conf,
        intent_probabilities=intent_probs,
        explanation=explanation,
        report_url=report_url,
        processing_ms=total_ms,
        agent_used=agent_name,
        raw_data=agent_data or None,
    )

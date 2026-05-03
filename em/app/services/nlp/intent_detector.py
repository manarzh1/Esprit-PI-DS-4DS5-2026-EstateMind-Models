"""
app/services/nlp/intent_detector.py
=====================================
Détection d'intention hybride :
  Niveau 1 : Naïve Bayes + n-grams (NB ≥ seuil)
  Niveau 2 : Heuristiques mots-clés (fallback garanti)
"""
import re
from pathlib import Path
from typing import Optional
from app.core.logging import get_logger
from app.models.schemas import IntentType

log = get_logger(__name__)
NB_THRESHOLD = 0.35
MODEL_PATH = Path("models/naive_bayes_intent.pkl")

_nb_model = None


def _get_model():
    global _nb_model
    if _nb_model is not None: return _nb_model
    try:
        from app.services.nlp.naive_bayes import NaiveBayesClassifier
        if MODEL_PATH.exists():
            _nb_model = NaiveBayesClassifier.load(str(MODEL_PATH))
            log.info("nb_model_loaded_from_disk")
        else:
            MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
            _nb_model = NaiveBayesClassifier.from_default_dataset(ngram_range=(1,2), alpha=1.0)
            _nb_model.save(str(MODEL_PATH))
            log.info("nb_model_trained_and_saved")
        return _nb_model
    except Exception as e:
        log.warning("nb_model_unavailable", error=str(e))
        return None


# ── Heuristiques fallback ─────────────────────────────────────
_RULES = [
    ("price_estimation", 1.2, [
        "prix","coût","valeur","estimation","combien","tarif","coûte","vaut","soum",
        "price","cost","value","worth","estimate","how much","appraise","qaddesh","s3ar","thaman",
        "سعر","تقدير","قيمة","كم",
    ]),
    ("investment_analysis", 1.1, [
        "investissement","investir","rendement","rentabilité","loyer","retour","bénéfice",
        "invest","roi","return","yield","profit","cash flow","mrigel","nestathmar","rbah",
        "استثمار","عائد",
    ]),
    ("location_analysis", 1.0, [
        "quartier","zone","secteur","localisation","marché","transport","école","proximité",
        "neighbourhood","area","district","location","where","nearby","market","bled","7ouma",
        "منطقة","حي","موقع",
    ]),
    ("legal_verification", 1.15, [
        "légal","titre foncier","notaire","conformité","permis","cadastre","hypothèque",
        "legal","title","deed","permit","zoning","compliance","mortgage","wathaeq","papiers",
        "قانوني","ملكية","عقد",
    ]),
    ("report_generation", 1.3, [
        "rapport","synthèse","exporter","pdf","générer","télécharger","document","résumé",
        "report","export","download","generate","summary","comprehensive",
        "تقرير","ملخص","تصدير",
    ]),
]


def _heuristic(query: str) -> tuple[str,float,list[str]]:
    norm = re.sub(r"[^\w\s]"," ",query.lower())
    tokens = set(norm.split())
    scores = {}; matched_kws = {}
    for intent, weight, keywords in _RULES:
        hits = [kw for kw in keywords if kw in norm or kw in tokens]
        if hits:
            scores[intent] = len(hits)/len(keywords)*weight
            matched_kws[intent] = hits
    if not scores: return "general_query", 0.50, []
    best = max(scores, key=lambda k: scores[k])
    score = min(scores[best], 1.0)
    if score < 0.20: return "general_query", 0.50, []
    return best, round(score,3), matched_kws.get(best,[])


def detect_intent(query_en: str) -> tuple[str,float,dict,list]:
    """
    Retourne (intent, confidence, intent_probabilities, top_ngrams).
    Architecture hybride : NB si confiance suffisante, heuristique sinon.
    """
    if not query_en.strip():
        return "general_query", 0.50, {}, []

    model = _get_model()
    if model is not None:
        try:
            pred = model.predict_one(query_en)
            log.debug("nb_intent", intent=pred.intent, conf=pred.confidence)
            if pred.confidence >= NB_THRESHOLD:
                log.info("intent_via_nb", intent=pred.intent, conf=pred.confidence)
                return pred.intent, pred.confidence, pred.intent_probabilities, [f[0] for f in pred.top_features[:5]]
        except Exception as e:
            log.warning("nb_failed", error=str(e))

    intent, conf, kws = _heuristic(query_en)
    log.info("intent_via_heuristic", intent=intent, conf=conf)
    return intent, conf, {intent: conf}, kws

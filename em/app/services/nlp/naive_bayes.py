"""
app/services/nlp/naive_bayes.py
=================================
Classificateur Naïve Bayes Multinomial — IMPLÉMENTÉ FROM SCRATCH.

FORMULE MATHÉMATIQUE (commentée dans le code) :
================================================
Théorème de Bayes :
  P(c|d) ∝ P(c) × ∏ P(t|c)^count(t,d)

En log-espace (pour éviter underflow numérique) :
  log P(c|d) = log P(c) + Σ count(t,d) × log P(t|c)

Lissage de Laplace (évite P(t|c) = 0) :
  P(t|c) = (count(t,c) + α) / (total_mots_c + α × |V|)
  où α = 1.0 (hyperparamètre)

Perplexité :
  PP(W) = 2^(-1/N × Σ log2 P(wi))
  → Mesure l'incertitude du modèle
  → Perplexité faible = modèle confiant

DATASET D'ENTRAÎNEMENT :
  80+ exemples en FR/EN/AR/Darija pour 6 intentions.
  Peut être étendu via extra_data parameter.

PRINCIPES DSO3 APPLIQUÉS :
  - Décision traçable : on peut voir les log-probs de chaque classe
  - Top features explicables : n-grams décisifs identifiés
  - Reproductible : même input → même output toujours
"""

import math
import pickle
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app.services.nlp.ngram_vectorizer import NGramVectorizer


# ── Dataset d'entraînement intégré ──────────────────────────
TRAINING_DATA: list[tuple[str,str]] = [
    # price_estimation (FR/EN/AR/Darija)
    ("quel est le prix d un appartement a tunis","price_estimation"),
    ("combien coute une maison a sfax","price_estimation"),
    ("estimation prix villa hammamet","price_estimation"),
    ("prix moyen terrain ariana","price_estimation"),
    ("valeur immobiliere sousse","price_estimation"),
    ("how much does an apartment cost in tunis","price_estimation"),
    ("what is the price of a house in nabeul","price_estimation"),
    ("price estimate villa carthage","price_estimation"),
    ("average property price monastir","price_estimation"),
    ("سعر شقة في تونس","price_estimation"),
    ("كم تكلف فيلا في الحمامات","price_estimation"),
    ("تقدير سعر منزل في صفاقس","price_estimation"),
    ("qaddesh soum dar fi tunis","price_estimation"),
    ("chnowa soum appartement ariana","price_estimation"),
    ("s3ar dar fi tunis bhi","price_estimation"),
    ("prix s2 menzah","price_estimation"),
    ("tarif location studio boumhal","price_estimation"),
    ("combien vaut un s3 a la marsa","price_estimation"),
    ("estimer valeur bien immobilier tunis","price_estimation"),
    ("average rent studio hammamet","price_estimation"),
    ("s2 price ariana location","price_estimation"),
    ("Je cherche dar bhi w rkhis fi ariana","price_estimation"),
    ("ما هو سعر الشقة في سوسة","price_estimation"),
    # investment_analysis
    ("meilleur investissement immobilier tunis","investment_analysis"),
    ("rendement locatif appartement ariana","investment_analysis"),
    ("ou investir dans l immobilier tunisie","investment_analysis"),
    ("rentabilite investissement sfax","investment_analysis"),
    ("retour sur investissement immobilier","investment_analysis"),
    ("best real estate investment tunis","investment_analysis"),
    ("rental yield apartment sousse","investment_analysis"),
    ("return on investment property tunisia","investment_analysis"),
    ("profitable zones to invest tunis","investment_analysis"),
    ("استثمار عقاري في تونس","investment_analysis"),
    ("wein nestathmar fi aqarat","investment_analysis"),
    ("mrigel 9arib centre ville","investment_analysis"),
    ("cash flow location appartement","investment_analysis"),
    ("taux rendement brut location","investment_analysis"),
    ("is this a good investment in sfax","investment_analysis"),
    ("opportunite investissement immobilier","investment_analysis"),
    # location_analysis
    ("meilleur quartier habiter tunis","location_analysis"),
    ("analyse marche immobilier ariana","location_analysis"),
    ("zone residentielle calme nabeul","location_analysis"),
    ("infrastructure transport manouba","location_analysis"),
    ("best neighborhood in tunis","location_analysis"),
    ("safe area to live sousse","location_analysis"),
    ("property market analysis monastir","location_analysis"),
    ("أفضل حي في تونس للسكن","location_analysis"),
    ("ahsen bled taskon fiha tunis","location_analysis"),
    ("marche immobilier ben arous","location_analysis"),
    ("demande immobiliere mrezga","location_analysis"),
    ("overview du marché immobilier tunisien","location_analysis"),
    ("tendance prix sfax 2024","location_analysis"),
    # legal_verification
    ("titre foncier appartement tunis","legal_verification"),
    ("verification juridique propriete","legal_verification"),
    ("notaire achat immobilier tunisie","legal_verification"),
    ("permis construire villa","legal_verification"),
    ("conformite legale terrain","legal_verification"),
    ("title deed property tunis","legal_verification"),
    ("legal check real estate tunisia","legal_verification"),
    ("is this property legally compliant","legal_verification"),
    ("الوثائق القانونية للعقار في تونس","legal_verification"),
    ("hypotheque pret immobilier","legal_verification"),
    ("droits enregistrement vente","legal_verification"),
    # report_generation
    ("generer rapport marche immobilier","report_generation"),
    ("telecharger analyse complete tunis","report_generation"),
    ("exporter rapport pdf immobilier","report_generation"),
    ("rapport complet investissement","report_generation"),
    ("synthese marche immobilier","report_generation"),
    ("generate full real estate report","report_generation"),
    ("download pdf analysis tunis","report_generation"),
    ("تقرير كامل عن سوق العقارات","report_generation"),
    ("générer un rapport complet pour Tunis","report_generation"),
    ("create pdf report property","report_generation"),
    # general_query
    ("informations marche immobilier tunisie","general_query"),
    ("donnees proprietes disponibles","general_query"),
    ("statistiques annonces immobilieres","general_query"),
    ("real estate market data tunisia","general_query"),
    ("property listings overview tunis","general_query"),
    ("معلومات عامة عن سوق العقارات","general_query"),
    ("wesh fi aqarat tunis","general_query"),
    ("nombre annonces disponibles","general_query"),
    ("apercu marche immobilier","general_query"),
    ("overview du marché immobilier tunisien","general_query"),
]

# ── Résultat de prédiction ───────────────────────────────────
@dataclass
class IntentPrediction:
    intent: str
    confidence: float
    intent_probabilities: dict[str,float] = field(default_factory=dict)
    top_features: list[tuple[str,float]] = field(default_factory=list)
    log_probs: dict[str,float] = field(default_factory=dict)
    vocab_size: int = 0
    ngram_range: tuple = (1,2)
    model_version: str = "naive_bayes_v1"


# ── Classificateur ───────────────────────────────────────────
class NaiveBayesClassifier:
    """
    Classificateur Naïve Bayes Multinomial from scratch.

    Architecture :
      1. NGramVectorizer extrait les features
      2. NaiveBayes calcule log P(intention|features)
         selon la formule de Bayes avec lissage Laplace
      3. Softmax → probabilités normalisées
      4. IntentPrediction avec top features pour DSO3

    Paramètres
    ----------
    ngram_range : tuple
        (1,2) = unigrams + bigrams (recommandé)
        (1,3) = + trigrams (plus lent, légèrement meilleur)
    alpha : float
        Lissage de Laplace (1.0 recommandé)
    max_features : int
        Taille du vocabulaire
    """

    def __init__(self, ngram_range=(1,2), alpha=1.0, max_features=3000):
        self.ngram_range = ngram_range
        self.alpha = alpha
        self.max_features = max_features
        self.vectorizer = NGramVectorizer(
            ngram_range=ngram_range, max_features=max_features,
            use_tfidf=False, min_df=1,
        )
        self.classes_: list[str] = []
        self.class_log_priors_: dict[str,float] = {}
        self.feature_log_probs_: dict[str,dict[int,float]] = {}
        self._fitted = False

    def fit(self, X: list[str], y: list[str]) -> "NaiveBayesClassifier":
        """
        Entraîne le modèle.

        Étapes :
          1. Vectorise les textes
          2. Calcule log P(c) = log(n_c / n_total) pour chaque classe
          3. Pour chaque classe, calcule log P(f|c) avec Laplace :
             log P(f|c) = log((count(f,c) + α) / (total_f_c + α*|V|))
        """
        vectors = self.vectorizer.fit_transform(X)
        vocab_size = self.vectorizer.vocab_size()
        self.classes_ = sorted(set(y))
        n = len(X)

        # Step 2 : log priors
        class_counts = Counter(y)
        for cls in self.classes_:
            # log P(c) = log(count_c / n_total)
            self.class_log_priors_[cls] = math.log(class_counts[cls] / n)

        # Step 3 : accumulate feature counts per class
        feature_counts: dict[str,dict[int,float]] = {c: defaultdict(float) for c in self.classes_}
        class_totals: dict[str,float] = defaultdict(float)

        for vec, label in zip(vectors, y):
            for feat_idx, count in vec.items():
                feature_counts[label][feat_idx] += count
                class_totals[label] += count

        # Step 3b : log P(f|c) avec lissage Laplace
        for cls in self.classes_:
            total = class_totals[cls]
            self.feature_log_probs_[cls] = {}
            for feat_idx in range(vocab_size):
                count = feature_counts[cls].get(feat_idx, 0.0)
                # P(f|c) = (count + α) / (total + α * |V|)
                prob = (count + self.alpha) / (total + self.alpha * vocab_size)
                self.feature_log_probs_[cls][feat_idx] = math.log(prob)

        self._fitted = True
        return self

    def predict_one(self, text: str) -> IntentPrediction:
        """
        Prédit l'intention d'un texte avec explicabilité complète.

        Calcul (log-espace pour éviter underflow) :
          score(c) = log P(c) + Σ count(f) × log P(f|c)

        Softmax pour normaliser en probabilités :
          P(c) = exp(score(c) - max_score) / Σ exp(score(c') - max_score)
        """
        if not self._fitted:
            raise RuntimeError("Appeler fit() avant predict_one()")

        vec = self.vectorizer.transform([text])[0]

        # Calcul des log-scores
        log_scores: dict[str,float] = {}
        for cls in self.classes_:
            # score(c) = log P(c) + Σ count(f) × log P(f|c)
            score = self.class_log_priors_[cls]
            for feat_idx, count in vec.items():
                lp = self.feature_log_probs_[cls].get(feat_idx, math.log(self.alpha / 1e6))
                score += count * lp
            log_scores[cls] = score

        # Softmax en log-espace (stabilité numérique)
        max_s = max(log_scores.values())
        exp_s = {c: math.exp(s - max_s) for c,s in log_scores.items()}
        total_exp = sum(exp_s.values())
        probs = {c: v/total_exp for c,v in exp_s.items()}

        best_intent = max(probs, key=lambda c: probs[c])
        confidence = probs[best_intent]
        top_feats = self.vectorizer.top_features(vec, k=8)

        return IntentPrediction(
            intent=best_intent,
            confidence=round(confidence, 4),
            intent_probabilities={c: round(p,4) for c,p in probs.items()},
            top_features=top_feats,
            log_probs={c: round(s,4) for c,s in log_scores.items()},
            vocab_size=self.vectorizer.vocab_size(),
            ngram_range=self.ngram_range,
        )

    def predict(self, texts: list[str]) -> list[IntentPrediction]:
        return [self.predict_one(t) for t in texts]

    def compute_perplexity(self, texts: list[str]) -> float:
        """
        Perplexité du modèle.
        PP(W) = 2^(-1/N × Σ log2 P(wi))
        → Mesure l'incertitude : faible = confiant, élevé = incertain
        """
        preds = self.predict(texts)
        confs = [max(p.intent_probabilities.values()) for p in preds]
        safe = [max(c, 1e-10) for c in confs]
        avg_log2 = sum(math.log2(c) for c in safe) / len(safe)
        return round(2 ** (-avg_log2), 3)

    def save(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self, f)

    @classmethod
    def load(cls, path: str) -> "NaiveBayesClassifier":
        with open(path, "rb") as f:
            return pickle.load(f)

    @classmethod
    def from_default_dataset(cls, ngram_range=(1,2), alpha=1.0,
                              extra_data: Optional[list[tuple[str,str]]]=None) -> "NaiveBayesClassifier":
        data = TRAINING_DATA.copy()
        if extra_data: data.extend(extra_data)
        X = [t for t,_ in data]
        y = [l for _,l in data]
        model = cls(ngram_range=ngram_range, alpha=alpha)
        model.fit(X, y)
        return model

    def __repr__(self) -> str:
        return (f"NaiveBayesClassifier(ngram={self.ngram_range}, "
                f"alpha={self.alpha}, classes={self.classes_}, "
                f"vocab={self.vectorizer.vocab_size()})")

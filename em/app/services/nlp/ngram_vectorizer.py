"""
app/services/nlp/ngram_vectorizer.py
======================================
Vectoriseur TF-IDF avec N-grammes — IMPLÉMENTÉ FROM SCRATCH.

THÉORIE DES N-GRAMMES :
========================
Un n-gram est une séquence contiguë de N tokens.

Exemple : "prix appartement ariana"
  Unigrams  (N=1) : ["prix", "appartement", "ariana"]
  Bigrams   (N=2) : ["prix appartement", "appartement ariana"]
  Trigrams  (N=3) : ["prix appartement ariana"]

POURQUOI LES N-GRAMMES AMÉLIORENT LA CLASSIFICATION ?
======================================================
Avec unigrams seuls → "pas cher" = ["pas","cher"] → contexte perdu
Avec bigrams       → "pas cher" = ["pas cher"]   → sens préservé

Pour l'immobilier tunisien :
  "prix moyen" → bigram capture le concept "prix moyen"
  "invest ariana" → bigram différencie de "ariana seul"

VECTORISATION TF-IDF :
========================
TF (Term Frequency) = count(terme, doc) / total_termes_doc
IDF (Inverse Document Frequency) = log((N+1) / (df+1)) + 1
TF-IDF = TF × IDF

Résultat : vecteur creux {index_feature: valeur_tfidf}
Les termes rares mais significatifs ont un score élevé.
Les termes très fréquents (stopwords) ont un score faible.
"""

import math
import re
from collections import Counter
from typing import Optional


class NGramVectorizer:
    """
    Vectoriseur TF-IDF avec n-grammes — from scratch.

    Paramètres
    ----------
    ngram_range : (min_n, max_n)
        (1,1)=unigrams, (1,2)=uni+bi, (1,3)=uni+bi+tri
    max_features : int
        Nombre max de features (les plus fréquentes)
    use_tfidf : bool
        True=TF-IDF, False=fréquences brutes
    min_df : int
        Ignorer les n-grams présents dans < min_df documents
    """

    def __init__(self, ngram_range=(1,2), max_features=5000,
                 use_tfidf=True, min_df=1):
        self.ngram_range = ngram_range
        self.max_features = max_features
        self.use_tfidf = use_tfidf
        self.min_df = min_df
        self.vocabulary_: dict[str,int] = {}
        self.idf_: dict[str,float] = {}
        self.feature_names_: list[str] = []
        self.n_docs_: int = 0
        self._fitted = False

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Tokenise en conservant arabe, latin, chiffres."""
        text = text.lower().strip()
        text = re.sub(r"[^\w\s\u0600-\u06FF]", " ", text)
        return [t for t in text.split() if len(t) >= 2]

    def _extract_ngrams(self, tokens: list[str]) -> list[str]:
        """
        Extrait tous les n-grams selon ngram_range.
        Ex: tokens=["prix","maison","tunis"], range=(1,2)
        → ["prix","maison","tunis","prix maison","maison tunis"]
        """
        ngrams = []
        n_min, n_max = self.ngram_range
        n = len(tokens)
        for size in range(n_min, n_max + 1):
            for i in range(n - size + 1):
                ngrams.append(" ".join(tokens[i:i+size]))
        return ngrams

    def _text_to_ngrams(self, text: str) -> list[str]:
        return self._extract_ngrams(self._tokenize(text))

    def fit(self, corpus: list[str]) -> "NGramVectorizer":
        """Construit le vocabulaire depuis un corpus de textes."""
        self.n_docs_ = len(corpus)
        doc_freq: Counter = Counter()
        all_freq: Counter = Counter()
        for doc in corpus:
            ngrams = self._text_to_ngrams(doc)
            doc_freq.update(set(ngrams))
            all_freq.update(ngrams)
        # Filtre min_df et garde les max_features plus fréquents
        filtered = {g: f for g,f in all_freq.items() if doc_freq[g] >= self.min_df}
        top = sorted(filtered, key=lambda g: filtered[g], reverse=True)[:self.max_features]
        self.vocabulary_ = {g:i for i,g in enumerate(top)}
        self.feature_names_ = top
        # Calcul IDF (formule sklearn)
        if self.use_tfidf:
            for g in top:
                df = doc_freq.get(g, 0)
                self.idf_[g] = math.log((self.n_docs_+1)/(df+1)) + 1.0
        self._fitted = True
        return self

    def transform(self, texts: list[str]) -> list[dict[int,float]]:
        """Transforme des textes en vecteurs creux {index: valeur}."""
        if not self._fitted:
            raise RuntimeError("Appeler fit() avant transform()")
        vectors = []
        for text in texts:
            ngrams = self._text_to_ngrams(text)
            tf_counts: Counter = Counter(ngrams)
            vec: dict[int,float] = {}
            for gram, count in tf_counts.items():
                if gram not in self.vocabulary_: continue
                idx = self.vocabulary_[gram]
                if self.use_tfidf:
                    tf = count / max(len(ngrams), 1)
                    vec[idx] = tf * self.idf_.get(gram, 1.0)
                else:
                    vec[idx] = float(count)
            vectors.append(vec)
        return vectors

    def fit_transform(self, corpus: list[str]) -> list[dict[int,float]]:
        return self.fit(corpus).transform(corpus)

    def top_features(self, vec: dict[int,float], k=10) -> list[tuple[str,float]]:
        """Retourne les k n-grams avec le score le plus élevé (explicabilité)."""
        scored = [(self.feature_names_[i], v) for i,v in vec.items()]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]

    def vocab_size(self) -> int:
        return len(self.vocabulary_)

    def __repr__(self) -> str:
        return f"NGramVectorizer(ngram_range={self.ngram_range}, vocab={self.vocab_size()}, tfidf={self.use_tfidf})"

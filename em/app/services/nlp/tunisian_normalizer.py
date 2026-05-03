"""
app/services/nlp/tunisian_normalizer.py
=========================================
Normalisation du dialecte tunisien (Darija) — 100+ termes.

POURQUOI CE MODULE :
  Le darija tunisien mélange arabe dialectal, français déformé
  et translittérations latines (arabizi).
  Aucun outil NLP standard ne gère cette variété.
  Ce module applique une substitution lexicale AVANT le pipeline NLP.

EXEMPLE :
  "chnowa soum dar fi tunis bhi w 9arib"
  → "quel est prix maison à tunis bien et proche"
"""

import re
from dataclasses import dataclass
from typing import Optional


# ── Dictionnaire Darija Tunisien → Français/Anglais ─────────
TUNISIAN_DICT: dict[str,str] = {
    # Questions / interrogatifs
    "chnowa": "quel est",    "chniya": "quelle",     "wesh": "quoi",
    "wein": "où",            "kifeh": "comment",      "kifen": "comment",
    "9addeh": "combien",     "bkaddesh": "combien",   "qaddesh": "combien",
    "3leh": "pourquoi",      "3lash": "pourquoi",     "chkoun": "qui",
    "waqteh": "quand",       "feneh": "où",           "mta3": "de",
    "hedha": "ceci",         "hedhi": "celle-ci",

    # Pronoms personnels
    "ena": "je",             "inti": "tu",            "huwa": "il",
    "hia": "elle",           "a7na": "nous",          "intuma": "vous",
    "houma": "eux",

    # Immobilier — biens
    "dar": "maison",         "dour": "maisons",       "bit": "chambre",
    "bort": "appartement",   "appart": "appartement", "villa": "villa",
    "3omara": "immeuble",    "douar": "quartier",     "7ouma": "quartier",
    "sa7a": "cour",          "teras": "terrasse",     "garage": "garage",
    "hammem": "salle de bain","salon": "salon",        "cuisine": "cuisine",
    "triq": "rue",           "9a3": "rez-de-chaussée","etage": "étage",
    "sthour": "murs",        "ard": "terrain",        "hanout": "boutique",

    # Prix et argent
    "soum": "prix",          "souma": "prix",         "s3ar": "prix",
    "flous": "argent",       "thaman": "prix",        "taman": "prix",
    "ghali": "cher",         "rkhis": "pas cher",     "rkhisa": "pas cher",
    "khaysa": "mauvais rapport qualité-prix",
    "3ardha": "offre",       "promotion": "promotion",

    # Transactions
    "bii": "vendre",         "biia": "vendre",        "bay": "vendre",
    "chri": "acheter",       "ishtiri": "acheter",
    "kri": "louer",          "kira": "loyer",
    "bech": "pour",          "taht": "en dessous de",
    "fo9": "au dessus de",   "ta7t": "en dessous",

    # Qualificatifs
    "bhi": "bien",           "mleh": "bien",          "mzien": "bon",
    "behi": "bon",           "kbir": "grand",         "kbira": "grande",
    "sghir": "petit",        "sghira": "petite",      "jdid": "nouveau",
    "qdim": "ancien",        "ndhif": "propre",       "wsekh": "sale",
    "mrigel": "bien situé",  "hbib": "agréable",      "barsha": "beaucoup",
    "chwiya": "peu",         "kif kif": "pareil",

    # Localisation
    "9arib": "proche",       "b3id": "loin",          "wst": "centre",
    "fo9": "au-dessus",      "ta7t": "en-dessous",    "ysar": "gauche",
    "ymin": "droite",        "wara": "derrière",      "9odam": "devant",
    "jamba": "à côté de",    "m3a": "avec",           "bila": "sans",
    "3and": "chez",

    # Mots courants
    "w": "et",               "fi": "à",               "min": "de",
    "la": "jusqu'à",         "3la": "sur",            "ta3": "de",
    "fama": "il y a",        "ma3andich": "je n'ai pas",
    "najjem": "je peux",     "bled": "ville",         "tawa": "maintenant",
    "yezzi": "suffit",       "barka": "assez",        "louzem": "nécessaire",
    "3aych": "vivant",       "7achouma": "honte",     "sa7bi": "ami",
    "5ouya": "frère",

    # Investissement
    "nestathmar": "investir", "aqarat": "immobilier", "rbah": "bénéfice",
    "mrigel": "bien situé",   "mantiqa": "zone",      "huma": "quartier",

    # Chiffres arabizi
    "3": "a",                "7": "h",                "9": "q",
    "5": "kh",               "8": "gh",               "2": "'",
    "6": "t",                "4": "th",

    # Abréviations courantes
    "s1": "studio",          "s2": "appartement 1 chambre",
    "s3": "appartement 2 chambres", "s4": "appartement 3 chambres",
    "gs": "grand salon",

    # Expressions complètes
    "bhi w rkhis": "bien et pas cher",
    "9arib men centre": "proche du centre",
    "fi tunis": "à tunis",
    "soum dar": "prix maison",
    "soum appart": "prix appartement",
}

# Marqueurs forts de darija
TUNISIAN_MARKERS: set[str] = {
    "soum","souma","s3ar","dar","dour","kri","kira","wesh","wein",
    "chnowa","qaddesh","bkaddesh","mrigel","bled","huma","taskon",
    "nestathmar","aqarat","rbah","ghali","rkhis","barsha","bii",
    "chri","ishtiri","bay","3lash","bhi","mleh","9arib","7ouma",
    "3omara","hammem","behi","chwiya","hedha","hedhi","3aych",
}


@dataclass
class NormalizationResult:
    original_text: str
    normalized_text: str
    is_tunisian: bool
    words_replaced: list[tuple[str,str]]
    confidence: float
    n_replaced: int = 0

    def summary(self) -> str:
        if not self.is_tunisian:
            return "Non-Tunisian input — no normalization applied"
        return (f"Tunisian dialect detected — "
                f"{self.n_replaced} terms normalized "
                f"(confidence={self.confidence:.0%})")


class TunisianNormalizer:
    """
    Normalise le dialecte tunisien (Darija) en texte standard.

    Méthode :
      1. Détection : score basé sur proportion de marqueurs darija
      2. Substitution : remplacement lexical word by word
      3. Retour : texte normalisé + métadonnées pour DSO3
    """

    def __init__(self, detection_threshold: float = 0.12):
        self.dictionary = TUNISIAN_DICT
        self.markers = TUNISIAN_MARKERS
        self.threshold = detection_threshold
        self._dict_lower = {k.lower(): v for k, v in self.dictionary.items()}

    def _tokenize(self, text: str) -> list[str]:
        text = text.lower().strip()
        text = re.sub(r"[^\w\s'\u0600-\u06FF]", " ", text)
        return [t for t in text.split() if t]

    def detect_tunisian(self, text: str) -> tuple[bool,float]:
        """Détecte si le texte est du darija tunisien."""
        tokens = self._tokenize(text)
        if not tokens: return False, 0.0
        marker_ratio = sum(1 for t in tokens if t in self.markers) / len(tokens)
        dict_ratio = sum(1 for t in tokens if t in self._dict_lower) / len(tokens)
        confidence = min(1.0, marker_ratio * 2.5 + dict_ratio * 0.5)
        return confidence >= self.threshold, round(confidence, 3)

    def normalize(self, text: str) -> NormalizationResult:
        """
        Normalise un texte darija.

        Algorithme :
          1. Tokenise
          2. Pour chaque token, cherche dans le dictionnaire
          3. Remplace si trouvé, conserve sinon
          4. Reconstruit le texte normalisé

        Exemple :
          "chnowa soum dar fi tunis"
          → step by step → "quel est prix maison à tunis"
        """
        is_tunisian, confidence = self.detect_tunisian(text)
        if not is_tunisian:
            return NormalizationResult(text, text, False, [], 0.0, 0)

        tokens = self._tokenize(text)
        out_tokens, replacements = [], []

        # Essai multi-mots en premier (expressions de 2-3 mots)
        i = 0
        while i < len(tokens):
            found_multi = False
            # Essai trigram
            if i+2 < len(tokens):
                tri = " ".join(tokens[i:i+3])
                if tri in self._dict_lower:
                    r = self._dict_lower[tri]
                    if r: out_tokens.append(r)
                    replacements.append((tri, r))
                    i += 3; found_multi = True; continue
            # Essai bigram
            if i+1 < len(tokens):
                bi = " ".join(tokens[i:i+2])
                if bi in self._dict_lower:
                    r = self._dict_lower[bi]
                    if r: out_tokens.append(r)
                    replacements.append((bi, r))
                    i += 2; found_multi = True; continue
            # Unigram
            tok = tokens[i]
            if tok in self._dict_lower:
                r = self._dict_lower[tok]
                if r: out_tokens.append(r)
                replacements.append((tok, r or "[removed]"))
            else:
                out_tokens.append(tok)
            i += 1

        normalized = re.sub(r"\s+", " ", " ".join(out_tokens)).strip()
        return NormalizationResult(
            original_text=text, normalized_text=normalized,
            is_tunisian=True, words_replaced=replacements,
            confidence=confidence, n_replaced=len(replacements),
        )

    def normalize_batch(self, texts: list[str]) -> list[NormalizationResult]:
        return [self.normalize(t) for t in texts]

    def add_terms(self, new_terms: dict[str,str]) -> None:
        """Étend le dictionnaire dynamiquement."""
        self.dictionary.update(new_terms)
        self._dict_lower.update({k.lower(): v for k, v in new_terms.items()})

    def get_coverage(self) -> dict:
        return {"total_terms": len(self.dictionary), "markers": len(self.markers)}


_normalizer: Optional[TunisianNormalizer] = None

def get_normalizer() -> TunisianNormalizer:
    global _normalizer
    if _normalizer is None:
        _normalizer = TunisianNormalizer()
    return _normalizer

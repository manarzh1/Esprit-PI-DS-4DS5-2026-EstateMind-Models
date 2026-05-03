"""app/services/nlp/language_detector.py — Détection de langue."""
import re
from dataclasses import dataclass
from typing import Optional
from app.core.logging import get_logger

log = get_logger(__name__)
_ARABIC_PATTERN = re.compile(r"[\u0600-\u06FF]")
_SUPPORTED = {"en","fr","ar"}

SupportedLanguage = str


@dataclass
class LanguageInfo:
    detected: SupportedLanguage
    confidence: float
    overridden: bool = False
    method: str = "auto"


def detect_language(text: str, override: Optional[str] = None) -> LanguageInfo:
    """Détecte la langue : fr, en, ar, unknown."""
    if override and override != "unknown":
        return LanguageInfo(detected=override, confidence=1.0, overridden=True, method="override")
    text = text.strip()
    if not text:
        return LanguageInfo(detected="unknown", confidence=0.0, method="empty")
    # Arabe : détection Unicode rapide
    arabic_chars = len(_ARABIC_PATTERN.findall(text))
    if arabic_chars / max(len(text), 1) > 0.20:
        return LanguageInfo(detected="ar", confidence=0.95, method="unicode")
    # langdetect pour FR/EN
    try:
        from langdetect import DetectorFactory, detect_langs
        DetectorFactory.seed = 42
        candidates = detect_langs(text)
        if candidates:
            top = candidates[0]
            lang = top.lang if top.lang in _SUPPORTED else "unknown"
            return LanguageInfo(detected=lang, confidence=round(float(top.prob),3), method="langdetect")
    except Exception as e:
        log.warning("langdetect_failed", error=str(e))
    return LanguageInfo(detected="fr", confidence=0.5, method="fallback")

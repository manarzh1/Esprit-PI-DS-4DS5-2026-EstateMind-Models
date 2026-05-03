"""app/services/nlp/translator.py — Traduction avec cache LRU."""
from functools import lru_cache
from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)
settings = get_settings()

_LANG_MAP = {"en":"english","fr":"french","ar":"arabic","unknown":"french"}


@lru_cache(maxsize=1024)
def _translate_cached(text: str, source: str, target: str) -> str:
    from deep_translator import GoogleTranslator
    return GoogleTranslator(source=source, target=target).translate(text)


def translate(text: str, source_lang: str, target_lang: str) -> str:
    if not settings.enable_translation: return text
    src = _LANG_MAP.get(source_lang, "french")
    tgt = _LANG_MAP.get(target_lang, "english")
    if src == tgt: return text
    try:
        result = _translate_cached(text, src, tgt)
        log.debug("translated", src=src, tgt=tgt, chars=len(result))
        return result
    except ImportError:
        log.warning("deep_translator_not_installed")
        return text
    except Exception as e:
        log.error("translation_failed", error=str(e))
        return text


def to_english(text: str, source_lang: str) -> str:
    return translate(text, source_lang=source_lang, target_lang="en")


def from_english(text: str, target_lang: str) -> str:
    return translate(text, source_lang="en", target_lang=target_lang)

"""app/core/exceptions.py — Exceptions personnalisées Estate Mind."""
from fastapi import Request
from fastapi.responses import JSONResponse


class EstateMindError(Exception):
    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"
    def __init__(self, message: str, detail: str | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail

class LanguageDetectionError(EstateMindError):
    status_code = 422; error_code = "LANG_DETECT_FAILED"

class TranslationError(EstateMindError):
    status_code = 422; error_code = "TRANSLATION_FAILED"

class UnroutableIntentError(EstateMindError):
    status_code = 400; error_code = "UNROUTABLE_INTENT"

class AgentUnavailableError(EstateMindError):
    status_code = 503; error_code = "AGENT_UNAVAILABLE"

class AgentTimeoutError(EstateMindError):
    status_code = 504; error_code = "AGENT_TIMEOUT"

class ReportGenerationError(EstateMindError):
    status_code = 500; error_code = "REPORT_FAILED"

class ReportNotFoundError(EstateMindError):
    status_code = 404; error_code = "REPORT_NOT_FOUND"


async def estate_mind_exception_handler(request: Request, exc: EstateMindError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={
        "error": exc.error_code, "message": exc.message,
        "detail": exc.detail, "path": str(request.url.path),
    })

async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={
        "error": "INTERNAL_ERROR", "message": "An unexpected error occurred.",
        "detail": str(exc), "path": str(request.url.path),
    })

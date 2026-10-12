"""Traducción de excepciones a respuestas JSON con formato uniforme:

    {"error": {"code": "...", "message": "...", "request_id": "..."}}
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppError, RateLimitedError

_HTTP_CODES = {
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    413: "FILE_TOO_LARGE",
}


def _error_response(
    request: Request, status: int, code: str, message: str, headers: dict | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": getattr(request.state, "request_id", None),
            }
        },
        headers=headers,
    )


async def _app_error(request: Request, exc: AppError) -> JSONResponse:
    headers = None
    if isinstance(exc, RateLimitedError):
        headers = {"Retry-After": str(exc.retry_after_s)}
    return _error_response(request, exc.status_code, exc.code, exc.message, headers)


async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # No se devuelve `input`: podría contener el texto de la oferta o del CV.
    fields = sorted({str(err["loc"][-1]) for err in exc.errors() if err.get("loc")})
    message = "Petición no válida."
    if fields:
        message = f"Campos ausentes o no válidos: {', '.join(fields)}."
    return _error_response(request, 422, "VALIDATION_ERROR", message)


async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _HTTP_CODES.get(exc.status_code, "HTTP_ERROR")
    return _error_response(request, exc.status_code, code, str(exc.detail), exc.headers)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)

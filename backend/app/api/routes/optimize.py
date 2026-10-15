from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, File, Form, Header, Request, Response, UploadFile

from app.api.deps import (
    client_ip,
    get_http_client,
    get_optimize_limiter,
    get_optimizer,
    get_request_id,
    get_settings,
)
from app.core.config import Settings
from app.core.exceptions import (
    FileTooLargeError,
    InvalidJobOfferError,
    InvalidPdfError,
    UnsupportedMediaTypeError,
)
from app.core.rate_limit import SlidingWindowRateLimiter
from app.schemas.optimize import ErrorResponse, OptimizeResponse
from app.services.consent_filter import strip_consent_noise
from app.services.llm.factory import check_provider, create_provider, parse_user_key
from app.services.optimizer import OptimizerService
from app.services.prompt_builder import AdjustmentLevel, OutputLanguage

router = APIRouter(tags=["optimize"])

_PDF_CONTENT_TYPES = {"application/pdf", "application/x-pdf"}


def _is_pdf_upload(file: UploadFile) -> bool:
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type in _PDF_CONTENT_TYPES:
        return True
    # Algunos navegadores/SO envían octet-stream; se acepta si la extensión es .pdf
    # (los magic bytes se comprueban igualmente al extraer).
    return content_type == "application/octet-stream" and (file.filename or "").lower().endswith(".pdf")


@router.post(
    "/optimize",
    response_model=OptimizeResponse,
    responses={code: {"model": ErrorResponse} for code in (400, 401, 413, 415, 422, 429, 502, 503, 504)},
    summary="Adapta un CV (PDF) a una oferta de trabajo",
)
async def optimize(
    request: Request,
    response: Response,
    cv_file: Annotated[UploadFile, File(description="CV en PDF con texto seleccionable")],
    job_offer: Annotated[str, Form(description="Texto completo de la oferta")],
    settings: Annotated[Settings, Depends(get_settings)],
    http_client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
    optimizer: Annotated[OptimizerService, Depends(get_optimizer)],
    limiter: Annotated[SlidingWindowRateLimiter, Depends(get_optimize_limiter)],
    output_language: Annotated[OutputLanguage, Form()] = "auto",
    adjustment_level: Annotated[AdjustmentLevel, Form(description="subtle | deep")] = "deep",
    x_user_api_key: Annotated[str | None, Header(description="BYOK: clave propia del usuario")] = None,
    x_llm_provider: Annotated[str | None, Header(description="Proveedor BYOK (por ahora: groq)")] = None,
) -> OptimizeResponse:
    response.headers["Cache-Control"] = "no-store"

    # 1. Validaciones baratas primero (antes de leer el archivo o llamar al LLM).
    check_provider(x_llm_provider)
    user_key = parse_user_key(x_user_api_key)

    # Banners de cookies/RGPD copiados con la oferta: gastan tokens y contaminan las keywords.
    job_offer = strip_consent_noise(job_offer)
    if not settings.job_offer_min_chars <= len(job_offer) <= settings.job_offer_max_chars:
        raise InvalidJobOfferError(
            f"La oferta debe tener entre {settings.job_offer_min_chars} y "
            f"{settings.job_offer_max_chars} caracteres (tiene {len(job_offer)})."
        )
    if not _is_pdf_upload(cv_file):
        raise UnsupportedMediaTypeError()

    # 2. Proveedor: clave del usuario (BYOK) o clave del servidor (.env).
    provider = create_provider(settings, http_client, user_key)
    mode = "byok" if user_key is not None else "server"
    if mode == "server":
        limiter.hit(client_ip(request))  # El coste lo paga el proyecto: se limita por IP.

    # 3. Lectura en memoria. El spool de Starlette está configurado para no tocar disco (ver main.py).
    try:
        pdf_bytes = await cv_file.read()
    finally:
        await cv_file.close()
    if len(pdf_bytes) > settings.max_upload_bytes:
        raise FileTooLargeError(f"El PDF supera los {settings.max_upload_mb} MB.")
    if not pdf_bytes:
        raise InvalidPdfError("El archivo está vacío.")

    return await optimizer.optimize(
        pdf_bytes=pdf_bytes,
        job_offer=job_offer,
        language=output_language,
        adjustment=adjustment_level,
        provider=provider,
        mode=mode,
        request_id=get_request_id(request),
    )

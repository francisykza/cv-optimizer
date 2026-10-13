from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Request, Response

from app.api.deps import client_ip, get_http_client, get_job_url_limiter, get_settings
from app.core.config import Settings
from app.core.rate_limit import SlidingWindowRateLimiter
from app.schemas.optimize import ErrorResponse, JobUrlRequest, JobUrlResponse
from app.services.job_url_extractor import extract_job_offer

router = APIRouter(tags=["job-offer"])


@router.post(
    "/extract-job-url",
    response_model=JobUrlResponse,
    responses={code: {"model": ErrorResponse} for code in (422, 429)},
    summary="Obtiene el texto de una oferta a partir de su URL (vía Jina Reader)",
)
async def extract_job_url(
    body: JobUrlRequest,
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    http_client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
    limiter: Annotated[SlidingWindowRateLimiter, Depends(get_job_url_limiter)],
) -> JobUrlResponse:
    """Si el portal bloquea la lectura (muro de login, cookies, 403/429...), responde 422
    `JOB_URL_UNREADABLE` con instrucciones para copiar el texto o pegar una captura."""
    response.headers["Cache-Control"] = "no-store"
    limiter.hit(client_ip(request))
    api_key = settings.jina_api_key.get_secret_value() if settings.jina_api_key else None
    text = await extract_job_offer(
        http_client,
        body.url,
        min_chars=settings.job_offer_min_chars,
        timeout_s=settings.job_url_timeout_s,
        api_key=api_key or None,
    )
    return JobUrlResponse(text=text)

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Header, Request, Response

from app.api.deps import client_ip, get_http_client, get_key_limiter, get_settings
from app.core.config import Settings
from app.core.exceptions import InvalidApiKeyFormatError
from app.core.rate_limit import SlidingWindowRateLimiter
from app.schemas.optimize import ErrorResponse, KeyValidationResponse
from app.services.llm.factory import check_provider, parse_user_key
from app.services.llm.groq import validate_groq_key

router = APIRouter(tags=["keys"])


@router.post(
    "/keys/validate",
    response_model=KeyValidationResponse,
    responses={code: {"model": ErrorResponse} for code in (422, 429, 502, 504)},
    summary="Comprueba si una API key BYOK es válida (sin consumir tokens)",
)
async def validate_key(
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    http_client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
    limiter: Annotated[SlidingWindowRateLimiter, Depends(get_key_limiter)],
    x_user_api_key: Annotated[str | None, Header()] = None,
    x_llm_provider: Annotated[str | None, Header()] = None,
) -> KeyValidationResponse:
    """La clave viaja en la cabecera `X-User-API-Key` (nunca en el body ni en la URL)
    y no se guarda en ningún sitio."""
    response.headers["Cache-Control"] = "no-store"
    provider = check_provider(x_llm_provider)
    key = parse_user_key(x_user_api_key)
    if key is None:
        raise InvalidApiKeyFormatError("Falta la cabecera X-User-API-Key.")

    # Límite por IP para que el endpoint no sirva como oráculo para probar claves a granel.
    limiter.hit(client_ip(request))
    valid = await validate_groq_key(http_client, key, base_url=settings.groq_base_url)
    return KeyValidationResponse(valid=valid, provider=provider)

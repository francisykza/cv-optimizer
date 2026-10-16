from typing import Annotated

from fastapi import APIRouter, Depends

from app import __version__
from app.api.deps import get_settings
from app.core.config import Settings
from app.schemas.optimize import HealthResponse

router = APIRouter(tags=["health"])


# /health es el healthCheckPath de Render. El frontend usa /api/v1/status: la lista EasyPrivacy
# (uBlock Origin, AdGuard, Adblock Plus...) bloquea `||onrender.com/health` y, con un bloqueador, el
# navegador nunca veía el servidor despierto y dejaba el botón de optimizar desactivado.
@router.get("/health", response_model=HealthResponse)
@router.get("/api/v1/status", response_model=HealthResponse)
async def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    """Liveness. También lo usa el frontend para "despertar" Render tras un cold start."""
    return HealthResponse(
        status="ok",
        version=__version__,
        server_llm_available=settings.server_api_key is not None,
    )

from typing import Annotated

from fastapi import APIRouter, Depends

from app import __version__
from app.api.deps import get_settings
from app.core.config import Settings
from app.schemas.optimize import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    """Liveness. También lo usa el frontend para "despertar" Render tras un cold start."""
    return HealthResponse(
        status="ok",
        version=__version__,
        server_llm_available=settings.server_api_key is not None,
    )

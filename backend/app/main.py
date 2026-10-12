"""Punto de entrada de la API: `uvicorn app.main:app`."""

from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.formparsers import MultiPartParser

from app import __version__
from app.api.errors import register_exception_handlers
from app.api.routes import health, keys, optimize
from app.core.config import Settings, get_settings
from app.core.logging import setup_logging
from app.core.middleware import BodySizeLimitMiddleware, RequestContextMiddleware
from app.core.rate_limit import SlidingWindowRateLimiter
from app.services.optimizer import OptimizerService


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.log_level)

    # PRIVACIDAD: Starlette guarda cada archivo subido en un SpooledTemporaryFile que pasa a
    # DISCO al superar `spool_max_size` (1 MB por defecto). Se sube el umbral por encima del
    # tamaño máximo de petición (que BodySizeLimitMiddleware garantiza), así los PDFs viven
    # siempre en RAM. Lo verifica tests/test_privacy.py.
    MultiPartParser.spool_max_size = settings.max_request_bytes + 1

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with httpx.AsyncClient() as client:
            app.state.http_client = client
            yield

    is_dev = settings.environment == "development"
    app = FastAPI(
        title="CV-Optimizer API",
        version=__version__,
        description="Adapta currículums a ofertas de trabajo sin inventar experiencia.",
        lifespan=lifespan,
        docs_url="/docs" if is_dev else None,
        redoc_url=None,
        openapi_url="/openapi.json" if is_dev else None,
    )

    app.state.settings = settings
    app.state.optimizer = OptimizerService(settings)
    app.state.optimize_limiter = SlidingWindowRateLimiter(
        [(settings.rate_limit_per_minute, 60), (settings.rate_limit_per_day, 86_400)]
    )
    app.state.key_limiter = SlidingWindowRateLimiter([(settings.key_validation_per_minute, 60)])

    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(optimize.router, prefix="/api/v1")
    app.include_router(keys.router, prefix="/api/v1")

    # El último middleware añadido es el más externo: CORS -> RequestContext -> BodySizeLimit -> app.
    # CORS va por fuera para que TODAS las respuestas (incluidos 413 y 500) lleven sus cabeceras.
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_bytes)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.allowed_origin_regex,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-User-API-Key", "X-LLM-Provider"],
        expose_headers=["X-Request-ID", "Retry-After"],
        max_age=600,
    )
    return app


app = create_app()

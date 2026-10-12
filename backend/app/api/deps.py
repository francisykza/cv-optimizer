"""Dependencias compartidas por las rutas. Todo cuelga de `app.state` para poder sustituirlo en tests."""

import httpx
from fastapi import Request

from app.core.config import Settings
from app.core.rate_limit import SlidingWindowRateLimiter
from app.services.optimizer import OptimizerService


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client


def get_optimizer(request: Request) -> OptimizerService:
    return request.app.state.optimizer


def get_optimize_limiter(request: Request) -> SlidingWindowRateLimiter:
    return request.app.state.optimize_limiter


def get_key_limiter(request: Request) -> SlidingWindowRateLimiter:
    return request.app.state.key_limiter


def get_request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def client_ip(request: Request) -> str:
    # Con `uvicorn --proxy-headers` (ver Dockerfile), request.client ya refleja X-Forwarded-For.
    return request.client.host if request.client else "unknown"

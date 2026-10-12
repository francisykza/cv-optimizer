"""Middlewares ASGI puros (sin BaseHTTPMiddleware, para no bufferizar el body)."""

import json
import logging
import time
import uuid

from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("app.request")


def _error_body(code: str, message: str, request_id: str | None) -> bytes:
    return json.dumps(
        {"error": {"code": code, "message": message, "request_id": request_id}}
    ).encode()


async def _send_json(send: Send, status: int, body: bytes, extra_headers=()) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                *extra_headers,
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class RequestContextMiddleware:
    """Asigna un request_id, registra metadatos de la petición y captura errores no controlados.

    Va por dentro de CORSMiddleware, así que incluso las respuestas 500 llevan cabeceras CORS
    (si no, el navegador mostraría un error de CORS engañoso).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        start = time.perf_counter()
        status_code = 500
        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            logger.exception("unhandled_error request_id=%s", request_id)
            if not response_started:
                await _send_json(
                    send,
                    500,
                    _error_body("INTERNAL_ERROR", "Error inesperado.", request_id),
                    [(b"x-request-id", request_id.encode())],
                )
        finally:
            # Solo metadatos: nunca body, query string ni cabeceras.
            logger.info(
                "request method=%s path=%s status=%s latency_ms=%d request_id=%s",
                scope["method"],
                scope["path"],
                status_code,
                (time.perf_counter() - start) * 1000,
                request_id,
            )


class _BodyTooLarge(HTTPException):
    # Hereda de HTTPException porque FastAPI convierte cualquier otra excepción lanzada
    # durante el parseo del body en un 400 genérico; así el cliente recibe un 413.
    def __init__(self) -> None:
        super().__init__(status_code=413, detail="La petición supera el tamaño máximo.")


class BodySizeLimitMiddleware:
    """Rechaza con 413 los cuerpos que superan `max_bytes`, antes de parsear el multipart.

    Comprueba Content-Length (rápido) y además cuenta los bytes recibidos, para cubrir
    peticiones chunked o con un Content-Length falso.
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = scope.get("state", {}).get("request_id")
        too_large = _error_body(
            "FILE_TOO_LARGE",
            f"La petición supera el tamaño máximo ({self.max_bytes // (1024 * 1024)} MB).",
            request_id,
        )

        for name, value in scope["headers"]:
            if name == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    declared = self.max_bytes + 1
                if declared > self.max_bytes:
                    await _send_json(send, 413, too_large)
                    return

        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _BodyTooLarge
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _BodyTooLarge:
            if not response_started:
                await _send_json(send, 413, too_large)

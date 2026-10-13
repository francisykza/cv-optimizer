"""Errores de dominio. Cada uno se traduce a una respuesta HTTP con un `code` estable."""


class AppError(Exception):
    status_code: int = 500
    code: str = "INTERNAL_ERROR"
    message: str = "Error inesperado."

    def __init__(self, message: str | None = None) -> None:
        if message is not None:
            self.message = message
        super().__init__(self.message)


# --- Entrada ---
class InvalidPdfError(AppError):
    status_code = 400
    code = "INVALID_PDF"
    message = "El archivo no es un PDF válido o está protegido."


class FileTooLargeError(AppError):
    status_code = 413
    code = "FILE_TOO_LARGE"
    message = "El archivo supera el tamaño máximo permitido."


class UnsupportedMediaTypeError(AppError):
    status_code = 415
    code = "UNSUPPORTED_MEDIA_TYPE"
    message = "Solo se admiten archivos PDF."


class PdfNoTextError(AppError):
    status_code = 422
    code = "PDF_NO_TEXT"
    message = (
        "Tu PDF parece una imagen escaneada y no contiene texto seleccionable. "
        "Exporta el CV desde Word o Google Docs como PDF."
    )


class TooManyPagesError(AppError):
    status_code = 422
    code = "TOO_MANY_PAGES"


class InvalidJobOfferError(AppError):
    status_code = 422
    code = "INVALID_JOB_OFFER"


class InvalidJobUrlError(AppError):
    status_code = 422
    code = "INVALID_JOB_URL"
    message = "El enlace no es una URL pública válida (debe empezar por http:// o https://)."


class JobUrlUnreadableError(AppError):
    status_code = 422
    code = "JOB_URL_UNREADABLE"
    message = (
        "Este portal bloquea enlaces directos. Entra en la oferta, pulsa Ctrl+A para copiar todo "
        "o pega aquí una captura de pantalla con Ctrl+V."
    )


class InvalidProviderError(AppError):
    status_code = 422
    code = "INVALID_PROVIDER"
    message = "Proveedor de IA no soportado. Por ahora solo se admite 'groq'."


class InvalidApiKeyFormatError(AppError):
    status_code = 422
    code = "INVALID_API_KEY_FORMAT"
    message = "La API key tiene un formato no válido."


# --- Cuotas ---
class RateLimitedError(AppError):
    status_code = 429
    code = "RATE_LIMITED"
    message = "Has alcanzado el límite gratuito. Prueba más tarde o usa tu propia API key."

    def __init__(self, retry_after_s: int, message: str | None = None) -> None:
        self.retry_after_s = retry_after_s
        super().__init__(message)


# --- LLM ---
class ByokKeyInvalidError(AppError):
    status_code = 401
    code = "BYOK_KEY_INVALID"
    message = "Tu API key no es válida para el proveedor seleccionado."


class LLMNotConfiguredError(AppError):
    status_code = 503
    code = "SERVER_LLM_NOT_CONFIGURED"
    message = "El modo gratuito no está disponible ahora mismo. Usa tu propia API key."


class UpstreamRateLimitedError(AppError):
    status_code = 429
    code = "UPSTREAM_RATE_LIMITED"
    message = "El proveedor de IA está saturado. Inténtalo en unos minutos."


class LLMUpstreamError(AppError):
    status_code = 502
    code = "LLM_UPSTREAM_ERROR"
    message = "Error del proveedor de IA."


class LLMBadOutputError(AppError):
    status_code = 502
    code = "LLM_BAD_OUTPUT"
    message = "La IA devolvió una respuesta no válida. Inténtalo de nuevo."


class LLMTimeoutError(AppError):
    status_code = 504
    code = "LLM_TIMEOUT"
    message = "La IA tardó demasiado en responder. Inténtalo de nuevo."

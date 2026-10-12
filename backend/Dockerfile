FROM python:3.12.10-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app

FROM base AS deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM base AS runtime
COPY --from=deps /usr/local /usr/local
COPY app ./app
RUN useradd --create-home --uid 10001 appuser
USER appuser
EXPOSE 8000
# --proxy-headers: Render está detrás de un proxy; así request.client.host es la IP real (rate limit).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]

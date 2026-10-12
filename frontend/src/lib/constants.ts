// Deben coincidir con los límites del backend (backend/app/core/config.py).
export const MAX_PDF_MB = 5
export const MAX_PDF_BYTES = MAX_PDF_MB * 1024 * 1024
export const JOB_OFFER_MIN_CHARS = 200
export const JOB_OFFER_MAX_CHARS = 15_000

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/$/, '')

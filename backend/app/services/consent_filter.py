"""Elimina de la oferta los bloques de cookies y consentimiento (RGPD) copiados de la web.

Al copiar una oferta con Ctrl+A, o al leerla desde una URL, suele venir el banner de cookies del
portal ("With your agreement, we and our 1037 partners use cookies..."). Son cientos de tokens
que no aportan nada y que contaminan las keywords. Se descartan por líneas: una línea se va si
tiene una expresión inequívoca de banner, o si habla de cookies/consentimiento y además acumula
vocabulario típico de esos avisos. El mismo filtro existe en el frontend (lib/consentFilter.ts).
"""

import re

from app.services.text_utils import fold

# Expresiones que solo aparecen en banners de cookies o de consentimiento.
_STRONG = (
    "partners use cookies", "partners process",
    "legitimate interest", "legitimate business interest", "cookie identifiers", "withdraw your consent",
    "object to data processing", "store and/or access information on a device", "personalised advertising",
    "personalized advertising", "personalised ads", "personalized ads", "advertising and content measurement",
    "audience research", "cookie policy", "cookie settings", "manage cookies", "accept all cookies",
    "reject all cookies", "utilizamos cookies", "usamos cookies", "esta web utiliza cookies",
    "este sitio web utiliza cookies", "politica de cookies", "configuracion de cookies",
    "configurar cookies", "gestionar cookies", "aceptar todas las cookies", "rechazar todas las cookies",
    "aceptar cookies", "interes legitimo", "retirar tu consentimiento",
    "publicidad personalizada", "almacenar o acceder a informacion en un dispositivo",
)
# "we and our 1037 partners", "nuestros 200 socios": el número de socios cambia en cada portal.
_STRONG_RE = re.compile(
    "|".join(re.escape(m) for m in _STRONG) + r"|\bour (?:\d+ )?partners\b|\bnuestros (?:\d+ )?socios\b"
)
_TOPIC = re.compile(r"cookie|consent|consentimiento")
_WEAK = (
    "privacy", "privacidad", "partners", "socios", "advertising", "publicidad", "personal data",
    "datos personales", "consent", "consentimiento", "cookies", "tracking", "analytics", "analitica",
    "preferences", "preferencias", "third parties", "terceros",
)
# Botones del banner que quedan sueltos en su propia línea.
_BUTTONS = frozenset(
    fold(b)
    for b in (
        "Aceptar", "Aceptar todo", "Aceptar todas", "Rechazar", "Rechazar todo", "Rechazar todas",
        "Configurar", "Personalizar", "Más opciones", "Accept", "Accept all", "Reject", "Reject all",
        "Agree", "I agree", "Disagree", "Manage options", "More options", "Learn more", "Customize",
    )
)


def is_consent_line(line: str) -> bool:
    folded = fold(line)
    if not folded:
        return False
    if folded.strip(" .!") in _BUTTONS:
        return True
    if _STRONG_RE.search(folded):
        return True
    return bool(_TOPIC.search(folded)) and sum(marker in folded for marker in _WEAK) >= 3


def strip_consent_noise(text: str) -> str:
    lines = [line for line in text.splitlines() if not is_consent_line(line)]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()

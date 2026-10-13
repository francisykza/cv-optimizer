"""Detecta qué ha reformulado la IA: expresiones del CV optimizado que no estaban en el original.

Se compara palabra a palabra (normalizando tildes, mayúsculas y plurales simples) y no línea a
línea: el CV se reordena por completo y un diff de líneas lo marcaría todo como cambiado.
Reordenar no cuenta como cambio; reformular sí.

Solo sirve para resaltar en la interfaz. No afecta al CV descargado ni a la validación.
"""

import re

from app.services.text_utils import STOPWORDS, SYNONYMS, fold, stem, tokens

_HEADING_MARK = re.compile(r"^\s*#{1,6}\s+")
_LIST_MARK = re.compile(r"^\s*(?:\d+[.)]|[-*+])\s+")
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
# Fronteras de formato: el frontend resalta dentro de cada nodo de texto del HTML, así que una
# frase no puede cruzar una negrita, una cursiva, código o un enlace.
_FORMAT_BOUNDARY = re.compile(r"\*\*|__|[*_`]|\]\([^)]*\)|[\[\]]")
_WORD = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9+#]+")
_MAX_STOPWORD_GAP = 2


class _Source:
    def __init__(self, text: str) -> None:
        self.tokens = set(tokens(text))
        self.stems = {stem(t) for t in self.tokens}
        self.folded = fold(text)

    def has(self, token: str) -> bool:
        if token in self.tokens or stem(token) in self.stems:
            return True
        return any(self._contains(alt) for alt in SYNONYMS.get(token, ()))

    def _contains(self, phrase: str) -> bool:
        return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", self.folded) is not None


def _classify(word: str, source: _Source, excluded: set[str]) -> str:
    """'new' (reformulación), 'stop' (palabra vacía) u 'old' (ya estaba o no se resalta)."""
    word_tokens = tokens(word)
    if not word_tokens:
        return "old"
    if all(t in STOPWORDS for t in word_tokens):
        return "stop"
    if any(t in excluded for t in word_tokens):
        return "old"  # Dato marcado en ámbar por el validador: debe seguir en ámbar.
    meaningful = [t for t in word_tokens if t not in STOPWORDS and not t.isdigit() and len(t) > 1]
    if not meaningful:
        return "old"  # Cifras y fechas las vigila el validador; no son "redacción".
    return "new" if any(not source.has(t) for t in meaningful) else "old"


def _phrases_in_segment(segment: str, source: _Source, excluded: set[str]) -> list[str]:
    words = [(m.start(), m.end(), _classify(m.group(), source, excluded)) for m in _WORD.finditer(segment)]
    phrases: list[str] = []
    i = 0
    while i < len(words):
        if words[i][2] != "new":
            i += 1
            continue
        start, end = words[i][0], words[i][1]
        j = i + 1
        while j < len(words):
            kind = words[j][2]
            if kind == "new":
                end = words[j][1]
                j += 1
                continue
            # Une "Diseñé y mantuve" en una sola frase: admite huecos cortos de palabras vacías.
            gap = j
            while gap < len(words) and words[gap][2] == "stop" and gap - j < _MAX_STOPWORD_GAP:
                gap += 1
            if gap < len(words) and gap > j and words[gap][2] == "new":
                j = gap
                continue
            break
        phrases.append(segment[start:end])
        i = j
    return phrases


def detect_changes(
    markdown: str, source_cv: str, exclude: list[str] | tuple[str, ...] = (), limit: int = 80
) -> list[str]:
    source = _Source(source_cv)
    excluded = {t for term in exclude for t in tokens(term) if t not in STOPWORDS}
    seen: set[str] = set()
    result: list[str] = []
    for line in markdown.splitlines():
        line = _LIST_MARK.sub("", _HEADING_MARK.sub("", _IMAGE.sub(" ", line)))
        for segment in _FORMAT_BOUNDARY.split(line):
            for phrase in _phrases_in_segment(segment, source, excluded):
                key = fold(phrase)
                if key in seen:
                    continue
                seen.add(key)
                result.append(phrase)
                if len(result) >= limit:
                    return result
    return result

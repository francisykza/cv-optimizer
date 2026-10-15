"""Normalización del texto extraído de PDFs."""

import re
import unicodedata

_BULLETS = re.compile(r"^[ \t]*[•▪●◦■□►▸‣∙·–—]+[ \t]*", re.MULTILINE)
_HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SPACES = re.compile(r"[ \t\u00a0]+")
_MANY_NEWLINES = re.compile(r"\n{3,}")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)  # ligaduras (ﬁ -> fi), anchos, etc.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    text = _CONTROL.sub("", text)
    text = _HYPHEN_BREAK.sub(r"\1\2", text)  # "desarro-\nllo" -> "desarrollo"
    text = _BULLETS.sub("- ", text)
    text = _SPACES.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _MANY_NEWLINES.sub("\n\n", text)
    return text.strip()

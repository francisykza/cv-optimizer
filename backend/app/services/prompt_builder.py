"""Construcción de prompts a partir de plantillas versionadas en `app/prompts/`."""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

PROMPT_VERSION = "v2"
_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

OutputLanguage = Literal["auto", "es", "en"]
_LANGUAGES: dict[str, str] = {
    "auto": "el mismo idioma en el que está escrita la oferta de trabajo",
    "es": "español",
    "en": "inglés (English)",
}

# Cualquier variante de <cv>, </cv>, <job_offer>, </ job_offer > ... dentro de los datos del
# usuario. Se neutraliza para que nadie pueda "cerrar" el bloque de datos e inyectar instrucciones.
_DELIMITER = re.compile(r"<\s*(/?)\s*(cv|job_offer)\s*>", re.IGNORECASE)
_PLACEHOLDER = re.compile(r"\{\{(JOB_OFFER|CV)\}\}")


@lru_cache
def _template(name: str) -> str:
    return (_PROMPTS_DIR / f"{name}.{PROMPT_VERSION}.md").read_text(encoding="utf-8")


def escape_user_data(text: str) -> str:
    return _DELIMITER.sub(lambda m: f"[{m.group(1)}{m.group(2)}]", text)


@dataclass(frozen=True)
class Prompt:
    system: str
    user: str
    version: str = PROMPT_VERSION


class PromptBuilder:
    def build(self, cv_text: str, job_offer: str, language: OutputLanguage) -> Prompt:
        system = _template("optimize_system").replace("{{OUTPUT_LANGUAGE}}", _LANGUAGES[language])
        values = {"JOB_OFFER": escape_user_data(job_offer), "CV": escape_user_data(cv_text)}
        # Sustitución en una sola pasada: un "{{CV}}" escrito dentro de la oferta no se expande.
        user = _PLACEHOLDER.sub(lambda m: values[m.group(1)], _template("optimize_user"))
        return Prompt(system=system, user=user)

    def repair_instruction(self) -> str:
        return _template("repair_json")

    def correction_instruction(self, items: list[str]) -> str:
        """Pide al LLM que elimine los elementos que el validador no encontró en el CV original."""
        listed = "\n".join(f"- {escape_user_data(item)}" for item in items)
        return _template("correct_ungrounded").replace("{{ITEMS}}", listed)

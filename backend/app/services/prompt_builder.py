"""Construcción de prompts a partir de plantillas versionadas en `app/prompts/`."""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

PROMPT_VERSION = "v5"
_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

OutputLanguage = Literal["auto", "es", "en"]
AdjustmentLevel = Literal["subtle", "deep"]
_LANGUAGES: dict[str, str] = {
    "auto": "el mismo idioma en el que está escrita la oferta de trabajo",
    "es": "español",
    "en": "inglés (English)",
}

_ADJUSTMENTS: dict[str, str] = {
    "subtle": (
        "SUTIL. Conserva las frases del CV original casi intactas. Limítate a ordenar las "
        "secciones, alinear la terminología con la de la oferta cuando sea un equivalente veraz e "
        "incorporar las palabras clave de la oferta que el CV ya respalda. No reescribas viñetas "
        "completas ni cambies su estructura."
    ),
    "deep": (
        "PROFUNDO. Reescribe el enfoque del CV para este puesto: resumen orientado a la oferta, "
        "viñetas con verbos de acción y estructura de logro [Acción] + [Herramienta] + [Resultado]. "
        "El resultado SOLO puede ser uno que aparezca en el CV; si el CV no indica ninguno, usa "
        "[Acción] + [Herramienta] y NUNCA inventes el resultado ni una cifra."
    ),
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
    def build(
        self, cv_text: str, job_offer: str, language: OutputLanguage, adjustment: AdjustmentLevel = "deep"
    ) -> Prompt:
        system = (
            _template("optimize_system")
            .replace("{{OUTPUT_LANGUAGE}}", _LANGUAGES[language])
            .replace("{{ADJUSTMENT}}", _ADJUSTMENTS[adjustment])
        )
        values = {"JOB_OFFER": escape_user_data(job_offer), "CV": escape_user_data(cv_text)}
        # Sustitución en una sola pasada: un "{{CV}}" escrito dentro de la oferta no se expande.
        user = _PLACEHOLDER.sub(lambda m: values[m.group(1)], _template("optimize_user"))
        return Prompt(system=system, user=user)

    def repair_instruction(self) -> str:
        return _template("repair_json")

    def correction_instruction(self, items: list[str], keep: list[str] | tuple[str, ...] = ()) -> str:
        """Pide al LLM que elimine lo no respaldado (`items`) y que recupere los términos de la
        oferta que ya estaban en el CV y ha quitado (`keep`)."""
        sections: list[str] = []
        if items:
            listed = "\n".join(f"- {escape_user_data(item)}" for item in items)
            sections.append(
                'Incumple la regla "PROHIBIDO INVENTAR". Estos elementos de "optimized_markdown" o de '
                f'"application_pitch" NO aparecen en el CV original:\n{listed}\n'
                "Elimínalos o sustitúyelos por lo que dice LITERALMENTE el CV original. Si alguno es un "
                'requisito de la oferta que el candidato no acredita, quítalo del CV y del pitch y '
                'añádelo a "gaps".'
            )
        if keep:
            listed = "\n".join(f"- {escape_user_data(term)}" for term in keep)
            sections.append(
                "Has quitado términos de la oferta que SÍ estaban en el CV original. Vuelve a incluirlos "
                f"LITERALMENTE donde correspondan:\n{listed}"
            )
        return _template("correct_ungrounded").replace("{{SECTIONS}}", "\n\n".join(sections))

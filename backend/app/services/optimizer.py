"""Caso de uso principal: PDF + oferta -> CV optimizado en Markdown."""

import asyncio
import json
import logging
import re
import time

from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings
from app.core.exceptions import AppError, InvalidPdfError, LLMBadOutputError
from app.schemas.optimize import (
    LLMOptimizeOutput,
    OptimizeMeta,
    OptimizeResponse,
    TokenUsageOut,
)
from app.services import match_scorer
from app.services.llm.base import ChatMessage, LLMProvider, LLMRequest, LLMResponse, Mode
from app.services.output_validator import OutputValidator, ValidationReport
from app.services.pdf_extractor import PdfExtractor
from app.services.prompt_builder import OutputLanguage, PromptBuilder

logger = logging.getLogger(__name__)

_CODE_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def parse_llm_output(content: str) -> LLMOptimizeOutput:
    try:
        data = json.loads(_CODE_FENCE.sub("", content))
        return LLMOptimizeOutput.model_validate(data)
    except (ValueError, ValidationError) as exc:
        raise LLMBadOutputError() from exc


class OptimizerService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._extractor = PdfExtractor(
            max_pages=settings.max_pdf_pages,
            min_chars=settings.cv_min_chars,
            max_chars=settings.cv_max_chars,
        )
        self._prompts = PromptBuilder()
        self._validator = OutputValidator()

    async def extract_text(self, pdf_bytes: bytes):
        try:
            return await asyncio.wait_for(
                run_in_threadpool(self._extractor.extract, pdf_bytes),
                timeout=self._settings.pdf_extraction_timeout_s,
            )
        except TimeoutError as exc:
            raise InvalidPdfError("El PDF es demasiado complejo para procesarlo.") from exc

    async def optimize(
        self,
        *,
        pdf_bytes: bytes,
        job_offer: str,
        language: OutputLanguage,
        provider: LLMProvider,
        mode: Mode,
        request_id: str | None,
    ) -> OptimizeResponse:
        start = time.perf_counter()
        extracted = await self.extract_text(pdf_bytes)

        prompt = self._prompts.build(extracted.text, job_offer, language)
        messages = [ChatMessage("system", prompt.system), ChatMessage("user", prompt.user)]
        output, responses = await self._complete_json(provider, messages)

        # Capa 4 del SDD: validación determinista + una corrección si hay datos no respaldados.
        keywords = match_scorer.clean_keywords(output.job_keywords, job_offer)
        report = self._validator.validate(output.optimized_markdown, extracted.text, keywords)
        first_ungrounded = report.ungrounded_count
        corrections = 0
        while (
            report.ungrounded_count >= self._settings.validator_correction_threshold
            and corrections < self._settings.validator_max_corrections
        ):
            corrections += 1
            corrected = await self._correct(provider, messages, responses[-1], report)
            if corrected is None:
                break
            new_output, new_responses = corrected
            responses += new_responses
            new_keywords = match_scorer.clean_keywords(new_output.job_keywords, job_offer)
            new_report = self._validator.validate(new_output.optimized_markdown, extracted.text, new_keywords)
            if new_report.ungrounded_count <= report.ungrounded_count:
                output, keywords, report = new_output, new_keywords, new_report

        match = match_scorer.score(
            keywords, extracted.text, output.optimized_markdown, exclude=report.leaked_keywords
        )
        quality = "needs_review" if report.ungrounded_count else "ok"
        latency_ms = int((time.perf_counter() - start) * 1000)
        tokens = TokenUsageOut(
            input=sum(r.usage.input for r in responses),
            output=sum(r.usage.output for r in responses),
        )

        # Solo metadatos: nunca el CV, la oferta ni la respuesta.
        logger.info(
            "optimize_done request_id=%s mode=%s model=%s pages=%d cv_chars=%d offer_chars=%d "
            "tokens_in=%d tokens_out=%d llm_calls=%d ungrounded_first=%d ungrounded_final=%d "
            "corrections=%d quality=%s latency_ms=%d",
            request_id, mode, responses[-1].model, extracted.pages, len(extracted.text),
            len(job_offer), tokens.input, tokens.output, len(responses), first_ungrounded,
            report.ungrounded_count, corrections, quality, latency_ms,
        )

        return OptimizeResponse(
            request_id=request_id,
            optimized_markdown=output.optimized_markdown.strip(),
            match=match,
            gaps=output.gaps,
            changes_summary=output.changes_summary,
            warnings=report.warnings,
            quality=quality,
            meta=OptimizeMeta(
                mode=mode,
                provider=provider.name,
                model=responses[-1].model,
                prompt_version=prompt.version,
                latency_ms=latency_ms,
                tokens=tokens,
                pdf_pages=extracted.pages,
            ),
        )

    async def _correct(
        self,
        provider: LLMProvider,
        messages: list[ChatMessage],
        previous: LLMResponse,
        report: ValidationReport,
    ) -> tuple[LLMOptimizeOutput, list[LLMResponse]] | None:
        """Pide al LLM que elimine lo no respaldado. Si la corrección falla, se conserva el
        resultado original (con sus avisos visibles) en lugar de perder toda la petición."""
        items = [w.term or w.message for w in report.ungrounded]
        correction_messages = [
            *messages,
            ChatMessage("assistant", previous.content),
            ChatMessage("user", self._prompts.correction_instruction(items)),
        ]
        try:
            return await self._complete_json(provider, correction_messages)
        except AppError as exc:
            logger.warning("llm_correction_failed code=%s", exc.code)
            return None

    async def _complete_json(
        self, provider: LLMProvider, messages: list[ChatMessage]
    ) -> tuple[LLMOptimizeOutput, list[LLMResponse]]:
        """Llama al LLM en modo JSON. Si la salida no es válida, hace UN intento de reparación."""
        responses: list[LLMResponse] = []
        previous_content: str | None = None
        try:
            response = await provider.complete(self._request(messages))
            responses.append(response)
            previous_content = response.content
            return parse_llm_output(response.content), responses
        except LLMBadOutputError:
            logger.warning("llm_bad_output_first_attempt; retrying with repair instruction")

        repair_messages = list(messages)
        if previous_content is not None:
            repair_messages.append(ChatMessage("assistant", previous_content))
        repair_messages.append(ChatMessage("user", self._prompts.repair_instruction()))

        response = await provider.complete(self._request(repair_messages))
        responses.append(response)
        return parse_llm_output(response.content), responses

    def _request(self, messages: list[ChatMessage]) -> LLMRequest:
        return LLMRequest(
            messages=messages,
            temperature=self._settings.llm_temperature,
            max_tokens=self._settings.llm_max_output_tokens,
            json_mode=True,
        )

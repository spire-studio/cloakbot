from __future__ import annotations

import time

from loguru import logger
from pydantic import BaseModel
from pydantic_ai import Agent, NativeOutput, RunContext
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.settings import ModelSettings

from cloakbot.privacy.core.detection.detector_model import (
    build_detector_model,
    response_text,
)
from cloakbot.privacy.core.placeholders import INTERNAL_TOKEN_RE
from cloakbot.privacy.core.types import REGISTRY, ComputableEntity

_TYPE_BLOCK = REGISTRY.get_prompt_block("computable")
_ENUM_STR = REGISTRY.get_enum_str("computable")
_VALID_ENTITY_TYPES = {spec.slug for spec in REGISTRY.computable}

_DIGIT_SYSTEM_PROMPT = f"""You are a privacy-focused numeric and temporal entity extractor.

Extract only private numeric or temporal values that should be masked before text is sent to an untrusted model.
Return exact substrings from the input.

Rules:
1. Extract private money, percentages, dates, timestamps, counts, ratios, and measurements only when tied to a specific person, private entity, account, case, or confidential workflow.
2. Do not extract formatting or workflow numbers: bullet counts, section numbers, field labels, worksheet placeholders, template versions, examples, or numbers the user says to keep as structure.
3. Do not extract public, generic, hypothetical, or common-knowledge numbers, including public fiscal/reporting years, unless they are a private deadline, timestamp, or milestone.
4. Do not extract numeric substrings inside addresses, phone numbers, emails, URLs, IP addresses, account IDs, invoice IDs, loan IDs, tax IDs, ticket IDs, contract IDs, or other compact identifiers. Other detectors handle those full spans.
5. Classify private money as financial. Money MUST have a currency symbol or currency word adjacent to the digits (e.g. "$5.00", "5.00 USD", "¥100", "€20", "5 EUR", "RMB 80"). A bare number with no currency is NOT financial — see Rules 9 and 10.
6. Use amount, value, and measurement only for standalone private quantities, not for identifiers or substrings inside another sensitive entity.
7. If masking a number would break the user's formatting or routing instruction, do not extract it unless it is clearly private.
8. Billing context: within a specific customer's document, its dates, money lines (subtotal, tax, total, balance, credit), and quantities are private even when they look generic — do not skip them as "common knowledge".
9. Completeness: extract EVERY currency-formatted span (including repeats and zero values) and EVERY date (including both ends of a range); the tokeniser dedupes downstream.
10. Number-with-unit: a digit joined to a unit (storage, weight, volume, time, count) or an "N × <noun>" multiplier is **measurement** / **amount** (value = N), never **financial** — even beside a money line.

Entity types:
{_TYPE_BLOCK}

Value normalization:
1. financial: extract as float/int, remove currency symbols and commas (e.g. "$1,200.50" -> 1200.5).
2. temporal: extract as a standardized string (e.g. "Oct 12th, 2023" -> "2023-10-12").
3. percentage: extract as float/int and normalize percentages to decimal fractions (e.g. "15%" -> 0.15).
4. amount: extract as float/int for counts or non-percentage ratios.
5. measurement: extract as float/int if possible, or string if units are inseparable (e.g. "0 GB" -> "0 GB").

Return ONLY valid JSON.
{{
  "entities": [
    {{
      "text": "<exact substring from input, unchanged>",
      "entity_type": "<{_ENUM_STR}>",
      "value": <numeric_value_or_string>
    }}
  ]
}}

If no sensitive numeric entities are found, use "entities": [].
Do NOT include the same entity text twice."""


class DigitDetection(BaseModel):
    """Structured output target for the digit detector LLM call."""

    entities: list[ComputableEntity] = []


class DigitDetectionResult(BaseModel):
    raw_output: str
    entities: list[ComputableEntity]
    latency_ms: float


_DIGIT_AGENT = Agent(
    output_type=NativeOutput(DigitDetection),
    instructions=_DIGIT_SYSTEM_PROMPT,
    deps_type=str,
    retries=1,
)


@_DIGIT_AGENT.output_validator
def _enforce_digit_invariants(ctx: RunContext[str], out: DigitDetection) -> DigitDetection:
    """Apply the privacy-bearing filters to the model's structured output.

    These are deterministic backstops, not model-correctable niceties: an
    extracted span must be a verbatim substring of the source and must not be
    one of our own internal placeholder tokens. ``ctx.deps`` is the source
    prompt.
    """
    return DigitDetection(entities=normalize_digit_entities(out.entities, ctx.deps))


def normalize_digit_entities(
    entities: list[ComputableEntity],
    prompt: str,
) -> list[ComputableEntity]:
    """Keep only valid, in-prompt, non-internal, de-duplicated numeric entities."""
    seen: set[str] = set()
    kept: list[ComputableEntity] = []
    for entity in entities:
        if entity.entity_type not in _VALID_ENTITY_TYPES:
            continue
        if INTERNAL_TOKEN_RE.search(entity.text):
            continue
        if entity.text in seen or entity.text not in prompt:
            continue
        seen.add(entity.text)
        kept.append(entity)
    return kept


class DigitPrivacyDetector:
    """Detect sensitive computable numeric entities for tokenization."""

    def __init__(self, temperature: float = 0.0) -> None:
        self._temperature = temperature

    async def detect(self, prompt: str) -> DigitDetectionResult:
        t0 = time.perf_counter()
        try:
            result = await _DIGIT_AGENT.run(
                prompt,
                deps=prompt,
                model=build_detector_model(),
                model_settings=ModelSettings(temperature=self._temperature),
            )
            entities = result.output.entities
            raw_output = response_text(result)
        except UnexpectedModelBehavior:
            logger.warning(
                "DigitPrivacyDetector: local model returned unparseable output; "
                "treating as no entities",
            )
            entities, raw_output = [], ""
        latency_ms = (time.perf_counter() - t0) * 1000
        return DigitDetectionResult(
            raw_output=raw_output, entities=entities, latency_ms=latency_ms,
        )

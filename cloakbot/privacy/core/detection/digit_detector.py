from __future__ import annotations

import re

from loguru import logger
from pydantic import BaseModel

from cloakbot.privacy.core.detection.llm_json import JsonCompletionRunner, load_json_object
from cloakbot.privacy.core.types import REGISTRY, ComputableEntity

_TYPE_BLOCK = REGISTRY.get_prompt_block("computable")
_ENUM_STR = REGISTRY.get_enum_str("computable")
_TOKEN_PATTERN = re.compile(r"(?:<<)?[A-Z]{2,}(?:_[A-Z]+)*_\d+(?:>>)?")
_VALID_ENTITY_TYPES = {spec.slug for spec in REGISTRY.computable}

_DIGIT_SYSTEM_PROMPT = f"""You are a privacy-focused numeric and temporal entity extractor.

━━━ System Architecture & Misson ━━━
You act as a local privacy-preserving proxy. The numeric entities you extract will be masked/anonymized before the sanitized prompt is sent to an untrusted remote LLM.
The remote LLM's job is to generate mathematical expressions based on the text. Therefore, you MUST preserve the logical structure and instructional numbers of the input, extracting ONLY the sensitive data values and require local computation values.

━━━ Strict Rules ━━━
3. Do NOT extract the entity that will affects the user instructed task after masking unless it is clearly private.
1. Format Validation: An entity MUST contain actual digits (0-9) or explicitly spelled-out numbers (e.g., "one", "hundred").
2. Instructional Bypass (CRITICAL): Do NOT extract numbers that are part of the user's formatting instructions, structural requests, or output constraints unless it is very sensitive.
3. Sensitivity Evaluation: Evaluate the contextual privacy risk. ONLY extract numbers tied to specific individuals, private entities, or confidential systems that require local computation (e.g., personal finances, medical vitals, specific coordinates, private scores).
4. Public Data Bypass: Do NOT extract generic, hypothetical, purely public, or common-knowledge numbers (e.g., "The earth has 1 moon", "a 5-star rating", "published in 2023").
5. When in doubt: If a number is tied to a specific individual/entity and you are unsure of its sensitivity, default to extracting it. But ALWAYS prioritize Rule 2 (ignore instructions).

━━━ Entity types ━━━
{_TYPE_BLOCK}

━━━ Value Normalization Rules ━━━
1. financial: extract as float/int, remove currency symbols and commas (e.g. "$1,200.50" -> 1200.5).
2. temporal: extract as a standardized string (e.g. "Oct 12th, 2023" -> "2023-10-12").
3. percentage: extract as float/int and normalize percentages to decimal fractions (e.g. "15%" -> 0.15).
4. amount: extract as float/int for counts or non-percentage ratios.
5. measurement: extract as float/int if possible, or string if units are inseparable.

━━━ Output format ━━━
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


class DigitDetectionResult(BaseModel):
    raw_output: str
    entities: list[ComputableEntity]
    latency_ms: float


class DigitPrivacyDetector:
    """Detect sensitive computable numeric entities for tokenization."""

    def __init__(self, temperature: float = 0.0) -> None:
        self._runner = JsonCompletionRunner(temperature=temperature)

    async def detect(self, prompt: str) -> DigitDetectionResult:
        raw_output, latency_ms = await self._runner.complete(_DIGIT_SYSTEM_PROMPT, prompt)
        entities = parse_digit_entities(raw_output, prompt)
        return DigitDetectionResult(raw_output=raw_output, entities=entities, latency_ms=latency_ms)


def parse_digit_entities(raw_output: str, prompt: str) -> list[ComputableEntity]:
    data = load_json_object(raw_output)
    if not data:
        return []

    seen: set[str] = set()
    entities: list[ComputableEntity] = []

    for item in data.get("entities", []):
        try:
            text = str(item["text"])
            slug = str(item["entity_type"])
            val = item["value"]

            if slug not in _VALID_ENTITY_TYPES:
                continue
            if _TOKEN_PATTERN.search(text):
                continue
            if text in seen or prompt.find(text) == -1:
                continue

            seen.add(text)
            entities.append(ComputableEntity(text=text, entity_type=slug, value=val))
        except (KeyError, ValueError):
            logger.debug("DigitPrivacyDetector: skipping malformed entity: {}", item)
            continue

    return entities

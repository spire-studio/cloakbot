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
8. Invoice / receipt / billing context: dates (invoice date, transaction date, billing period, due date), money lines (Subtotal, Total, Tax, Credit, Balance), and quantity lines are ALL private when they belong to a specific customer's document. Do not skip them as "common knowledge".
9. Number-with-unit rule: when a digit is immediately followed by a measurement or quantity unit (e.g. "GB", "TB", "MB", "KB", "kg", "lb", "ml", "hours", "minutes", "items", "pcs", "users", or a multiplier "x"), classify as **measurement** (keep the unit in the text) or **amount** (for pure quantity multipliers like "0 x ..."). Never label number-with-unit as **financial**, even when it appears next to a money line.
10. Quantity multiplier rule: spans of the form "N x <noun>" or "N × <noun>" describe a count, not money. Classify as **amount** with value N. Examples: "0 x Extra IPv4 Address" -> amount value=0; "2 x Storage Slots" -> amount value=2.
11. Money completeness: if you extract any currency amount from the input, extract EVERY currency-formatted span in the document, including duplicates and zero values ("$0.00 USD", "$0.00") — the downstream tokeniser dedupes by canonical value, so you must not skip repeats or zeros. Examples: an invoice with "$5.00 USD" extra fee, "$95.00 USD" subtotal, and "$0.00 USD" credit yields three financial entities, not one.
12. Date completeness: invoices and receipts frequently list 3+ dates (issue, transaction, period). Extract every date you see, including ranges like "05/02/2026 - 06/01/2026" — emit each date in the range as a separate temporal entity, or the range itself if it is one inseparable span.

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

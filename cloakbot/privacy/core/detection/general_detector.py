from __future__ import annotations

from loguru import logger
from pydantic import BaseModel

from cloakbot.privacy.core.detection.llm_json import JsonCompletionRunner, load_json_object
from cloakbot.privacy.core.types import REGISTRY, GeneralEntity

_TYPE_BLOCK = REGISTRY.get_prompt_block("general")
_ENUM_STR = REGISTRY.get_enum_str("general")
_VALID_ENTITY_TYPES = {spec.slug for spec in REGISTRY.general}

_GENERAL_SYSTEM_PROMPT = f"""You are a privacy-focused general entity extractor.

━━━ System Architecture & Misson ━━━
You act as a local privacy-preserving proxy. The general entities you extract will be masked/anonymized before the sanitized prompt is sent to an untrusted remote LLM.
The remote LLM's job is to answer the user's request while preserving task intent. Therefore, you MUST preserve the task structure and instructions, extracting ONLY sensitive non-computable entity values.

━━━ Strict Rules ━━━
1. Extract only sensitive NON-COMPUTABLE entity values.
2. Each extracted entity must be an exact substring from the input.
3. Instructional Bypass: Do NOT extract task instructions, formatting requirements, structural requests, or output constraints.
4. Public Data Bypass: Do NOT extract public entities unless they act as private identifiers in context.
5. Do NOT extract slot phrases or field references such as: "my name" in "What is my name", "my email" in "Send my email to Alice".
6. Never extract money, dates, times, percentages, counts, measurements, or plain numbers; the numeric detector handles private numeric values.
7. Use identifier only for compact reference codes or explicit account endings; never for spans with "$", "%", month names, or date formats.
8. Extract explicit person aliases and private-context organizations such as vendors, lenders, banks, payroll firms, and clinics.

━━━ Entity types ━━━
{_TYPE_BLOCK}

━━━ Output format ━━━
Return ONLY valid JSON.
{{
  "entities": [
    {{
      "text": "<exact substring from input, unchanged>",
      "entity_type": "<{_ENUM_STR}>"
    }}
  ]
}}

If no sensitive general entities are found, use "entities": [].
Do NOT include the same entity text twice."""

class GeneralDetectionResult(BaseModel):
    raw_output: str
    entities: list[GeneralEntity]
    latency_ms: float


class GeneralPrivacyDetector:
    """Detect general sensitive entities, excluding computable math elements."""

    def __init__(self, *, temperature: float = 0.0) -> None:
        self._runner = JsonCompletionRunner(temperature=temperature)

    async def detect(self, prompt: str) -> GeneralDetectionResult:
        raw_output, latency_ms = await self._runner.complete(_GENERAL_SYSTEM_PROMPT, prompt)
        entities = parse_general_entities(raw_output, prompt)
        return GeneralDetectionResult(
            raw_output=raw_output, entities=entities, latency_ms=latency_ms
        )


def parse_general_entities(raw_output: str, prompt: str) -> list[GeneralEntity]:
    data = load_json_object(raw_output)
    if not data:
        return []

    seen: set[str] = set()
    entities: list[GeneralEntity] = []

    for item in data.get("entities", []):
        try:
            text = str(item["text"])
            slug = str(item["entity_type"])
            if slug not in _VALID_ENTITY_TYPES:
                continue
            if text in seen or prompt.find(text) == -1:
                continue

            seen.add(text)
            entities.append(GeneralEntity(text=text, entity_type=slug))
        except (KeyError, ValueError):
            logger.debug("GeneralPrivacyDetector: skipping malformed entity: {}", item)
            continue

    return entities

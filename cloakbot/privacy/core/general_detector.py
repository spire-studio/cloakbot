from __future__ import annotations

from loguru import logger
from pydantic import BaseModel

from cloakbot.privacy.core.llm_json import JsonCompletionRunner, load_json_object
from cloakbot.privacy.core.types import REGISTRY, GeneralEntity

_TYPE_BLOCK = REGISTRY.get_prompt_block("general")
_ENUM_STR = REGISTRY.get_enum_str("general")
_VALID_ENTITY_TYPES = {spec.slug for spec in REGISTRY.general}

_GENERAL_SYSTEM_PROMPT = f"""You are a Named Entity Recognition (NER) system focused on privacy.

Your STRICT task is to extract sensitive NON-COMPUTABLE entities from the user text.
These entities that you extract will be masked before sending to a remote LLM.

━━━ STRICT RULES ━━━
1. Do NOT extract computable numeric values (e.g., money, salaries, percentages, dates, measurements). Leave those to a separate math detector.
2. Do NOT extract the entities that may affect the user instructed task.

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

If no entities are found, use "entities": [].
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

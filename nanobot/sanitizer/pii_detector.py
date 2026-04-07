"""
PII detector — sends the user prompt to the local Gemma 4 model and returns
a structured list of sensitive entities found in the text.

Design notes
------------
- Always uses the local vLLM endpoint so PII never leaves the device during
  detection.
- stream=False: we need the full JSON before proceeding.
- Char offsets are computed in Python (str.find), not trusted from the LLM.
- Duplicate entity texts are deduplicated; only the first occurrence is kept.
- Defensive JSON extraction handles markdown fences and stray think-blocks
  (Gemma 4 does not emit these, but kept for robustness).
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from enum import Enum

from loguru import logger

from nanobot.providers.vllm import get_vllm_client, get_vllm_model


# ---------------------------------------------------------------------------
# Entity types (must match the labels in the system prompt)
# ---------------------------------------------------------------------------

class EntityType(str, Enum):
    PERSON = "person"
    PHONE = "phone"
    EMAIL = "email"
    ID = "id"
    ADDRESS = "address"
    CREDENTIAL = "credential"
    ORG = "org"
    BIZ_DATE = "biz_date"
    BIZ_FINANCE = "biz_finance"
    BIZ_OPS = "biz_ops"
    OTHER = "other"


# Map EntityType → short uppercase tag used inside placeholders.
ENTITY_TAG: dict[EntityType, str] = {
    EntityType.PERSON: "PERSON",
    EntityType.PHONE: "PHONE",
    EntityType.EMAIL: "EMAIL",
    EntityType.ID: "ID",
    EntityType.ADDRESS: "ADDRESS",
    EntityType.CREDENTIAL: "CREDENTIAL",
    EntityType.ORG: "ORG",
    EntityType.BIZ_DATE: "DATE",
    EntityType.BIZ_FINANCE: "AMOUNT",
    EntityType.BIZ_OPS: "BIZ_DETAIL",
    EntityType.OTHER: "ENTITY",
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class DetectedEntity:
    text: str
    entity_type: EntityType
    context_reason: str
    should_sanitize: bool


@dataclass
class DetectionResult:
    original_prompt: str
    entities: list[DetectedEntity]
    llm_raw_output: str
    latency_ms: float

    @property
    def has_sensitive_data(self) -> bool:
        return any(e.should_sanitize for e in self.entities)

    @property
    def sensitive_entities(self) -> list[DetectedEntity]:
        return [e for e in self.entities if e.should_sanitize]


# ---------------------------------------------------------------------------
# System prompt (bilingual, context-aware NER)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are a privacy and data-security analyst specializing in both Chinese and English text.

Your task:
1. Identify every entity in the user text that may constitute personally identifiable information (PII) or sensitive business/organisational data.
2. For each entity, decide whether it should be sanitized before the text is sent to a remote LLM.

━━━ Entity types ━━━

Personal PII:
  person      – individual names (full or partial)
  phone       – phone numbers in any format
  email       – email addresses
  id          – government IDs, passport numbers, employee IDs, license plates
  address     – physical addresses (specific enough to locate a person)
  credential  – passwords, API keys, tokens, secrets

Organisational / business-sensitive:
  org         – company or organisation names
  biz_date    – specific dates tied to a corporate event, decision, or filing
                (e.g. deal close date, board resolution date, fiscal year-end
                used as a reference point for unreleased data)
  biz_finance – specific financial figures tied to a business operation:
                deal prices, internal cost targets, production volumes,
                exchange rate projections, revenue/margin forecasts
  biz_ops     – operational details revealing strategy or competitive position:
                named geographic markets being entered or exited, M&A targets,
                headcount figures, product launch timelines
  credential  – passwords, API keys, tokens, secrets
  other       – sensitive identifiers not covered above

━━━ Sanitization rules (context-aware) ━━━

SHOULD sanitize:
  Personal PII (always):
    • Private individual names (clients, employees, family members)
    • All phone numbers, emails, government IDs, physical addresses, credentials

  Business data (when the text contains non-public or proprietary details):
    • Specific financial figures tied to internal operations or undisclosed deals
    • Specific dates that anchor an undisclosed decision or unreleased milestone
    • Named geographic markets combined with operational intent
    • Forward-looking projections and internal estimates

SHOULD NOT sanitize:
  • Well-known public figures (heads of state, global celebrities)
  • Globally recognised public companies in purely descriptive, non-operational context
  • Geographic names used as pure location references with no operational intent
  • Widely published regulatory dates
  • Historical facts with no operational sensitivity

━━━ Quasi-identifier rule ━━━
If multiple individually borderline items together would reveal an organisation's
confidential strategy, finances, or identity, flag each of them.

━━━ Output format ━━━
Return ONLY valid JSON, no markdown fences, no explanation outside the JSON:
{
  "entities": [
    {
      "text": "<exact substring from input, unchanged>",
      "entity_type": "<person|org|phone|email|id|address|credential|biz_date|biz_finance|biz_ops|other>",
      "context_reason": "<one concise sentence explaining the decision>",
      "should_sanitize": <true|false>
    }
  ]
}

If no entities are found, return: {"entities": []}
Do NOT include the same entity text twice."""


# ---------------------------------------------------------------------------
# JSON parsing helpers
# ---------------------------------------------------------------------------

def _strip_think_block(text: str) -> str:
    """Remove <think>…</think> blocks (defensive; Gemma 4 does not emit these)."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _extract_json(text: str) -> str:
    """Return the JSON portion of the model output, stripping fences if present."""
    text = _strip_think_block(text)
    match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def _parse_response(raw: str, prompt: str) -> list[DetectedEntity]:
    """
    Parse LLM JSON output into DetectedEntity objects.

    Silently drops entities that:
    - cannot be parsed
    - have an unknown entity_type
    - do not appear verbatim in the prompt
    - are duplicates of an already-seen text
    """
    json_text = _extract_json(raw)
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        logger.warning("PiiDetector: LLM returned invalid JSON; treating as no entities")
        return []

    seen: set[str] = set()
    entities: list[DetectedEntity] = []

    for item in data.get("entities", []):
        try:
            text = str(item["text"])
            entity_type = EntityType(item["entity_type"])
            context_reason = str(item["context_reason"])
            should_sanitize = bool(item["should_sanitize"])
        except (KeyError, ValueError):
            logger.debug("PiiDetector: skipping malformed entity: {}", item)
            continue

        if text in seen:
            continue
        if prompt.find(text) == -1:
            logger.debug("PiiDetector: entity '{}' not found in prompt; skipping", text)
            continue

        seen.add(text)
        entities.append(DetectedEntity(
            text=text,
            entity_type=entity_type,
            context_reason=context_reason,
            should_sanitize=should_sanitize,
        ))

    return entities


# ---------------------------------------------------------------------------
# Public detector class
# ---------------------------------------------------------------------------

class PiiDetector:
    """
    Runs a single non-streaming local-LLM call to detect and classify PII.

    Parameters
    ----------
    temperature:
        Keep at 0.0 for deterministic entity extraction.
    """

    def __init__(self, temperature: float = 0.0) -> None:
        self._temperature = temperature

    async def detect(self, prompt: str) -> DetectionResult:
        """
        Detect sensitive entities in *prompt*.

        Raises on LLM connectivity failure — the caller decides whether to
        block the message or allow it through (failing open vs. closed).
        """
        client = get_vllm_client()
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        t0 = time.perf_counter()
        try:
            response = await client.chat.completions.create(
                model=get_vllm_model(),
                messages=messages,  # type: ignore[arg-type]
                temperature=self._temperature,
                stream=False,
            )
            raw_output: str = response.choices[0].message.content or ""
        except Exception:
            logger.exception("PiiDetector: LLM call failed")
            raise

        latency_ms = (time.perf_counter() - t0) * 1000
        entities = _parse_response(raw_output, prompt)

        logger.debug(
            "PiiDetector: {} entities found ({} to sanitize) in {:.0f} ms",
            len(entities),
            sum(1 for e in entities if e.should_sanitize),
            latency_ms,
        )

        return DetectionResult(
            original_prompt=prompt,
            entities=entities,
            llm_raw_output=raw_output,
            latency_ms=latency_ms,
        )

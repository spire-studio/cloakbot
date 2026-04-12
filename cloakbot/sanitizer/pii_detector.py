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

from cloakbot.providers.vllm import get_vllm_client, get_vllm_model


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
class MathVariable:
    name: str
    value: float
    description: str
    source_text: str
    is_sensitive: bool = True


@dataclass
class MathPlan:
    is_math_task: bool = False
    intent: str = ""
    variables: list[MathVariable] = field(default_factory=list)

    @property
    def enabled(self) -> bool:
        return self.is_math_task and bool(self.variables)


@dataclass
class DetectionResult:
    original_prompt: str
    entities: list[DetectedEntity]
    llm_raw_output: str
    latency_ms: float
    math_plan: MathPlan = field(default_factory=MathPlan)

    @property
    def has_sensitive_data(self) -> bool:
        return bool(self.sensitive_entities)

    @property
    def sensitive_entities(self) -> list[DetectedEntity]:
        sensitive: list[DetectedEntity] = [e for e in self.entities if e.should_sanitize]
        if not self.math_plan.is_math_task:
            return sensitive

        seen_texts = {e.text for e in sensitive}
        for var in self.math_plan.variables:
            text = var.source_text.strip()
            if not text:
                continue
            if text in seen_texts:
                continue
            if self.original_prompt.find(text) == -1:
                continue
            sensitive.append(
                DetectedEntity(
                    text=text,
                    entity_type=EntityType.BIZ_FINANCE,
                    context_reason="privacy-math sensitive numeric variable",
                    should_sanitize=True,
                )
            )
            seen_texts.add(text)

        # Fallback: in math tasks, redact all numeric literals from the prompt
        # even if the model omitted them from `math.variables`.
        numeric_pattern = r"[$¥€£]?\s*-?\d[\d,]*(?:\.\d+)?\s*%?"
        for match in re.finditer(numeric_pattern, self.original_prompt):
            text = match.group(0).strip()
            if not text or text in seen_texts:
                continue
            sensitive.append(
                DetectedEntity(
                    text=text,
                    entity_type=EntityType.BIZ_FINANCE,
                    context_reason="privacy-math numeric literal fallback",
                    should_sanitize=True,
                )
            )
            seen_texts.add(text)
        return sensitive


# ---------------------------------------------------------------------------
# System prompt (bilingual, context-aware NER)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are a privacy and data-security analyst specializing in both Chinese and English text.

Your task:
1. Identify every entity in the user text that may constitute personally identifiable information (PII) or sensitive business/organisational data.
2. For each entity, decide whether it should be sanitized before the text is sent to a remote LLM.

━━━ Entity types ━━━

Personal PII:
  person      – private individual names or unique personal handles
  phone       – phone numbers
  email       – email addresses
  id          – unique identifiers (government/tax/insurance/employee/student/account/device IDs, license plates)
  address     – precise physical addresses or location details tied to a person
  credential  – authentication secrets (passwords, API keys, tokens, private keys, one-time codes)
  other       – personal numeric/quasi-identifying attributes linked to a private individual
                (e.g. personal balances, salary, debt, transaction amounts, age, scores,
                medical metrics, exact coordinates, repeated time/location patterns)

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
    • Any person, phone, email, id, address, or credential that can identify or authenticate a private individual
    • Personal numeric values or quantitative facts tied to a private individual
      (finances, health, education/performance, geolocation, behavior patterns),
      even when the number alone looks harmless

  Business data (when the text contains non-public or proprietary details):
    • Specific financial figures tied to internal operations or undisclosed deals
    • Specific dates that anchor an undisclosed decision or unreleased milestone
    • Named geographic markets combined with operational intent
    • Forward-looking projections and internal estimates

SHOULD NOT sanitize:
  • Well-known public figures (heads of state, global celebrities)
  • Globally recognised public companies in purely descriptive, non-operational context
  • Geographic names used as pure location references with no operational intent
  • Generic numbers with no link to a private individual or confidential business context
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
  ],
  "math": {
    "is_math_task": <true|false>,
    "intent": "<brief user math intent>",
    "variables": [
      {
        "name": "<V1|V2|...>",
        "description": "<what the number means>",
        "source_text": "<exact substring from input containing that number>",
        "value": <number>,
        "is_sensitive": <true|false>
      }
    ]
  }
}

For "math":
- Set is_math_task=true only when the user asks for numeric calculation/comparison/forecast.
- Extract only numbers needed for the calculation.
- "value" must be numeric (int/float), no units in the value field.
- If not a math task, return:
  "math": {"is_math_task": false, "intent": "", "variables": []}

If no entities are found, use "entities": [].
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


def _parse_should_sanitize(value: object) -> bool:
    """
    Parse should_sanitize using strict boolean semantics.

    Accepts:
    - bool values
    - strings "true"/"false" (case-insensitive)
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
    raise ValueError(f"invalid should_sanitize value: {value!r}")


def _parse_bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
    return default


def _parse_numeric(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?\s*%?", value.strip())
        if not match:
            return None
        raw = match.group(0).replace(",", "").strip()
        if raw.endswith("%"):
            raw = raw[:-1].strip()
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            return None
    return None


def _normalize_var_name(value: object, *, fallback: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_]", "", str(value or "").strip())
    if not text:
        return fallback
    if text[0].isdigit():
        text = f"V_{text}"
    return text.upper()


def _find_numeric_substring(prompt: str, value: float) -> str:
    """
    Find a numeric literal in prompt that matches *value*.

    Supports optional currency symbols, thousands separators, and percent suffix.
    """
    pattern = r"[$¥€£]?\s*-?\d[\d,]*(?:\.\d+)?\s*%?"
    for match in re.finditer(pattern, prompt):
        token = match.group(0).strip()
        raw = token
        for symbol in ("$", "¥", "€", "£"):
            raw = raw.replace(symbol, "")
        raw = raw.replace(",", "").strip()
        if raw.endswith("%"):
            raw = raw[:-1].strip()
        if not raw:
            continue
        try:
            parsed = float(raw)
        except ValueError:
            continue
        if abs(parsed - value) < 1e-9:
            return token
    return ""


def _load_response_json(raw: str) -> dict[str, object]:
    json_text = _extract_json(raw)
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        logger.warning("PiiDetector: LLM returned invalid JSON; treating as empty result")
        return {}
    if not isinstance(data, dict):
        logger.warning("PiiDetector: LLM returned non-object JSON; treating as empty result")
        return {}
    return data


def _parse_response(raw: str, prompt: str) -> list[DetectedEntity]:
    """
    Parse LLM JSON output into DetectedEntity objects.

    Silently drops entities that:
    - cannot be parsed
    - have an unknown entity_type
    - do not appear verbatim in the prompt
    - are duplicates of an already-seen text
    """
    data = _load_response_json(raw)
    if not data:
        return []

    seen: set[str] = set()
    entities: list[DetectedEntity] = []

    for item in data.get("entities", []):
        try:
            text = str(item["text"])
            entity_type = EntityType(item["entity_type"])
            context_reason = str(item["context_reason"])
            should_sanitize = _parse_should_sanitize(item["should_sanitize"])
        except (KeyError, TypeError, ValueError):
            logger.debug("PiiDetector: skipping malformed entity: {}", item)
            continue

        if text in seen:
            continue
        if prompt.find(text) == -1:
            logger.debug("PiiDetector: entity '{}' not found in prompt; skipping", text)
            continue

        seen.add(text)
        entities.append(
            DetectedEntity(
                text=text,
                entity_type=entity_type,
                context_reason=context_reason,
                should_sanitize=should_sanitize,
            )
        )

    return entities


def _parse_math_plan(raw: str, prompt: str) -> MathPlan:
    data = _load_response_json(raw)
    if not data:
        return MathPlan()

    math_data = data.get("math")
    if not isinstance(math_data, dict):
        return MathPlan()

    is_math_task = _parse_bool(math_data.get("is_math_task"), default=False)
    intent = str(math_data.get("intent", "")).strip()

    raw_variables = math_data.get("variables", [])
    if not isinstance(raw_variables, list):
        raw_variables = []

    variables: list[MathVariable] = []
    seen_names: set[str] = set()
    for index, item in enumerate(raw_variables, start=1):
        if not isinstance(item, dict):
            continue

        model_value = _parse_numeric(item.get("value"))
        source_text = str(item.get("source_text", "")).strip()
        if source_text and prompt.find(source_text) == -1:
            logger.debug(
                "PiiDetector: math source_text '{}' not found in prompt; trying numeric fallback",
                source_text,
            )
            source_text = ""
        if not source_text and model_value is not None:
            source_text = _find_numeric_substring(prompt, model_value)
        source_value = _parse_numeric(source_text) if source_text else None
        value = source_value if source_value is not None else model_value
        if value is None:
            continue

        description = str(item.get("description", "")).strip() or source_text or f"value_{index}"
        name = _normalize_var_name(item.get("name"), fallback=f"V{index}")
        if name in seen_names:
            suffix = 2
            while f"{name}_{suffix}" in seen_names:
                suffix += 1
            name = f"{name}_{suffix}"
        seen_names.add(name)

        variables.append(
            MathVariable(
                name=name,
                value=value,
                description=description,
                source_text=source_text,
                is_sensitive=_parse_bool(item.get("is_sensitive"), default=True),
            )
        )

    if not variables:
        return MathPlan(
            is_math_task=False,
            intent=intent,
            variables=[],
        )

    return MathPlan(
        is_math_task=is_math_task,
        intent=intent,
        variables=variables,
    )


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
        math_plan = _parse_math_plan(raw_output, prompt)

        logger.debug(
            "PiiDetector: {} entities found ({} to sanitize), math_task={} vars={} in {:.0f} ms",
            len(entities),
            sum(1 for e in entities if e.should_sanitize),
            math_plan.is_math_task,
            len(math_plan.variables),
            latency_ms,
        )

        return DetectionResult(
            original_prompt=prompt,
            entities=entities,
            llm_raw_output=raw_output,
            latency_ms=latency_ms,
            math_plan=math_plan,
        )

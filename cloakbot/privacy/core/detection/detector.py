"""Composed privacy detector facade."""

from __future__ import annotations

import json
import re

from loguru import logger

from cloakbot.privacy.core.detection.digit_detector import DigitPrivacyDetector
from cloakbot.privacy.core.detection.general_detector import (
    GeneralPrivacyDetector,
    PartialCandidate,
)
from cloakbot.privacy.core.placeholders import INTERNAL_TOKEN_RE
from cloakbot.privacy.core.types import (
    DetectedEntity,
    DetectionResult,
    GeneralEntity,
    Severity,
)

_ENTITY_PRIORITY = {
    "email": 100,
    "phone": 100,
    "ip_address": 100,
    "local_path": 100,
    "url": 100,
    "address": 95,
    "identifier": 95,
    "person": 90,
    "org": 90,
    "medical": 90,
    "financial": 85,
    "temporal": 85,
    "percentage": 85,
    "credential": 70,
    "measurement": 60,
    "amount": 55,
    "value": 50,
}
_LOCAL_PATH_PATTERN = re.compile(
    r"(?<!\S)(?:file://[^\s<>'\"]+|~[/\\][^\s<>'\"]+|/[^<>'\"\s]+|\.{1,2}[/\\][^\s<>'\"]+|[A-Za-z]:[\\/][^\s<>'\"]+)",
)
_LOCAL_PATH_TRAILING = ".,;:!?)\\]}"


class PiiDetector:
    """Run general and digit detectors to produce one detection result."""

    def __init__(self, temperature: float = 0.0) -> None:
        self._general = GeneralPrivacyDetector(temperature=temperature)
        self._digit = DigitPrivacyDetector(temperature=temperature)

    async def detect(
        self,
        prompt: str,
        *,
        intent_hint: str | None = None,
        partial_candidates: list[PartialCandidate] | None = None,
    ) -> DetectionResult:
        # Run the detectors SEQUENTIALLY, not concurrently. They share one local
        # model instance; firing both at once thrashes a single-instance backend
        # (KV-cache contention) — which is slower end-to-end AND can make the
        # slower general detector time out and silently return nothing, leaking
        # PII. Sequential is faster and reliable here. (Concurrency would only
        # help a batching server such as vLLM.)
        general_result = await self._general.detect(
            prompt,
            partial_candidates=partial_candidates,
        )
        digit_result = await self._digit.detect(prompt)
        latency_ms = general_result.latency_ms + digit_result.latency_ms

        entities_by_text: dict[str, DetectedEntity] = {}
        for entity in general_result.entities + digit_result.entities + _detect_local_paths(prompt):
            # Central filter: Ignore anything that looks like our own internal tokens
            if INTERNAL_TOKEN_RE.search(entity.text):
                logger.debug("PiiDetector: ignoring internal token match '{}'", entity.text)
                continue

            existing = entities_by_text.get(entity.text)
            if existing is not None and _entity_priority(existing) >= _entity_priority(entity):
                continue

            entities_by_text[entity.text] = entity

        entities = list(entities_by_text.values())

        llm_raw_output = json.dumps(
            {
                "general": general_result.raw_output,
                "digit": digit_result.raw_output,
                "intent_hint": intent_hint,
            },
        )

        logger.debug(
            "PiiDetector: {} entities found in {:.0f} ms",
            len(entities),
            latency_ms,
        )

        return DetectionResult(
            original_prompt=prompt,
            entities=entities,
            llm_raw_output=llm_raw_output,
            latency_ms=latency_ms,
        )


def _entity_priority(entity: DetectedEntity) -> int:
    return _ENTITY_PRIORITY.get(entity.entity_type, 0)


def _detect_local_paths(prompt: str) -> list[GeneralEntity]:
    entities: list[GeneralEntity] = []
    seen: set[str] = set()
    for match in _LOCAL_PATH_PATTERN.finditer(prompt):
        value = match.group(0).rstrip(_LOCAL_PATH_TRAILING)
        if not value or value in seen:
            continue
        if value.startswith(("http://", "https://")):
            continue
        seen.add(value)
        entities.append(GeneralEntity(text=value, entity_type="local_path"))
    return entities


__all__ = [
    "DetectedEntity",
    "DetectionResult",
    "PiiDetector",
    "Severity",
]

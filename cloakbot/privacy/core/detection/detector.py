"""Composed privacy detector facade."""

from __future__ import annotations

import asyncio
import json
import re

from loguru import logger

from cloakbot.privacy.core.detection.digit_detector import DigitPrivacyDetector
from cloakbot.privacy.core.detection.general_detector import GeneralPrivacyDetector
from cloakbot.privacy.core.types import (
    DetectedEntity,
    DetectionResult,
    Severity,
)

# Robust regex to catch placeholders with or without brackets, and various PII tags
_TOKEN_PATTERN = re.compile(r"(?:<<)?[A-Z]{2,}(?:_[A-Z]+)*_\d+(?:>>)?")


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
    ) -> DetectionResult:
        # Run both detectors concurrently to halve the latency
        general_result, digit_result = await asyncio.gather(
            self._general.detect(prompt), self._digit.detect(prompt)
        )
        latency_ms = max(general_result.latency_ms, digit_result.latency_ms)

        entities: list[DetectedEntity] = []
        seen_text: set[str] = set()
        for entity in general_result.entities + digit_result.entities:
            # Central filter: Ignore anything that looks like our own internal tokens
            if _TOKEN_PATTERN.search(entity.text):
                logger.debug("PiiDetector: ignoring internal token match '{}'", entity.text)
                continue

            if entity.text in seen_text:
                continue

            seen_text.add(entity.text)
            entities.append(entity)

        llm_raw_output = json.dumps(
            {
                "general": general_result.raw_output,
                "digit": digit_result.raw_output,
                "intent_hint": intent_hint,
            }
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


__all__ = [
    "DetectedEntity",
    "DetectionResult",
    "PiiDetector",
    "Severity",
]

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from cloakbot.privacy.core.detection.digit_detector import DigitPrivacyDetector


@pytest.mark.asyncio
async def test_digit_detector_extracts_numeric_entities() -> None:
    detector = DigitPrivacyDetector()
    detector._runner.complete = AsyncMock(
        return_value=(
            json.dumps(
                {
                    "entities": [
                        {"text": "$100,000", "entity_type": "financial", "value": 100000},
                        {"text": "10%", "entity_type": "percentage", "value": 0.1},
                    ]
                }
            ),
            1.0,
        )
    )

    result = await detector.detect("salary is $100,000 and bonus rate is 10%")

    assert [entity.text for entity in result.entities] == ["$100,000", "10%"]
    assert [entity.entity_type for entity in result.entities] == ["financial", "percentage"]


@pytest.mark.asyncio
async def test_digit_detector_skips_values_not_in_prompt() -> None:
    detector = DigitPrivacyDetector()
    detector._runner.complete = AsyncMock(
        return_value=(
            json.dumps(
                {
                    "entities": [
                        {"text": "$200,000", "entity_type": "financial", "value": 200000},
                    ]
                }
            ),
            1.0,
        )
    )

    result = await detector.detect("salary is $100,000")

    assert result.entities == []


@pytest.mark.asyncio
async def test_digit_detector_skips_placeholder_like_tokens() -> None:
    detector = DigitPrivacyDetector()
    detector._runner.complete = AsyncMock(
        return_value=(
            json.dumps(
                {
                    "entities": [
                        {"text": "<<AMOUNT_1>>", "entity_type": "amount", "value": 1},
                        {"text": "AMOUNT_1", "entity_type": "amount", "value": 1},
                        {"text": "$<<AMOUNT_1>>", "entity_type": "financial", "value": 1},
                    ]
                }
            ),
            1.0,
        )
    )

    result = await detector.detect("value <<AMOUNT_1>>")

    assert result.entities == []

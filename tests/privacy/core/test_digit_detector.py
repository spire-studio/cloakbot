from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from cloakbot.privacy.core.detection.digit_detector import DigitPrivacyDetector


def _fixed_model(payload: str) -> FunctionModel:
    """A local model stand-in that always returns ``payload`` as its text."""
    return FunctionModel(lambda messages, info: ModelResponse(parts=[TextPart(payload)]))


def _patch_model(payload: str):
    return patch(
        "cloakbot.privacy.core.detection.digit_detector.build_detector_model",
        return_value=_fixed_model(payload),
    )


@pytest.mark.asyncio
async def test_digit_detector_extracts_numeric_entities() -> None:
    payload = json.dumps(
        {
            "entities": [
                {"text": "$100,000", "entity_type": "financial", "value": 100000},
                {"text": "10%", "entity_type": "percentage", "value": 0.1},
            ]
        }
    )
    with _patch_model(payload):
        result = await DigitPrivacyDetector().detect("salary is $100,000 and bonus rate is 10%")

    assert [entity.text for entity in result.entities] == ["$100,000", "10%"]
    assert [entity.entity_type for entity in result.entities] == ["financial", "percentage"]


@pytest.mark.asyncio
async def test_digit_detector_skips_values_not_in_prompt() -> None:
    payload = json.dumps(
        {"entities": [{"text": "$200,000", "entity_type": "financial", "value": 200000}]}
    )
    with _patch_model(payload):
        result = await DigitPrivacyDetector().detect("salary is $100,000")

    assert result.entities == []


@pytest.mark.asyncio
async def test_digit_detector_skips_placeholder_like_tokens() -> None:
    payload = json.dumps(
        {
            "entities": [
                {"text": "<<AMOUNT_1>>", "entity_type": "amount", "value": 1},
                {"text": "AMOUNT_1", "entity_type": "amount", "value": 1},
                {"text": "$<<AMOUNT_1>>", "entity_type": "financial", "value": 1},
            ]
        }
    )
    with _patch_model(payload):
        result = await DigitPrivacyDetector().detect("value <<AMOUNT_1>>")

    assert result.entities == []


@pytest.mark.asyncio
async def test_digit_detector_returns_empty_on_unparseable_output() -> None:
    # Invalid JSON survives the retry budget -> treated as "no entities" (not an error),
    # mirroring the previous load_json_object -> {} -> [] behaviour.
    with _patch_model("not json at all"):
        result = await DigitPrivacyDetector().detect("salary is $100,000")

    assert result.entities == []
    assert result.raw_output == ""

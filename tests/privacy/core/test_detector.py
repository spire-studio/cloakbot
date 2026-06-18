from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from cloakbot.privacy.core.detection.detector import PiiDetector
from cloakbot.privacy.core.detection.digit_detector import DigitDetectionResult
from cloakbot.privacy.core.detection.general_detector import (
    GeneralDetectionResult,
    GeneralPrivacyDetector,
    PartialCandidate,
    _build_system_prompt,
    _build_user_prompt,
    scan_partial_candidates,
)
from cloakbot.privacy.core.types import ComputableEntity, DetectionResult, GeneralEntity

_GENERAL_MODEL = "cloakbot.privacy.core.detection.general_detector.build_detector_model"


def _fixed_model(payload: str) -> FunctionModel:
    return FunctionModel(lambda messages, info: ModelResponse(parts=[TextPart(payload)]))


def _general(text: str, entity_type: str) -> GeneralEntity:
    return GeneralEntity(text=text, entity_type=entity_type)


def _computable(text: str, entity_type: str, value: int | float | str) -> ComputableEntity:
    return ComputableEntity(text=text, entity_type=entity_type, value=value)


class TestGeneralDetectorPrompt:
    def test_build_system_prompt_has_no_candidate_context(self) -> None:
        prompt = _build_system_prompt()

        assert "Candidate partial mentions detected" not in prompt

    def test_scan_partial_candidates_filters_and_deduplicates_surfaces(self) -> None:
        candidates = scan_partial_candidates(
            "Robert sent Acme the update. Liu signed it.",
            [
                {"canonical": "Robert Liu", "type": "person"},
                {"canonical": "Acme Corporation", "type": "org"},
                {"canonical": "R X", "type": "person"},
                {"canonical": "robert@example.com", "type": "email"},
            ],
        )

        assert candidates == [
            PartialCandidate(surface="Robert", canonical="Robert Liu", entity_type="person"),
            PartialCandidate(surface="Liu", canonical="Robert Liu", entity_type="person"),
            PartialCandidate(surface="Acme", canonical="Acme Corporation", entity_type="org"),
        ]

    def test_build_user_prompt_includes_partial_candidates(self) -> None:
        prompt = _build_user_prompt(
            "Robert 的邮箱是 robertliu@corp.com",
            [
                PartialCandidate(surface="Robert", canonical="Robert Liu", entity_type="person"),
            ],
        )

        assert "Candidate partial mentions detected" in prompt
        assert '"Robert" may refer to known person "Robert Liu"' in prompt
        assert 'extract "Robert" as: person' in prompt
        assert "If ambiguous or unrelated, skip it." in prompt
        assert "Text to analyze:\nRobert 的邮箱是 robertliu@corp.com" in prompt

    def test_build_user_prompt_without_candidates_returns_text(self) -> None:
        prompt = "Robert 的邮箱是 robertliu@corp.com"

        assert _build_user_prompt(prompt, []) == prompt


@pytest.mark.asyncio
class TestGeneralPrivacyDetector:
    async def test_detect_places_partial_candidates_in_user_prompt_only(self) -> None:
        captured: dict[str, str] = {}

        def capture(messages, info):
            captured["instructions"] = messages[0].instructions or ""
            for message in messages:
                for part in getattr(message, "parts", []):
                    if type(part).__name__ == "UserPromptPart":
                        captured["user_prompt"] = part.content
            return ModelResponse(
                parts=[
                    TextPart(
                        json.dumps(
                            {
                                "entities": [
                                    {"text": "Robert", "entity_type": "person"},
                                    {"text": "Robert Liu", "entity_type": "person"},
                                ]
                            }
                        )
                    )
                ]
            )

        detector = GeneralPrivacyDetector()
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(_GENERAL_MODEL, lambda: FunctionModel(capture), raising=True)
            result = await detector.detect(
                "Robert 的邮箱是 robertliu@corp.com",
                partial_candidates=[
                    PartialCandidate(surface="Robert", canonical="Robert Liu", entity_type="person"),
                ],
            )

        # The system prompt (instructions) must never carry candidate context.
        assert "Robert Liu" not in captured["instructions"]
        assert '"Robert" may refer to known person "Robert Liu"' in captured["user_prompt"]
        # "Robert Liu" is not a verbatim substring of the prompt -> filtered out.
        assert [entity.text for entity in result.entities] == ["Robert"]

    async def test_detect_returns_empty_on_unparseable_output(self) -> None:
        detector = GeneralPrivacyDetector()
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(_GENERAL_MODEL, lambda: _fixed_model("not json at all"), raising=True)
            result = await detector.detect("Hello Alice")

        assert result.entities == []
        assert result.raw_output == ""


@pytest.mark.asyncio
class TestPiiDetectorFacade:
    async def test_detect_runs_general_and_digit_detectors(self) -> None:
        detector = PiiDetector()
        detector._general.detect = AsyncMock(
            return_value=GeneralDetectionResult(
                raw_output='{"entities": []}',
                entities=[_general("Alice", "person")],
                latency_ms=10.0,
            )
        )
        detector._digit.detect = AsyncMock(
            return_value=DigitDetectionResult(
                raw_output='{"entities": []}',
                entities=[_computable("$100,000", "financial", 100000)],
                latency_ms=5.0,
            )
        )

        result = await detector.detect("Alice has $100,000")

        detector._general.detect.assert_awaited_once_with(
            "Alice has $100,000",
            partial_candidates=None,
        )
        detector._digit.detect.assert_awaited_once_with("Alice has $100,000")
        assert isinstance(result, DetectionResult)
        assert len(result.entities) == 2
        assert result.latency_ms == 15.0  # sequential: general (10.0) + digit (5.0)

    async def test_detect_passes_partial_candidates_only_to_general_detector(self) -> None:
        detector = PiiDetector()
        detector._general.detect = AsyncMock(
            return_value=GeneralDetectionResult(
                raw_output='{"entities": []}',
                entities=[],
                latency_ms=1.0,
            )
        )
        detector._digit.detect = AsyncMock(
            return_value=DigitDetectionResult(
                raw_output='{"entities": []}',
                entities=[],
                latency_ms=1.0,
            )
        )
        candidates = [
            PartialCandidate(surface="Robert", canonical="Robert Liu", entity_type="person"),
        ]

        await detector.detect("Robert followed up", partial_candidates=candidates)

        detector._general.detect.assert_awaited_once_with(
            "Robert followed up",
            partial_candidates=candidates,
        )
        detector._digit.detect.assert_awaited_once_with("Robert followed up")

    async def test_detect_prefers_financial_over_credential_for_same_text(self) -> None:
        detector = PiiDetector()
        detector._general.detect = AsyncMock(
            return_value=GeneralDetectionResult(
                raw_output='{"entities": []}',
                entities=[_general("$430", "credential")],
                latency_ms=1.0,
            )
        )
        detector._digit.detect = AsyncMock(
            return_value=DigitDetectionResult(
                raw_output='{"entities": []}',
                entities=[_computable("$430", "financial", 430)],
                latency_ms=1.0,
            )
        )

        result = await detector.detect("$430")

        assert [entity.text for entity in result.entities] == ["$430"]
        assert [entity.entity_type for entity in result.entities] == ["financial"]

    async def test_detect_prefers_specific_general_entity_over_numeric_guess(self) -> None:
        detector = PiiDetector()
        detector._general.detect = AsyncMock(
            return_value=GeneralDetectionResult(
                raw_output='{"entities": []}',
                entities=[_general("555-010-8821", "phone")],
                latency_ms=1.0,
            )
        )
        detector._digit.detect = AsyncMock(
            return_value=DigitDetectionResult(
                raw_output='{"entities": []}',
                entities=[_computable("555-010-8821", "amount", "5550108821")],
                latency_ms=1.0,
            )
        )

        result = await detector.detect("phone 555-010-8821")

        assert [entity.text for entity in result.entities] == ["555-010-8821"]
        assert [entity.entity_type for entity in result.entities] == ["phone"]

    async def test_detect_adds_local_path_entity_deterministically(self) -> None:
        detector = PiiDetector()
        detector._general.detect = AsyncMock(
            return_value=GeneralDetectionResult(
                raw_output='{"entities": []}',
                entities=[],
                latency_ms=1.0,
            )
        )
        detector._digit.detect = AsyncMock(
            return_value=DigitDetectionResult(
                raw_output='{"entities": []}',
                entities=[],
                latency_ms=1.0,
            )
        )

        result = await detector.detect(
            "/Users/laurieluo/Documents/github/my-repos/cloakbot/gamma4-image-test/data/invoice.jpg\n"
            "Please read this invoice."
        )

        assert [
            (entity.text, entity.entity_type)
            for entity in result.entities
        ] == [
            (
                "/Users/laurieluo/Documents/github/my-repos/cloakbot/gamma4-image-test/data/invoice.jpg",
                "local_path",
            )
        ]

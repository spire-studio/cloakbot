from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from cloakbot.privacy.core.detector import PiiDetector
from cloakbot.privacy.core.digit_detector import DigitDetectionResult
from cloakbot.privacy.core.general_detector import GeneralDetectionResult
from cloakbot.privacy.core.llm_json import JsonCompletionRunner, is_valid_json_object
from cloakbot.privacy.core.types import ComputableEntity, DetectionResult, GeneralEntity


def _response(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
            )
        ]
    )


def _general(text: str, entity_type: str) -> GeneralEntity:
    return GeneralEntity(text=text, entity_type=entity_type)


def _computable(text: str, entity_type: str, value: int | float | str) -> ComputableEntity:
    return ComputableEntity(text=text, entity_type=entity_type, value=value)


class TestDetectorJsonValidation:
    def test_has_valid_response_json_returns_true_for_object(self) -> None:
        assert is_valid_json_object('{"entities": []}') is True

    def test_has_valid_response_json_returns_false_for_incomplete_json(self) -> None:
        assert is_valid_json_object('{"entities": []') is False


@pytest.mark.asyncio
class TestJsonCompletionRunner:
    async def test_complete_retries_once_on_invalid_json(self) -> None:
        client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=AsyncMock(
                        side_effect=[
                            _response('{"entities": []'),
                            _response('{"entities": []}'),
                        ]
                    )
                )
            )
        )

        runner = JsonCompletionRunner()
        with patch(
            "cloakbot.privacy.core.llm_json.get_vllm_client",
            return_value=client,
        ), patch(
            "cloakbot.privacy.core.llm_json.get_vllm_model",
            return_value="test-model",
        ):
            raw_output, _latency_ms = await runner.complete("system", "prompt")

        assert raw_output == '{"entities": []}'
        assert client.chat.completions.create.await_count == 2
        first_call = client.chat.completions.create.await_args_list[0].kwargs
        assert first_call["response_format"] == {"type": "json_object"}

    async def test_complete_does_not_retry_when_json_is_valid(self) -> None:
        client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=AsyncMock(return_value=_response('{"entities": []}'))
                )
            )
        )

        runner = JsonCompletionRunner()
        with patch(
            "cloakbot.privacy.core.llm_json.get_vllm_client",
            return_value=client,
        ), patch(
            "cloakbot.privacy.core.llm_json.get_vllm_model",
            return_value="test-model",
        ):
            await runner.complete("system", "prompt")

        assert client.chat.completions.create.await_count == 1


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

        detector._general.detect.assert_awaited_once_with("Alice has $100,000")
        detector._digit.detect.assert_awaited_once_with("Alice has $100,000")
        assert isinstance(result, DetectionResult)
        assert len(result.entities) == 2
        assert result.latency_ms == 10.0

    async def test_detect_deduplicates_same_text_across_detectors(self) -> None:
        detector = PiiDetector()
        detector._general.detect = AsyncMock(
            return_value=GeneralDetectionResult(
                raw_output='{"entities": []}',
                entities=[_general("Alice", "person")],
                latency_ms=1.0,
            )
        )
        detector._digit.detect = AsyncMock(
            return_value=DigitDetectionResult(
                raw_output='{"entities": []}',
                entities=[_computable("Alice", "value", "Alice")],
                latency_ms=1.0,
            )
        )

        result = await detector.detect("Alice")

        assert [entity.text for entity in result.entities] == ["Alice"]

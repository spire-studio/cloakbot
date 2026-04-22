"""
Tests for the privacy sanitization modules.

Unit tests (no LLM, pure Python):
  - PII detector response parser
  - Rewrite + remap logic
  - Session-level map persistence

Integration tests (require vLLM, skipped by default):
  - Full sanitize_input / remap_response round-trip
  Run with: pytest -m integration
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from cloakbot.privacy.core.detection.detector import PiiDetector
from cloakbot.privacy.core.detection.general_detector import parse_general_entities
from cloakbot.privacy.core.sanitization.handler import apply_tokens as _rewrite
from cloakbot.privacy.core.sanitization.restorer import restore_tokens as _remap
from cloakbot.privacy.core.sanitization.sanitize import (
    remap_response,
    sanitize_input,
    sanitize_input_with_detection,
)
from cloakbot.privacy.core.state.vault import (
    _SessionMap,
    _load_map,
    _save_map,
    clear_cache,
)
from cloakbot.privacy.core.types import (
    ComputableEntity,
    DetectedEntity,
    DetectionResult,
    GeneralEntity,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _detection(prompt: str, entities: list[DetectedEntity]) -> DetectionResult:
    return DetectionResult(
        original_prompt=prompt,
        entities=entities,
        llm_raw_output="",
        latency_ms=0.0,
    )


def _entity(text: str, entity_type: str) -> GeneralEntity:
    return GeneralEntity(text=text, entity_type=entity_type)


def _computable(text: str, entity_type: str, value: int | float | str) -> ComputableEntity:
    return ComputableEntity(text=text, entity_type=entity_type, value=value)


def _empty_map() -> _SessionMap:
    return _SessionMap(
        original_to_placeholder={},
        placeholder_to_original={},
        counters={},
    )


# ---------------------------------------------------------------------------
# PiiDetector — JSON parser (no LLM)
# ---------------------------------------------------------------------------

class TestParseResponse:
    def test_parses_valid_json(self):
        raw = json.dumps({"entities": [
            {"text": "Alice", "entity_type": "person"},
        ]})
        result = parse_general_entities(raw, "Hello Alice")
        assert len(result) == 1
        assert result[0].text == "Alice"
        assert result[0].entity_type == "person"

    def test_strips_markdown_fences(self):
        raw = '```json\n{"entities": []}\n```'
        result = parse_general_entities(raw, "anything")
        assert result == []

    def test_strips_think_block(self):
        raw = '<think>reasoning</think>\n{"entities": []}'
        result = parse_general_entities(raw, "anything")
        assert result == []

    def test_returns_empty_on_invalid_json(self):
        result = parse_general_entities("not json at all", "prompt")
        assert result == []

    def test_skips_entity_not_in_prompt(self):
        raw = json.dumps({"entities": [
            {"text": "Bob", "entity_type": "person"},
        ]})
        result = parse_general_entities(raw, "Hello Alice")  # Bob not in prompt
        assert result == []

    def test_deduplicates_same_text(self):
        raw = json.dumps({"entities": [
            {"text": "Alice", "entity_type": "person"},
            {"text": "Alice", "entity_type": "person"},
        ]})
        result = parse_general_entities(raw, "Hello Alice and Alice")
        assert len(result) == 1

    def test_skips_unknown_entity_type(self):
        raw = json.dumps({"entities": [
            {"text": "Alice", "entity_type": "unknown_type"},
        ]})
        result = parse_general_entities(raw, "Hello Alice")
        assert result == []


# ---------------------------------------------------------------------------
# Rewrite — pure Python
# ---------------------------------------------------------------------------

class TestRewrite:
    def test_single_entity_replaced(self):
        det = _detection("Hello Alice", [_entity("Alice", "person")])
        smap = _empty_map()
        text, modified = _rewrite(det, smap)
        assert modified is True
        assert "Alice" not in text
        assert "<<PERSON_1>>" in text

    def test_clean_input_unchanged(self):
        det = _detection("What is the capital?", [])
        smap = _empty_map()
        text, modified = _rewrite(det, smap)
        assert modified is False
        assert text == "What is the capital?"

    def test_multiple_types_get_own_counters(self):
        det = _detection(
            "Alice alice@acme.com 138-0000-1234",
            [
                _entity("Alice", "person"),
                _entity("alice@acme.com", "email"),
                _entity("138-0000-1234", "phone"),
            ],
        )
        smap = _empty_map()
        text, modified = _rewrite(det, smap)
        assert modified is True
        assert "<<PERSON_1>>" in text
        assert "<<EMAIL_1>>" in text
        assert "<<PHONE_1>>" in text

    def test_same_entity_reuses_existing_placeholder(self):
        det = _detection("Hello Alice", [_entity("Alice", "person")])
        smap = _empty_map()
        smap.original_to_placeholder["Alice"] = "<<PERSON_1>>"
        smap.placeholder_to_original["<<PERSON_1>>"] = "Alice"
        smap.counters["PERSON"] = 1
        _rewrite(det, smap)
        # Counter must not advance — still PERSON_1, no PERSON_2
        assert smap.counters["PERSON"] == 1

    def test_longest_entity_replaced_first(self):
        # "张伟明" must be replaced before "张伟" to avoid partial collision
        det = _detection(
            "张伟明的电话",
            [
                _entity("张伟", "person"),
                _entity("张伟明", "person"),
            ],
        )
        smap = _empty_map()
        text, modified = _rewrite(det, smap)
        assert modified is True
        assert "张伟明" not in text
        assert "张伟" not in text

# ---------------------------------------------------------------------------
# Remap — pure Python
# ---------------------------------------------------------------------------

class TestRemap:
    def test_placeholder_restored(self):
        smap = _empty_map()
        smap.placeholder_to_original["<<PERSON_1>>"] = "Alice"
        result = _remap("Hello <<PERSON_1>>", smap)
        assert result == "Hello Alice"

    def test_empty_map_returns_original(self):
        smap = _empty_map()
        result = _remap("Hello <<PERSON_1>>", smap)
        assert result == "Hello <<PERSON_1>>"

    def test_missing_placeholder_silently_skipped(self):
        smap = _empty_map()
        smap.placeholder_to_original["<<PERSON_1>>"] = "Alice"
        result = _remap("No placeholders here", smap)
        assert result == "No placeholders here"

    def test_longest_placeholder_first(self):
        # <<PERSON_10>> must not be partially matched by <<PERSON_1>>
        smap = _empty_map()
        smap.placeholder_to_original["<<PERSON_1>>"] = "Alice"
        smap.placeholder_to_original["<<PERSON_10>>"] = "Bob"
        result = _remap("<<PERSON_10>> and <<PERSON_1>>", smap)
        assert result == "Bob and Alice"

    def test_multiple_placeholders_all_restored(self):
        smap = _empty_map()
        smap.placeholder_to_original = {
            "<<PERSON_1>>": "Alice",
            "<<EMAIL_1>>": "alice@acme.com",
        }
        result = _remap("<<PERSON_1>> — <<EMAIL_1>>", smap)
        assert result == "Alice — alice@acme.com"


# ---------------------------------------------------------------------------
# Session map — JSON persistence
# ---------------------------------------------------------------------------

class TestSessionMap:
    def test_save_and_load_roundtrip(self, tmp_path: Path):
        smap = _SessionMap(
            original_to_placeholder={"Alice": "<<PERSON_1>>"},
            placeholder_to_original={"<<PERSON_1>>": "Alice"},
            counters={"PERSON": 1},
        )
        with patch(
            "cloakbot.privacy.core.state.vault._map_path",
            return_value=tmp_path / "test.json",
        ):
            _save_map("test:session", smap)
            loaded = _load_map("test:session")

        assert loaded.original_to_placeholder == {"Alice": "<<PERSON_1>>"}
        assert loaded.placeholder_to_original == {"<<PERSON_1>>": "Alice"}
        assert loaded.counters == {"PERSON": 1}

    def test_missing_file_returns_empty_map(self, tmp_path: Path):
        with patch(
            "cloakbot.privacy.core.state.vault._map_path",
            return_value=tmp_path / "nonexistent.json",
        ):
            loaded = _load_map("no:session")
        assert loaded.original_to_placeholder == {}

    def test_corrupt_file_returns_empty_map(self, tmp_path: Path):
        bad = tmp_path / "bad.json"
        bad.write_text("not json", encoding="utf-8")
        with patch(
            "cloakbot.privacy.core.state.vault._map_path",
            return_value=bad,
        ):
            loaded = _load_map("bad:session")
        assert loaded.original_to_placeholder == {}


# ---------------------------------------------------------------------------
# sanitize_input + remap_response — mocked LLM
# ---------------------------------------------------------------------------

def _mock_detection(entities_json: list[dict]) -> AsyncMock:
    """Return an AsyncMock for PiiDetector.detect() with given entities."""
    mock = AsyncMock()

    def _build_result(prompt: str) -> DetectionResult:
        raw = json.dumps({"entities": entities_json})
        entities = parse_general_entities(raw, prompt)
        return DetectionResult(
            original_prompt=prompt,
            entities=entities,
            llm_raw_output=raw,
            latency_ms=1.0,
        )

    mock.side_effect = lambda prompt: asyncio.coroutine(lambda: _build_result(prompt))()
    return mock


import asyncio


@pytest.fixture()
def session_key(tmp_path: Path):
    """Isolated session key that writes maps to tmp_path."""
    key = "test:isolated"
    with patch(
        "cloakbot.privacy.core.state.vault._map_path",
        side_effect=lambda k: tmp_path / f"{k.replace(':', '_')}.json",
    ):
        clear_cache(key)
        yield key
        clear_cache(key)


class TestSanitizeInput:
    async def test_pii_detected_and_redacted(self, session_key: str):
        with patch.object(PiiDetector, "detect", new_callable=AsyncMock) as mock_detect:
            mock_detect.return_value = DetectionResult(
                original_prompt="Hello Alice",
                entities=[_entity("Alice", "person")],
                llm_raw_output="",
                latency_ms=1.0,
            )
            text, modified, _ = await sanitize_input("Hello Alice", session_key)

        assert modified is True
        assert "Alice" not in text
        assert "<<PERSON_1>>" in text

    async def test_clean_input_passes_through(self, session_key: str):
        with patch.object(PiiDetector, "detect", new_callable=AsyncMock) as mock_detect:
            mock_detect.return_value = DetectionResult(
                original_prompt="What time is it?",
                entities=[],
                llm_raw_output="",
                latency_ms=1.0,
            )
            text, modified, _ = await sanitize_input("What time is it?", session_key)

        assert modified is False
        assert text == "What time is it?"

    async def test_with_detection_returns_detection_payload(self, session_key: str):
        with patch.object(PiiDetector, "detect", new_callable=AsyncMock) as mock_detect:
            mock_detect.return_value = DetectionResult(
                original_prompt="Revenue is 100, cost is 60, margin?",
                entities=[
                    _computable("100", "amount", 100),
                    _computable("60", "amount", 60),
                ],
                llm_raw_output="",
                latency_ms=1.0,
            )
            text, modified, _entities, detection = await sanitize_input_with_detection(
                "Revenue is 100, cost is 60, margin?",
                session_key,
            )

        assert modified is True
        assert "100" not in text
        assert "60" not in text
        assert "<<AMOUNT_1>>" in text
        assert "<<AMOUNT_2>>" in text
        assert detection is not None
        assert detection.original_prompt == "Revenue is 100, cost is 60, margin?"

    async def test_fail_open_on_llm_error(self, session_key: str):
        with patch.object(PiiDetector, "detect", new_callable=AsyncMock) as mock_detect:
            mock_detect.side_effect = ConnectionError("vLLM unreachable")
            text, modified, _ = await sanitize_input(
                "Hello Alice", session_key, fail_open=True
            )

        assert modified is False
        assert text == "Hello Alice"  # passes through unmodified

    async def test_fail_closed_raises_on_llm_error(self, session_key: str):
        with patch.object(PiiDetector, "detect", new_callable=AsyncMock) as mock_detect:
            mock_detect.side_effect = ConnectionError("vLLM unreachable")
            with pytest.raises(ConnectionError):
                await sanitize_input("Hello Alice", session_key, fail_open=False)

    async def test_cross_turn_same_entity_reuses_placeholder(self, session_key: str):
        """Same entity in turn 2 must get the same placeholder as turn 1."""
        entity = _entity("Alice", "person")

        with patch.object(PiiDetector, "detect", new_callable=AsyncMock) as mock_detect:
            mock_detect.return_value = DetectionResult(
                original_prompt="I'm Alice",
                entities=[entity],
                llm_raw_output="",
                latency_ms=1.0,
            )
            text1, _, _e = await sanitize_input("I'm Alice", session_key)

        with patch.object(PiiDetector, "detect", new_callable=AsyncMock) as mock_detect:
            mock_detect.return_value = DetectionResult(
                original_prompt="Alice again",
                entities=[_entity("Alice", "person")],
                llm_raw_output="",
                latency_ms=1.0,
            )
            text2, _, _e = await sanitize_input("Alice again", session_key)

        assert "<<PERSON_1>>" in text1
        assert "<<PERSON_1>>" in text2
        # Must not create PERSON_2 for the same name
        assert "<<PERSON_2>>" not in text2

    async def test_remap_response_restores_cross_turn(self, session_key: str):
        """Placeholder written in turn 1 must be restorable in turn 2 response."""
        with patch.object(PiiDetector, "detect", new_callable=AsyncMock) as mock_detect:
            mock_detect.return_value = DetectionResult(
                original_prompt="I'm Alice",
                entities=[_entity("Alice", "person")],
                llm_raw_output="",
                latency_ms=1.0,
            )
            await sanitize_input("I'm Alice", session_key)

        # Simulate LLM echoing the placeholder in its response
        restored = await remap_response("Nice to meet you, <<PERSON_1>>!", session_key)
        assert restored == "Nice to meet you, Alice!"


# ---------------------------------------------------------------------------
# Integration tests (require running vLLM — skipped by default)
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestIntegration:
    async def test_personal_pii_round_trip(self):
        text = "My name is Alice Chen, email alice@acme.com, phone 138-0000-1234."
        session = "integration:pii"
        sanitized, modified, _ = await sanitize_input(text, session, fail_open=False)

        assert modified is True
        assert "Alice Chen" not in sanitized
        assert "alice@acme.com" not in sanitized
        assert "138-0000-1234" not in sanitized

        restored = await remap_response(sanitized, session)
        assert "Alice Chen" in restored
        assert "alice@acme.com" in restored

    async def test_business_sensitive_round_trip(self):
        text = "We're acquiring TargetCorp for $205 million, closing December 15."
        session = "integration:biz"
        sanitized, modified, _ = await sanitize_input(text, session, fail_open=False)

        assert modified is True
        assert "$205 million" not in sanitized
        assert "December 15" not in sanitized

        restored = await remap_response(sanitized, session)
        assert "$205 million" in restored
        assert "December 15" in restored
        assert "TargetCorp" in restored

    async def test_clean_input_no_modification(self):
        text = "What is the capital of France?"
        session = "integration:clean"
        sanitized, modified, _ = await sanitize_input(text, session, fail_open=False)

        assert modified is False
        assert sanitized == text

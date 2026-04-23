from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from cloakbot.privacy.core.detection.detector import PiiDetector
from cloakbot.privacy.core.sanitization.alias_resolver import resolve_existing_placeholder
from cloakbot.privacy.core.sanitization.sanitize import sanitize_input_with_detection
from cloakbot.privacy.core.types import DetectionResult, GeneralEntity
from cloakbot.privacy.core.state.vault import _SessionMap


def _entity(text: str, entity_type: str) -> GeneralEntity:
    return GeneralEntity(text=text, entity_type=entity_type)


@pytest.mark.asyncio
async def test_sanitize_input_pre_swaps_known_originals(monkeypatch) -> None:
    smap = _SessionMap()
    placeholder, _ = smap.get_or_create_placeholder("Alice Chen", "PERSON", turn_id="turn-1")
    smap.register_alias(placeholder, "Alice", turn_id="turn-1")

    detect = AsyncMock(
        return_value=DetectionResult(
            original_prompt="Hello <<PERSON_1>>",
            entities=[],
            llm_raw_output="",
            latency_ms=1.0,
        )
    )
    save_calls: list[_SessionMap] = []

    monkeypatch.setattr(PiiDetector, "detect", detect)
    monkeypatch.setattr("cloakbot.privacy.core.sanitization.sanitize.get_map", lambda _session_key: smap)
    monkeypatch.setattr(
        "cloakbot.privacy.core.sanitization.sanitize.save_map",
        lambda _session_key, saved_map: save_calls.append(saved_map),
    )

    sanitized, modified, entities, _ = await sanitize_input_with_detection(
        "Hello Alice",
        "cli:test",
        turn_id="turn-2",
    )

    detect.assert_awaited_once_with("Hello <<PERSON_1>>")
    assert sanitized == "Hello <<PERSON_1>>"
    assert modified is True
    assert entities == []
    assert save_calls == [smap]


def test_alias_resolver_reuses_existing_person_placeholder() -> None:
    smap = _SessionMap()
    placeholder, _ = smap.get_or_create_placeholder("Laurie Luo", "PERSON", turn_id="turn-1")
    smap.register_alias(placeholder, "Laurie", turn_id="turn-1")

    reused = resolve_existing_placeholder("Laurie", "PERSON", smap)

    assert reused == placeholder

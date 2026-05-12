from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from cloakbot.privacy.core.detection.detector import PiiDetector
from cloakbot.privacy.core.detection.general_detector import PartialCandidate
from cloakbot.privacy.core.sanitization.alias_resolver import resolve_existing_placeholder
from cloakbot.privacy.core.sanitization.sanitize import (
    _alias_prone_vault_entries,
    sanitize_input_with_detection,
)
from cloakbot.privacy.core.state.vault import _SessionMap
from cloakbot.privacy.core.types import DetectionResult, GeneralEntity


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

    detect.assert_awaited_once_with(
        "Hello <<PERSON_1>>",
        partial_candidates=[],
    )
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


def test_alias_prone_vault_entries_filter_to_person_and_org_canonical_values() -> None:
    smap = _SessionMap()
    placeholder, _ = smap.get_or_create_placeholder("Robert Liu", "PERSON", turn_id="turn-1")
    smap.register_alias(placeholder, "Robert", turn_id="turn-1")
    smap.get_or_create_placeholder("Acme Corporation", "ORG", turn_id="turn-99")
    smap.get_or_create_placeholder("robert@example.com", "EMAIL", turn_id="turn-100")

    entries = _alias_prone_vault_entries(smap)

    assert entries == [
        {"canonical": "Robert Liu", "type": "person"},
        {"canonical": "Acme Corporation", "type": "org"},
    ]


@pytest.mark.asyncio
async def test_sanitize_input_passes_partial_candidates_from_vault(monkeypatch) -> None:
    smap = _SessionMap()
    smap.get_or_create_placeholder("Robert Liu", "PERSON", turn_id="turn-1")
    detect = AsyncMock(
        return_value=DetectionResult(
            original_prompt="Robert 的邮箱是 robertliu@corp.com",
            entities=[],
            llm_raw_output="",
            latency_ms=1.0,
        )
    )

    monkeypatch.setattr(PiiDetector, "detect", detect)
    monkeypatch.setattr("cloakbot.privacy.core.sanitization.sanitize.get_map", lambda _session_key: smap)

    await sanitize_input_with_detection(
        "Robert 的邮箱是 robertliu@corp.com",
        "cli:test",
        turn_id="turn-2",
    )

    detect.assert_awaited_once_with(
        "Robert 的邮箱是 robertliu@corp.com",
        partial_candidates=[
            PartialCandidate(surface="Robert", canonical="Robert Liu", entity_type="person"),
        ],
    )

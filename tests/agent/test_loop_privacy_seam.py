"""End-to-end privacy-seam test for the rebased AgentLoop.

Proves the load-bearing invariant of the [seam:2] loop wiring: the raw user
turn is sanitized in `_state_build` *before* it reaches the LLM provider, so no
raw sensitive value can cross the wire. Detection is mocked (no local vLLM in
unit tests); token restoration on the way out is covered by tests/privacy/test_hooks.py.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cloakbot.bus.events import InboundMessage
from cloakbot.privacy.core.types import DetectionResult, GeneralEntity
from cloakbot.privacy.hooks.context import Intent
from cloakbot.providers.base import LLMResponse

from .conftest import make_loop


@pytest.mark.asyncio
async def test_raw_user_input_never_reaches_provider(tmp_path) -> None:
    captured_messages: list[list[dict]] = []

    async def chat_with_retry(*, messages, **kwargs):
        captured_messages.append(messages)
        return LLMResponse(content="Noted, <<PERSON_1>>.", tool_calls=[])

    # Tolerant (unspec'd) provider: the shared conftest.make_provider uses
    # MagicMock(spec=LLMProvider) and sets estimate_prompt_tokens, which upstream
    # LLMProvider no longer exposes (a W0-tail harness mismatch). Build our own.
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    provider.generation = SimpleNamespace(max_tokens=4096, temperature=0.1, reasoning_effort=None)
    provider.estimate_prompt_tokens.return_value = (10_000, "test")
    provider.chat_with_retry = chat_with_retry

    loop = make_loop(tmp_path, provider=provider)

    detection = DetectionResult(
        original_prompt="My name is Alice",
        entities=[GeneralEntity(text="Alice", entity_type="person")],
        llm_raw_output="",
        latency_ms=1.0,
    )

    with patch(
        "cloakbot.privacy.runtime.pipeline.sanitize_input_with_detection",
        new=AsyncMock(
            return_value=(
                "My name is <<PERSON_1>>",
                True,
                detection.sensitive_entities,
                detection,
            )
        ),
    ), patch(
        "cloakbot.privacy.runtime.pipeline.analyze_user_intent",
        new=AsyncMock(return_value=Intent.CHAT),
    ):
        msg = InboundMessage(
            channel="cli",
            sender_id="user",
            chat_id="leaktest",
            content="My name is Alice",
        )
        await loop._process_message(msg, session_key="cli:leaktest")

    assert captured_messages, "provider was never called"
    payload = repr(captured_messages)
    assert "Alice" not in payload, "RAW PII reached the provider payload — privacy seam leaked"
    assert "<<PERSON_1>>" in payload, "sanitized placeholder missing from provider payload"


@pytest.mark.asyncio
async def test_ephemeral_run_vault_never_lands_on_disk(tmp_path) -> None:
    """[Cap B] An ephemeral run (dream / cron / heartbeat / autonomous turn) is
    keyed to a memory-only child vault scope: privacy is still ON for the run
    (the provider sees placeholders, not raw values), but the placeholder map is
    never written under privacy_vault/maps/{key}.json and is dropped at run end.
    """
    import cloakbot.privacy.core.state.vault as vault

    captured_messages: list[list[dict]] = []

    async def chat_with_retry(*, messages, **kwargs):
        captured_messages.append(messages)
        return LLMResponse(content="Acknowledged <<SSN_1>>.", tool_calls=[])

    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    provider.generation = SimpleNamespace(max_tokens=4096, temperature=0.1, reasoning_effort=None)
    provider.estimate_prompt_tokens.return_value = (10_000, "test")
    provider.chat_with_retry = chat_with_retry

    loop = make_loop(tmp_path, provider=provider)
    maps_dir = tmp_path / "privacy_vault" / "maps"

    detection = DetectionResult(
        original_prompt="ssn 123-45-6789",
        entities=[GeneralEntity(text="123-45-6789", entity_type="ssn")],
        llm_raw_output="",
        latency_ms=1.0,
    )

    with patch(
        "cloakbot.privacy.runtime.pipeline.sanitize_input_with_detection",
        new=AsyncMock(
            return_value=("ssn <<SSN_1>>", True, detection.sensitive_entities, detection)
        ),
    ), patch(
        "cloakbot.privacy.runtime.pipeline.analyze_user_intent",
        new=AsyncMock(return_value=Intent.CHAT),
    ):
        msg = InboundMessage(
            channel="cli",
            sender_id="autonomous",
            chat_id="dreamrun",
            content="ssn 123-45-6789",
        )
        await loop._process_message(msg, session_key="dream:run-1", ephemeral=True)

    # Privacy is ON inside the ephemeral run: the provider sees the placeholder,
    # never the raw SSN.
    assert captured_messages, "provider was never called"
    payload = repr(captured_messages)
    assert "123-45-6789" not in payload, "RAW PII reached the provider in an ephemeral run"
    assert "<<SSN_1>>" in payload, "sanitized placeholder missing from ephemeral-run payload"

    # The ephemeral run's vault never touched disk and was dropped at run end.
    on_disk = sorted(p.name for p in maps_dir.iterdir()) if maps_dir.exists() else []
    assert on_disk == [], f"ephemeral run leaked a vault file to disk: {on_disk}"
    assert vault._ephemeral_cache == {}, "ephemeral scope was not dropped at run end"

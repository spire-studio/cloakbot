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

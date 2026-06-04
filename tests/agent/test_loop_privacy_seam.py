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
async def test_webui_turn_attaches_privacy_side_channel_payload(tmp_path) -> None:
    """[Cap F / W2] A webui turn rides the privacy report on the side-channel.

    The transparency report no longer rides the message content (include_report
    is False); instead `_state_respond` attaches the WebUIPrivacyPayload under
    OutboundMessage.metadata[WEBUI_PRIVACY_METADATA_KEY] so the privacy channel
    can fold the localhost-gated blob into _agent_ui.privacy + fire the standalone
    frames, and persists it for the GET /api/sessions/{key}/privacy route.
    """
    from cloakbot.privacy.webui.contracts import WEBUI_PRIVACY_METADATA_KEY
    from cloakbot.privacy.webui.history import load_webui_privacy_payloads

    async def chat_with_retry(*, messages, **kwargs):
        return LLMResponse(content="Noted, <<PERSON_1>>.", tool_calls=[])

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
            return_value=("My name is <<PERSON_1>>", True, detection.sensitive_entities, detection)
        ),
    ), patch(
        "cloakbot.privacy.runtime.pipeline.analyze_user_intent",
        new=AsyncMock(return_value=Intent.CHAT),
    ):
        msg = InboundMessage(
            channel="websocket",
            sender_id="user",
            chat_id="webuichat",
            content="My name is Alice",
            metadata={"webui": True},
        )
        outbound = await loop._process_message(msg, session_key="websocket:webuichat")

    assert outbound is not None, "no outbound produced for the webui turn"
    payload = outbound.metadata.get(WEBUI_PRIVACY_METADATA_KEY)
    assert payload is not None, "privacy side-channel payload not attached to webui outbound"
    assert payload.privacy_turn.turn_id  # well-formed payload
    assert payload.privacy_turn.remote_prompt == "My name is <<PERSON_1>>"

    # And it was persisted for HTTP rehydration.
    persisted = load_webui_privacy_payloads(tmp_path, "websocket:webuichat")
    assert persisted, "privacy payload not persisted for the rehydration route"


@pytest.mark.asyncio
async def test_non_webui_turn_has_no_side_channel_payload(tmp_path) -> None:
    """A non-webui channel turn carries no privacy overlay metadata (additive)."""
    from cloakbot.privacy.webui.contracts import WEBUI_PRIVACY_METADATA_KEY

    async def chat_with_retry(*, messages, **kwargs):
        return LLMResponse(content="Noted, <<PERSON_1>>.", tool_calls=[])

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
            return_value=("My name is <<PERSON_1>>", True, detection.sensitive_entities, detection)
        ),
    ), patch(
        "cloakbot.privacy.runtime.pipeline.analyze_user_intent",
        new=AsyncMock(return_value=Intent.CHAT),
    ):
        msg = InboundMessage(
            channel="cli",
            sender_id="user",
            chat_id="cliplain",
            content="My name is Alice",
        )
        outbound = await loop._process_message(msg, session_key="cli:cliplain")

    assert outbound is not None
    assert WEBUI_PRIVACY_METADATA_KEY not in outbound.metadata


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


@pytest.mark.asyncio
async def test_cron_keyed_ephemeral_run_writes_no_cron_map(tmp_path) -> None:
    """[Cap B / H1] A cron-keyed (``cron:{job.id}``) ephemeral run must NOT
    persist a placeholder map to privacy_vault/maps/cron_<id>.json.

    The cron reminder dispatch (cli/commands.py ``on_cron_job``) passes
    ``ephemeral=True``; this proves the loop side of that contract: the
    cron-keyed run mints placeholders in memory only and leaves no
    ``cron_<id>.json`` on disk.
    """
    import cloakbot.privacy.core.state.vault as vault

    captured_messages: list[list[dict]] = []

    async def chat_with_retry(*, messages, **kwargs):
        captured_messages.append(messages)
        return LLMResponse(content="Reminder for <<PERSON_1>>.", tool_calls=[])

    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    provider.generation = SimpleNamespace(max_tokens=4096, temperature=0.1, reasoning_effort=None)
    provider.estimate_prompt_tokens.return_value = (10_000, "test")
    provider.chat_with_retry = chat_with_retry

    loop = make_loop(tmp_path, provider=provider)
    maps_dir = tmp_path / "privacy_vault" / "maps"

    detection = DetectionResult(
        original_prompt="remind Dana Scully",
        entities=[GeneralEntity(text="Dana Scully", entity_type="person")],
        llm_raw_output="",
        latency_ms=1.0,
    )

    with patch(
        "cloakbot.privacy.runtime.pipeline.sanitize_input_with_detection",
        new=AsyncMock(
            return_value=("remind <<PERSON_1>>", True, detection.sensitive_entities, detection)
        ),
    ), patch(
        "cloakbot.privacy.runtime.pipeline.analyze_user_intent",
        new=AsyncMock(return_value=Intent.CHAT),
    ):
        msg = InboundMessage(
            channel="cli",
            sender_id="cron",
            chat_id="direct",
            content="remind Dana Scully",
        )
        await loop._process_message(msg, session_key="cron:job-7", ephemeral=True)

    payload = repr(captured_messages)
    assert "Dana Scully" not in payload, "RAW PII reached the provider in a cron run"
    assert "<<PERSON_1>>" in payload

    on_disk = sorted(p.name for p in maps_dir.iterdir()) if maps_dir.exists() else []
    assert "cron_job-7.json" not in on_disk, "cron run persisted a placeholder map to disk"
    assert on_disk == [], f"cron ephemeral run leaked a vault file to disk: {on_disk}"
    assert vault._ephemeral_cache == {}


def test_cron_and_heartbeat_dispatch_pass_ephemeral_true() -> None:
    """[Cap B / H1] Static guard: the cron reminder and heartbeat ``process_direct``
    call sites in ``on_cron_job`` pass ``ephemeral=True``.

    This is the exact gap the review found: without the flag, those autonomous
    runs would persist placeholder->original maps to disk
    (maps/cron_<id>.json / maps/heartbeat.json). Parsing the call AST makes the
    contract regression-proof without standing up the whole gateway closure.
    """
    import ast
    import inspect

    from cloakbot.cli import commands

    source = inspect.getsource(commands._run_gateway)
    tree = ast.parse(source)

    ephemeral_session_keys: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "process_direct"):
            continue
        kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}
        session_key = kwargs.get("session_key")
        ephemeral = kwargs.get("ephemeral")
        is_ephemeral = isinstance(ephemeral, ast.Constant) and ephemeral.value is True
        # Record the session_key shape for every process_direct that is ephemeral.
        if is_ephemeral and session_key is not None:
            if isinstance(session_key, ast.Constant):
                ephemeral_session_keys.add(str(session_key.value))
            elif isinstance(session_key, ast.JoinedStr):
                # f-string like f"cron:{job.id}" -> record its literal prefix.
                literal = "".join(
                    part.value for part in session_key.values if isinstance(part, ast.Constant)
                )
                ephemeral_session_keys.add(literal)

    assert "heartbeat" in ephemeral_session_keys, (
        "heartbeat process_direct must pass ephemeral=True"
    )
    assert any(k.startswith("cron:") for k in ephemeral_session_keys), (
        "cron reminder process_direct must pass ephemeral=True"
    )

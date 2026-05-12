from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cloakbot.agent.runner import AgentRunner, AgentRunSpec
from cloakbot.privacy.core.state.vault import get_map, save_map, set_vault_workspace
from cloakbot.privacy.core.types import GeneralEntity
from cloakbot.privacy.hooks.context import TurnContext
from cloakbot.privacy.runtime.tool_interceptor import ToolPrivacyInterceptor
from cloakbot.privacy.tool_models import ToolApprovalRequiredError
from cloakbot.providers.base import LLMResponse, ToolCallRequest
from cloakbot.tool_privacy import ToolPrivacyClass


def _entity(text: str, entity_type: str) -> GeneralEntity:
    return GeneralEntity(text=text, entity_type=entity_type)


@pytest.mark.asyncio
async def test_tool_interceptor_restores_placeholder_arguments_before_execution(tmp_path) -> None:
    set_vault_workspace(tmp_path)
    smap = get_map("cli:test")
    path_placeholder, _ = smap.get_or_create_placeholder("/tmp/private.txt", "PRIVATE_URL", turn_id="turn-old")
    person_placeholder, _ = smap.get_or_create_placeholder("Alice", "PERSON", turn_id="turn-old")
    save_map("cli:test", smap)

    ctx = TurnContext(session_key="cli:test", turn_id="turn-1", raw_input="read my file")
    interceptor = ToolPrivacyInterceptor(ctx)
    tool_call = ToolCallRequest(
        id="call_1",
        name="read_file",
        arguments={"path": path_placeholder, "filters": [f"owner={person_placeholder}"]},
    )

    prepared = await interceptor.prepare_tool_call(
        tool_call,
        privacy_class=ToolPrivacyClass.LOCAL,
    )

    assert prepared.arguments == {"path": "/tmp/private.txt", "filters": ["owner=Alice"]}
    assert tool_call.arguments == {"path": path_placeholder, "filters": [f"owner={person_placeholder}"]}


@pytest.mark.asyncio
async def test_tool_interceptor_sanitizes_text_result_and_records_entities() -> None:
    ctx = TurnContext(session_key="cli:test", turn_id="turn-1", raw_input="inspect tool output")
    interceptor = ToolPrivacyInterceptor(ctx)
    tool_call = ToolCallRequest(
        id="call_1",
        name="grep",
        arguments={"pattern": "<<PERSON_1>>"},
    )

    async def fake_sanitize(text: str, _session_key: str, *, turn_id: str | None = None):
        assert turn_id == "turn-1"
        return text.replace("Alice", "<<PERSON_1>>"), True, [_entity("Alice", "person")]

    with patch(
        "cloakbot.privacy.runtime.tool_interceptor.sanitize_tool_output",
        new=AsyncMock(side_effect=fake_sanitize),
    ):
        sanitized = await interceptor.sanitize_tool_result(
            tool_call,
            "Owner: Alice",
            privacy_class=ToolPrivacyClass.LOCAL,
        )

    assert sanitized == "Owner: <<PERSON_1>>"
    assert ctx.tool_output_entities == [_entity("Alice", "person")]
    assert ctx.tool_results[0].tool_name == "grep"
    assert ctx.tool_results[0].remote_arguments == {"pattern": "<<PERSON_1>>"}
    assert ctx.tool_results[0].sanitized_output == "Owner: <<PERSON_1>>"
    assert ctx.tool_results[0].was_sanitized is True


@pytest.mark.asyncio
async def test_external_tool_input_with_sensitive_data_requires_approval() -> None:
    ctx = TurnContext(session_key="cli:test", turn_id="turn-1", raw_input="search")
    interceptor = ToolPrivacyInterceptor(ctx)
    tool_call = ToolCallRequest(
        id="call_1",
        name="web_search",
        arguments={"query": "Alice SSN case"},
    )

    async def fake_sanitize(text: str, _session_key: str, *, turn_id: str | None = None):
        assert turn_id == "turn-1"
        return text.replace("Alice", "<<PERSON_1>>"), True, [_entity("Alice", "person")]

    with patch(
        "cloakbot.privacy.runtime.tool_interceptor.sanitize_tool_output",
        new=AsyncMock(side_effect=fake_sanitize),
    ), pytest.raises(ToolApprovalRequiredError) as raised:
        await interceptor.prepare_tool_call(
            tool_call,
            privacy_class=ToolPrivacyClass.EXTERNAL,
        )

    request = raised.value.request
    assert request.tool_name == "web_search"
    assert request.privacy_class is ToolPrivacyClass.EXTERNAL
    assert request.remote_arguments == {"query": "<<PERSON_1>> SSN case"}
    assert request.restored_arguments == {"query": "Alice SSN case"}
    assert ctx.tool_input_entities == [_entity("Alice", "person")]
    assert ctx.tool_approvals == [request]


@pytest.mark.asyncio
async def test_tool_interceptor_sanitizes_nested_structured_result() -> None:
    ctx = TurnContext(session_key="cli:test", turn_id="turn-1", raw_input="inspect")
    interceptor = ToolPrivacyInterceptor(ctx)
    tool_call = ToolCallRequest(id="call_1", name="mcp_lookup", arguments={})

    async def fake_sanitize(text: str, _session_key: str, *, turn_id: str | None = None):
        return text.replace("Alice", "<<PERSON_1>>"), "Alice" in text, (
            [_entity("Alice", "person")] if "Alice" in text else []
        )

    with patch(
        "cloakbot.privacy.runtime.tool_interceptor.sanitize_tool_output",
        new=AsyncMock(side_effect=fake_sanitize),
    ):
        sanitized = await interceptor.sanitize_tool_result(
            tool_call,
            {"rows": [{"owner": "Alice"}, {"owner": "public"}]},
            privacy_class=ToolPrivacyClass.EXTERNAL,
        )

    assert sanitized == {"rows": [{"owner": "<<PERSON_1>>"}, {"owner": "public"}]}
    assert ctx.tool_results[0].sanitized_output == "{'rows': [{'owner': '<<PERSON_1>>'}, {'owner': 'public'}]}"


@pytest.mark.asyncio
async def test_runner_restores_tool_input_and_sanitizes_output_before_next_model_call(tmp_path) -> None:
    provider = MagicMock()
    captured_second_call: list[dict] = []
    call_count = {"n": 0}

    async def chat_with_retry(*, messages, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return LLMResponse(
                content="reading",
                tool_calls=[
                    ToolCallRequest(
                        id="call_1",
                        name="read_file",
                        arguments={"path": "<<PRIVATE_URL_1>>"},
                    )
                ],
            )
        captured_second_call[:] = messages
        return LLMResponse(content="done", tool_calls=[])

    async def fake_remap(text: str, _session_key: str) -> str:
        return text.replace("<<PRIVATE_URL_1>>", "/tmp/private.txt")

    async def fake_sanitize(text: str, _session_key: str, *, turn_id: str | None = None):
        return text.replace("Alice", "<<PERSON_1>>"), True, [_entity("Alice", "person")]

    provider.chat_with_retry = chat_with_retry
    tools = MagicMock()
    tools.get_definitions.return_value = []
    tools.prepare_call = lambda name, args: (None, args, None)
    tools.execute = AsyncMock(return_value="Owner: Alice")
    ctx = TurnContext(session_key="cli:test", turn_id="turn-1", raw_input="read file")

    with patch(
        "cloakbot.privacy.runtime.tool_interceptor.remap_response",
        new=AsyncMock(side_effect=fake_remap),
    ), patch(
        "cloakbot.privacy.runtime.tool_interceptor.sanitize_tool_output",
        new=AsyncMock(side_effect=fake_sanitize),
    ):
        result = await AgentRunner(provider).run(
            AgentRunSpec(
                initial_messages=[{"role": "user", "content": "read <<PRIVATE_URL_1>>"}],
                tools=tools,
                model="test-model",
                max_iterations=2,
                max_tool_result_chars=16_000,
                workspace=tmp_path,
                session_key="cli:test",
                tool_privacy_interceptor=ToolPrivacyInterceptor(ctx),
            )
        )

    assert result.final_content == "done"
    tools.execute.assert_awaited_once_with("read_file", {"path": "/tmp/private.txt"})
    tool_message = next(msg for msg in captured_second_call if msg.get("role") == "tool")
    assert tool_message["content"] == "Owner: <<PERSON_1>>"
    assert "Alice" not in tool_message["content"]
    assert ctx.tool_output_entities == [_entity("Alice", "person")]


@pytest.mark.asyncio
async def test_runner_sanitizes_large_tool_output_before_persisting(tmp_path) -> None:
    provider = MagicMock()
    call_count = {"n": 0}

    async def chat_with_retry(*, messages, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return LLMResponse(
                content="reading",
                tool_calls=[ToolCallRequest(id="call_big", name="read_file", arguments={"path": "x"})],
            )
        return LLMResponse(content="done", tool_calls=[])

    async def fake_sanitize(text: str, _session_key: str, *, turn_id: str | None = None):
        return text.replace("Alice", "<<PERSON_1>>"), True, [_entity("Alice", "person")]

    provider.chat_with_retry = chat_with_retry
    tools = MagicMock()
    tools.get_definitions.return_value = []
    tools.prepare_call = lambda name, args: (None, args, None)
    tools.execute = AsyncMock(return_value="Alice " + ("x" * 200))
    ctx = TurnContext(session_key="cli:test", turn_id="turn-1", raw_input="read file")

    with patch(
        "cloakbot.privacy.runtime.tool_interceptor.sanitize_tool_output",
        new=AsyncMock(side_effect=fake_sanitize),
    ):
        await AgentRunner(provider).run(
            AgentRunSpec(
                initial_messages=[{"role": "user", "content": "read file"}],
                tools=tools,
                model="test-model",
                max_iterations=2,
                max_tool_result_chars=50,
                workspace=tmp_path,
                session_key="cli:test",
                tool_privacy_interceptor=ToolPrivacyInterceptor(ctx),
            )
        )

    persisted = tmp_path / ".cloakbot" / "tool-results" / "cli_test" / "call_big.txt"
    assert persisted.exists()
    assert "Alice" not in persisted.read_text(encoding="utf-8")
    assert "<<PERSON_1>>" in persisted.read_text(encoding="utf-8")

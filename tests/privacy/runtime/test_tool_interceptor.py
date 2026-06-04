from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cloakbot.agent.runner import AgentRunner, AgentRunSpec
from cloakbot.privacy.core.state.vault import get_map, save_map, set_vault_workspace
from cloakbot.privacy.core.types import GeneralEntity
from cloakbot.privacy.hooks.context import TurnContext
from cloakbot.privacy.runtime.tool_interceptor import ToolPrivacyInterceptor
from cloakbot.privacy.tool_models import ToolApprovalRequiredError
from cloakbot.privacy.visual_redaction import (
    VisualBlocksResult,
    VisualPrivacyRedaction,
    VisualVaultEntry,
)
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
async def test_tool_interceptor_rewrites_web_fetch_local_path_to_read_file(tmp_path) -> None:
    set_vault_workspace(tmp_path)
    smap = get_map("cli:test")
    path_placeholder, _ = smap.get_or_create_placeholder(
        "/Users/me/invoice.jpg",
        "PRIVATE_URL",
        turn_id="turn-old",
    )
    save_map("cli:test", smap)

    ctx = TurnContext(session_key="cli:test", turn_id="turn-1", raw_input="summarize invoice")
    interceptor = ToolPrivacyInterceptor(ctx)
    tool_call = ToolCallRequest(
        id="call_1",
        name="web_fetch",
        arguments={"url": path_placeholder, "extractMode": "markdown", "maxChars": 8000},
    )

    prepared = await interceptor.prepare_tool_call(
        tool_call,
        privacy_class=ToolPrivacyClass.EXTERNAL,
    )

    assert prepared.name == "read_file"
    assert prepared.arguments == {"path": "/Users/me/invoice.jpg"}
    assert ctx.tool_approvals == []


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
async def test_tool_interceptor_redacts_visual_tool_result_before_model_reuse(tmp_path) -> None:
    set_vault_workspace(tmp_path)
    ctx = TurnContext(session_key="cli:test", turn_id="turn-1", raw_input="inspect invoice")
    interceptor = ToolPrivacyInterceptor(ctx)
    tool_call = ToolCallRequest(id="call_img", name="read_file", arguments={"path": "<<PRIVATE_URL_1>>"})
    raw_blocks = [
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,cmF3LWltYWdl"},
            "_meta": {"path": "/tmp/invoice.png"},
        },
        {"type": "text", "text": "(Image file: /tmp/invoice.png)"},
    ]
    redacted_blocks = [
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,cmVkYWN0ZWQ="},
            "_meta": {"path": "/tmp/invoice.png"},
        },
        {"type": "text", "text": "(Image file: /tmp/invoice.png)"},
    ]
    visual_record = VisualPrivacyRedaction(
        sourcePath="/tmp/invoice.png",
        status="redacted",
        detectedItems=2,
        redactionBoxes=3,
        labels=["invoice_number", "amount"],
    )

    redacted_image_path = tmp_path / "redacted_image.png"
    redacted_image_path.write_bytes(b"\x89PNGredacted")
    visual_result = VisualBlocksResult(
        redacted_blocks=redacted_blocks,
        sanitized_text="Invoice #ABC-123\nTotal $9.99",
        modified=True,
        entities=[],
        visual_redactions=[visual_record],
        vault_entries=[
            VisualVaultEntry(
                kind="redacted_image",
                path=str(redacted_image_path),
                media_type="image/png",
            )
        ],
        omitted_count=0,
        image_count=1,
    )

    with patch(
        "cloakbot.privacy.runtime.tool_interceptor.process_visual_blocks",
        new=AsyncMock(return_value=visual_result),
    ):
        sanitized = await interceptor.sanitize_tool_result(
            tool_call,
            raw_blocks,
            privacy_class=ToolPrivacyClass.LOCAL,
        )

    assert sanitized == "Invoice #ABC-123\nTotal $9.99"
    assert ctx.tool_results[0].was_sanitized is True
    assert ctx.tool_results[0].visual_redactions == [visual_record]
    assert [artifact.kind for artifact in ctx.tool_results[0].vault_artifacts] == [
        "redacted_image",
        "sanitized_text",
    ]
    follow_up = interceptor.take_follow_up_messages(tool_call.id)
    assert len(follow_up) == 1
    assert follow_up[0]["role"] == "user"
    assert follow_up[0]["content"][1]["type"] == "image_url"


@pytest.mark.asyncio
async def test_runner_converts_visual_tool_result_to_text_before_next_model_call(tmp_path) -> None:
    set_vault_workspace(tmp_path)
    provider = MagicMock()
    captured_second_call: list[dict] = []
    call_count = {"n": 0}

    async def chat_with_retry(*, messages, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return LLMResponse(
                content="reading",
                tool_calls=[ToolCallRequest(id="call_img", name="read_file", arguments={"path": "invoice.png"})],
            )
        captured_second_call[:] = messages
        return LLMResponse(content="done", tool_calls=[])

    provider.chat_with_retry = chat_with_retry
    tools = MagicMock()
    tools.get_definitions.return_value = []
    tools.prepare_call = lambda name, args: (None, args, None)
    tools.execute = AsyncMock(return_value=[
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,cmF3LWltYWdl"},
            "_meta": {"path": str(tmp_path / "invoice.png")},
        },
        {"type": "text", "text": f"(Image file: {tmp_path / 'invoice.png'})"},
    ])
    ctx = TurnContext(session_key="cli:test", turn_id="turn-1", raw_input="read invoice")
    visual_record = VisualPrivacyRedaction(
        sourcePath=str(tmp_path / "invoice.png"),
        status="redacted",
        detectedItems=2,
        redactionBoxes=3,
        labels=["invoice_number", "amount"],
    )

    redacted_image_path = tmp_path / "redacted_image.png"
    redacted_image_path.write_bytes(b"\x89PNGredacted")
    image_block = {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64,cmVkYWN0ZWQ="},
        "_meta": {"path": str(tmp_path / "invoice.png")},
    }
    visual_result = VisualBlocksResult(
        redacted_blocks=[image_block, {"type": "text", "text": f"(Image file: {tmp_path / 'invoice.png'})"}],
        sanitized_text="Invoice #<<INVOICE_NUMBER_1>>\nTotal $9.99",
        modified=True,
        entities=[_entity("ABC-123", "invoice_number")],
        visual_redactions=[visual_record],
        vault_entries=[
            VisualVaultEntry(
                kind="redacted_image",
                path=str(redacted_image_path),
                media_type="image/png",
            )
        ],
        omitted_count=0,
        image_count=1,
    )

    with patch(
        "cloakbot.privacy.runtime.tool_interceptor.process_visual_blocks",
        new=AsyncMock(return_value=visual_result),
    ):
        result = await AgentRunner(provider).run(
            AgentRunSpec(
                initial_messages=[{"role": "user", "content": "read invoice"}],
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
    tool_message = next(msg for msg in captured_second_call if msg.get("role") == "tool")
    assert tool_message["content"] == "Invoice #<<INVOICE_NUMBER_1>>\nTotal $9.99"
    assert isinstance(tool_message["content"], str)
    follow_up = next(
        msg for msg in captured_second_call
        if msg.get("role") == "user" and isinstance(msg.get("content"), list)
    )
    assert isinstance(follow_up["content"], list)
    assert follow_up["content"][1]["type"] == "image_url"
    assert ctx.tool_results[0].visual_redactions == [visual_record]


@pytest.mark.asyncio
async def test_runner_restores_tool_input_and_sanitizes_output_before_next_model_call(tmp_path) -> None:
    set_vault_workspace(tmp_path)
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
    assert [artifact.kind for artifact in ctx.tool_results[0].vault_artifacts] == ["sanitized_text"]


@pytest.mark.asyncio
async def test_runner_executes_rewritten_local_web_fetch_as_read_file(tmp_path) -> None:
    set_vault_workspace(tmp_path)
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
                        name="web_fetch",
                        arguments={"url": "<<PRIVATE_URL_1>>"},
                    )
                ],
            )
        captured_second_call[:] = messages
        return LLMResponse(content="done", tool_calls=[])

    async def fake_remap(text: str, _session_key: str) -> str:
        return text.replace("<<PRIVATE_URL_1>>", str(tmp_path / "invoice.jpg"))

    async def fake_sanitize(text: str, _session_key: str, *, turn_id: str | None = None):
        return text, False, []

    provider.chat_with_retry = chat_with_retry
    tools = MagicMock()
    tools.get_definitions.return_value = []
    tools.prepare_call = lambda name, args: (None, args, None)
    tools.execute = AsyncMock(return_value="Invoice #ABC-123")
    ctx = TurnContext(session_key="cli:test", turn_id="turn-1", raw_input="read invoice")

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
    tools.execute.assert_awaited_once_with("read_file", {"path": str(tmp_path / "invoice.jpg")})
    assert ctx.tool_approvals == []
    assert ctx.tool_results[0].tool_name == "read_file"
    assert [artifact.kind for artifact in ctx.tool_results[0].vault_artifacts] == ["sanitized_text"]
    tool_message = next(msg for msg in captured_second_call if msg.get("role") == "tool")
    assert tool_message["name"] == "web_fetch"
    assert tool_message["content"] == "Invoice #ABC-123"


@pytest.mark.asyncio
async def test_runner_sanitizes_large_tool_output_before_persisting(tmp_path) -> None:
    provider = MagicMock()
    call_count = {"n": 0}

    async def chat_with_retry(*, messages, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return LLMResponse(
                content="reading",
                # read_file is offload-exempt upstream (binds its own output); use a
                # generic tool name so the large-output offload+sanitize path runs.
                tool_calls=[ToolCallRequest(id="call_big", name="fetch_data", arguments={"path": "x"})],
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


@pytest.mark.asyncio
async def test_tool_interceptor_skips_detection_for_pure_placeholder_strings(tmp_path) -> None:
    """Pre-tokenised strings short-circuit without invoking the detector.

    The interceptor used to re-run the LLM-backed PII detector on
    strings that were entirely ``<<…_N>>`` placeholders — wasted
    compute and a vector for nested-token corruption (a regex matching
    inside ``<<NAME_12>>``).
    """
    set_vault_workspace(tmp_path)
    ctx = TurnContext(session_key="cli:test", turn_id="turn-1", raw_input="inspect")
    interceptor = ToolPrivacyInterceptor(ctx)
    tool_call = ToolCallRequest(id="call_skip", name="grep", arguments={})

    with patch(
        "cloakbot.privacy.runtime.tool_interceptor.sanitize_tool_output",
        new=AsyncMock(side_effect=AssertionError("must not be called for pure placeholders")),
    ):
        sanitized = await interceptor.sanitize_tool_result(
            tool_call,
            "<<PERSON_1>>  <<EMAIL_2>>",
            privacy_class=ToolPrivacyClass.LOCAL,
        )

    assert sanitized == "<<PERSON_1>>  <<EMAIL_2>>"
    assert ctx.tool_results[0].was_sanitized is False


@pytest.mark.asyncio
async def test_tool_interceptor_fail_closes_on_chunked_detection_failure(tmp_path) -> None:
    """A failed chunk on a large tool output triggers fail-closed omit."""
    set_vault_workspace(tmp_path)
    ctx = TurnContext(session_key="cli:test", turn_id="turn-1", raw_input="x")
    interceptor = ToolPrivacyInterceptor(ctx)
    tool_call = ToolCallRequest(id="call_big", name="read_file", arguments={"path": "x"})

    big_payload = "Block 1.\n\n" + ("A" * 8000) + "\n\nTrailing."

    async def fake_chunked(
        text: str,
        _session_key: str,
        *,
        tool_name: str,
        turn_id: str | None = None,
        content_type=None,
    ):
        # Pretend chunk 2 failed. The interceptor must drop the payload.
        return text, False, [], True

    with patch(
        "cloakbot.privacy.runtime.tool_interceptor.sanitize_tool_output_chunked",
        new=AsyncMock(side_effect=fake_chunked),
    ):
        sanitized = await interceptor.sanitize_tool_result(
            tool_call,
            big_payload,
            privacy_class=ToolPrivacyClass.LOCAL,
        )

    assert isinstance(sanitized, str)
    assert "tool output omitted" in sanitized
    assert "read_file" in sanitized
    assert "A" * 100 not in sanitized
    assert ctx.tool_results[0].was_sanitized is True


@pytest.mark.asyncio
async def test_local_tool_with_high_severity_arg_requires_approval_when_opt_in(
    tmp_path, monkeypatch
) -> None:
    """Severity-driven LOCAL approval is opt-in via env and trips on Severity.HIGH.

    Default behaviour for LOCAL tools is unchanged (no approval).
    Setting ``CLOAKBOT_APPROVAL_HIGH_SEVERITY_LOCAL=true`` raises the
    bar — even local tool calls that touch SSNs / credentials need a
    user prompt before they run.
    """
    set_vault_workspace(tmp_path)
    monkeypatch.setenv("CLOAKBOT_APPROVAL_HIGH_SEVERITY_LOCAL", "true")

    ctx = TurnContext(session_key="cli:test", turn_id="turn-1", raw_input="read")
    interceptor = ToolPrivacyInterceptor(ctx)
    tool_call = ToolCallRequest(
        id="call_local",
        name="read_file",
        arguments={"path": "/tmp/contains-ssn.txt"},
    )

    high_severity = _entity("999-77-1234", "identifier")  # Severity.HIGH per registry

    async def fake_sanitize(text, _session_key, *, turn_id=None):
        return text, True, [high_severity]

    with patch(
        "cloakbot.privacy.runtime.tool_interceptor.sanitize_tool_output",
        new=AsyncMock(side_effect=fake_sanitize),
    ), pytest.raises(ToolApprovalRequiredError) as raised:
        await interceptor.prepare_tool_call(
            tool_call, privacy_class=ToolPrivacyClass.LOCAL,
        )

    request = raised.value.request
    assert request.tool_name == "read_file"
    assert request.privacy_class is ToolPrivacyClass.LOCAL
    assert ctx.tool_approvals == [request]


@pytest.mark.asyncio
async def test_local_tool_with_high_severity_arg_passes_without_opt_in(tmp_path) -> None:
    """Without the env var, LOCAL tools never raise approval requests.

    Locks the default-permissive behaviour so users who don't set the
    opt-in don't see new approval prompts after this change.
    """
    set_vault_workspace(tmp_path)
    ctx = TurnContext(session_key="cli:test", turn_id="turn-1", raw_input="read")
    interceptor = ToolPrivacyInterceptor(ctx)
    tool_call = ToolCallRequest(
        id="call_local",
        name="read_file",
        arguments={"path": "/tmp/contains-ssn.txt"},
    )

    prepared = await interceptor.prepare_tool_call(
        tool_call, privacy_class=ToolPrivacyClass.LOCAL,
    )

    assert prepared.arguments == {"path": "/tmp/contains-ssn.txt"}
    assert ctx.tool_approvals == []

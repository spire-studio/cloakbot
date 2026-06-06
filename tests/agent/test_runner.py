"""Tests for the shared agent runner and its integration contracts."""

from __future__ import annotations

import asyncio
import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cloakbot.agent.tools.base import Tool
from cloakbot.config.schema import AgentDefaults
from cloakbot.providers.base import LLMResponse, ToolCallRequest

_MAX_TOOL_RESULT_CHARS = AgentDefaults().max_tool_result_chars


def _make_loop(tmp_path):
    from cloakbot.agent.loop import AgentLoop
    from cloakbot.bus.queue import MessageBus

    bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    with patch("cloakbot.agent.loop.ContextBuilder"), \
         patch("cloakbot.agent.loop.SessionManager"), \
         patch("cloakbot.agent.loop.SubagentManager") as MockSubMgr:
        MockSubMgr.return_value.cancel_by_session = AsyncMock(return_value=0)
        loop = AgentLoop(bus=bus, provider=provider, workspace=tmp_path)
    return loop


@pytest.mark.asyncio
async def test_runner_preserves_reasoning_fields_and_tool_results():
    from cloakbot.agent.runner import AgentRunner, AgentRunSpec

    provider = MagicMock()
    captured_second_call: list[dict] = []
    call_count = {"n": 0}

    async def chat_with_retry(*, messages, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return LLMResponse(
                content="thinking",
                tool_calls=[ToolCallRequest(id="call_1", name="list_dir", arguments={"path": "."})],
                reasoning_content="hidden reasoning",
                thinking_blocks=[{"type": "thinking", "thinking": "step"}],
                usage={"prompt_tokens": 5, "completion_tokens": 3},
            )
        captured_second_call[:] = messages
        return LLMResponse(content="done", tool_calls=[], usage={})

    provider.chat_with_retry = chat_with_retry
    tools = MagicMock()
    tools.get_definitions.return_value = []
    tools.execute = AsyncMock(return_value="tool result")

    runner = AgentRunner(provider)
    result = await runner.run(AgentRunSpec(
        initial_messages=[
            {"role": "system", "content": "system"},
            {"role": "user", "content": "do task"},
        ],
        tools=tools,
        model="test-model",
        max_iterations=3,
        max_tool_result_chars=_MAX_TOOL_RESULT_CHARS,
    ))

    assert result.final_content == "done"
    assert result.tools_used == ["list_dir"]
    assert result.tool_events == [
        {"name": "list_dir", "status": "ok", "detail": "tool result"}
    ]

    assistant_messages = [
        msg for msg in captured_second_call
        if msg.get("role") == "assistant" and msg.get("tool_calls")
    ]
    assert len(assistant_messages) == 1
    assert assistant_messages[0]["reasoning_content"] == "hidden reasoning"
    assert assistant_messages[0]["thinking_blocks"] == [{"type": "thinking", "thinking": "step"}]
    assert any(
        msg.get("role") == "tool" and msg.get("content") == "tool result"
        for msg in captured_second_call
    )


@pytest.mark.asyncio
async def test_runner_calls_hooks_in_order():
    from cloakbot.agent.hook import AgentHook, AgentHookContext
    from cloakbot.agent.runner import AgentRunner, AgentRunSpec

    provider = MagicMock()
    call_count = {"n": 0}
    events: list[tuple] = []

    async def chat_with_retry(**kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return LLMResponse(
                content="thinking",
                tool_calls=[ToolCallRequest(id="call_1", name="list_dir", arguments={"path": "."})],
            )
        return LLMResponse(content="done", tool_calls=[], usage={})

    provider.chat_with_retry = chat_with_retry
    tools = MagicMock()
    tools.get_definitions.return_value = []
    tools.execute = AsyncMock(return_value="tool result")

    class RecordingHook(AgentHook):
        async def before_iteration(self, context: AgentHookContext) -> None:
            events.append(("before_iteration", context.iteration))

        async def before_execute_tools(self, context: AgentHookContext) -> None:
            events.append((
                "before_execute_tools",
                context.iteration,
                [tc.name for tc in context.tool_calls],
            ))

        async def after_iteration(self, context: AgentHookContext) -> None:
            events.append((
                "after_iteration",
                context.iteration,
                context.final_content,
                list(context.tool_results),
                list(context.tool_events),
                context.stop_reason,
            ))

        def finalize_content(self, context: AgentHookContext, content: str | None) -> str | None:
            events.append(("finalize_content", context.iteration, content))
            return content.upper() if content else content

    runner = AgentRunner(provider)
    result = await runner.run(AgentRunSpec(
        initial_messages=[],
        tools=tools,
        model="test-model",
        max_iterations=3,
        max_tool_result_chars=_MAX_TOOL_RESULT_CHARS,
        hook=RecordingHook(),
    ))

    assert result.final_content == "DONE"
    assert events == [
        ("before_iteration", 0),
        ("before_execute_tools", 0, ["list_dir"]),
        (
            "after_iteration",
            0,
            None,
            ["tool result"],
            [{"name": "list_dir", "status": "ok", "detail": "tool result"}],
            None,
        ),
        ("before_iteration", 1),
        ("finalize_content", 1, "done"),
        ("after_iteration", 1, "DONE", [], [], "completed"),
    ]


@pytest.mark.asyncio
async def test_runner_streaming_hook_receives_deltas_and_end_signal():
    from cloakbot.agent.hook import AgentHook, AgentHookContext
    from cloakbot.agent.runner import AgentRunner, AgentRunSpec

    provider = MagicMock()
    streamed: list[str] = []
    endings: list[bool] = []

    async def chat_stream_with_retry(*, on_content_delta, **kwargs):
        await on_content_delta("he")
        await on_content_delta("llo")
        return LLMResponse(content="hello", tool_calls=[], usage={})

    provider.chat_stream_with_retry = chat_stream_with_retry
    provider.chat_with_retry = AsyncMock()
    tools = MagicMock()
    tools.get_definitions.return_value = []

    class StreamingHook(AgentHook):
        def wants_streaming(self) -> bool:
            return True

        async def on_stream(self, context: AgentHookContext, delta: str) -> None:
            streamed.append(delta)

        async def on_stream_end(self, context: AgentHookContext, *, resuming: bool) -> None:
            endings.append(resuming)

    runner = AgentRunner(provider)
    result = await runner.run(AgentRunSpec(
        initial_messages=[],
        tools=tools,
        model="test-model",
        max_iterations=1,
        max_tool_result_chars=_MAX_TOOL_RESULT_CHARS,
        hook=StreamingHook(),
    ))

    assert result.final_content == "hello"
    assert streamed == ["he", "llo"]
    assert endings == [False]
    provider.chat_with_retry.assert_not_awaited()


@pytest.mark.asyncio
async def test_runner_returns_max_iterations_fallback():
    from cloakbot.agent.runner import AgentRunner, AgentRunSpec

    provider = MagicMock()
    provider.chat_with_retry = AsyncMock(return_value=LLMResponse(
        content="still working",
        tool_calls=[ToolCallRequest(id="call_1", name="list_dir", arguments={"path": "."})],
    ))
    tools = MagicMock()
    tools.get_definitions.return_value = []
    tools.execute = AsyncMock(return_value="tool result")

    runner = AgentRunner(provider)
    result = await runner.run(AgentRunSpec(
        initial_messages=[],
        tools=tools,
        model="test-model",
        max_iterations=2,
        max_tool_result_chars=_MAX_TOOL_RESULT_CHARS,
    ))

    assert result.stop_reason == "max_iterations"
    assert result.final_content == (
        "I reached the maximum number of tool call iterations (2) "
        "without completing the task. You can try breaking the task into smaller steps."
    )
    assert result.messages[-1]["role"] == "assistant"
    assert result.messages[-1]["content"] == result.final_content

@pytest.mark.asyncio
async def test_runner_returns_structured_tool_error():
    from cloakbot.agent.runner import AgentRunner, AgentRunSpec

    provider = MagicMock()
    provider.chat_with_retry = AsyncMock(return_value=LLMResponse(
        content="working",
        tool_calls=[ToolCallRequest(id="call_1", name="list_dir", arguments={})],
    ))
    tools = MagicMock()
    tools.get_definitions.return_value = []
    tools.execute = AsyncMock(side_effect=RuntimeError("boom"))

    runner = AgentRunner(provider)

    result = await runner.run(AgentRunSpec(
        initial_messages=[],
        tools=tools,
        model="test-model",
        max_iterations=2,
        max_tool_result_chars=_MAX_TOOL_RESULT_CHARS,
        fail_on_tool_error=True,
    ))

    assert result.stop_reason == "tool_error"
    assert result.error == "Error: RuntimeError: boom"
    assert result.tool_events == [
        {"name": "list_dir", "status": "error", "detail": "boom"}
    ]


@pytest.mark.asyncio
async def test_runner_persists_large_tool_results_for_follow_up_calls(tmp_path):
    from cloakbot.agent.runner import AgentRunner, AgentRunSpec

    provider = MagicMock()
    captured_second_call: list[dict] = []
    call_count = {"n": 0}

    async def chat_with_retry(*, messages, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return LLMResponse(
                content="working",
                tool_calls=[ToolCallRequest(id="call_big", name="list_dir", arguments={"path": "."})],
                usage={"prompt_tokens": 5, "completion_tokens": 3},
            )
        captured_second_call[:] = messages
        return LLMResponse(content="done", tool_calls=[], usage={})

    provider.chat_with_retry = chat_with_retry
    tools = MagicMock()
    tools.get_definitions.return_value = []
    tools.execute = AsyncMock(return_value="x" * 20_000)

    runner = AgentRunner(provider)
    result = await runner.run(AgentRunSpec(
        initial_messages=[{"role": "user", "content": "do task"}],
        tools=tools,
        model="test-model",
        max_iterations=2,
        workspace=tmp_path,
        session_key="test:runner",
        max_tool_result_chars=2048,
    ))

    assert result.final_content == "done"
    tool_message = next(msg for msg in captured_second_call if msg.get("role") == "tool")
    assert "[tool output persisted]" in tool_message["content"]
    assert "tool-results" in tool_message["content"]
    assert (tmp_path / ".cloakbot" / "tool-results" / "test_runner" / "call_big.txt").exists()


def test_persist_tool_result_prunes_old_session_buckets(tmp_path):
    from cloakbot.utils.helpers import maybe_persist_tool_result

    root = tmp_path / ".cloakbot" / "tool-results"
    old_bucket = root / "old_session"
    recent_bucket = root / "recent_session"
    old_bucket.mkdir(parents=True)
    recent_bucket.mkdir(parents=True)
    (old_bucket / "old.txt").write_text("old", encoding="utf-8")
    (recent_bucket / "recent.txt").write_text("recent", encoding="utf-8")

    stale = time.time() - (8 * 24 * 60 * 60)
    os.utime(old_bucket, (stale, stale))
    os.utime(old_bucket / "old.txt", (stale, stale))

    persisted = maybe_persist_tool_result(
        tmp_path,
        "current:session",
        "call_big",
        "x" * 5000,
        max_chars=64,
    )

    assert "[tool output persisted]" in persisted
    assert not old_bucket.exists()
    assert recent_bucket.exists()
    assert (root / "current_session" / "call_big.txt").exists()


def test_persist_tool_result_leaves_no_temp_files(tmp_path):
    from cloakbot.utils.helpers import maybe_persist_tool_result

    root = tmp_path / ".cloakbot" / "tool-results"
    maybe_persist_tool_result(
        tmp_path,
        "current:session",
        "call_big",
        "x" * 5000,
        max_chars=64,
    )

    assert (root / "current_session" / "call_big.txt").exists()
    assert list((root / "current_session").glob("*.tmp")) == []




@pytest.mark.asyncio
async def test_runner_replaces_empty_tool_result_with_marker():
    from cloakbot.agent.runner import AgentRunner, AgentRunSpec

    provider = MagicMock()
    captured_second_call: list[dict] = []
    call_count = {"n": 0}

    async def chat_with_retry(*, messages, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return LLMResponse(
                content="working",
                tool_calls=[ToolCallRequest(id="call_1", name="noop", arguments={})],
                usage={},
            )
        captured_second_call[:] = messages
        return LLMResponse(content="done", tool_calls=[], usage={})

    provider.chat_with_retry = chat_with_retry
    tools = MagicMock()
    tools.get_definitions.return_value = []
    tools.execute = AsyncMock(return_value="")

    runner = AgentRunner(provider)
    result = await runner.run(AgentRunSpec(
        initial_messages=[{"role": "user", "content": "do task"}],
        tools=tools,
        model="test-model",
        max_iterations=2,
        max_tool_result_chars=_MAX_TOOL_RESULT_CHARS,
    ))

    assert result.final_content == "done"
    tool_message = next(msg for msg in captured_second_call if msg.get("role") == "tool")
    assert tool_message["content"] == "(noop completed with no output)"


@pytest.mark.asyncio
async def test_runner_uses_raw_messages_when_context_governance_fails():
    from cloakbot.agent.runner import AgentRunner, AgentRunSpec

    provider = MagicMock()
    captured_messages: list[dict] = []

    async def chat_with_retry(*, messages, **kwargs):
        captured_messages[:] = messages
        return LLMResponse(content="done", tool_calls=[], usage={})

    provider.chat_with_retry = chat_with_retry
    tools = MagicMock()
    tools.get_definitions.return_value = []
    initial_messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "hello"},
    ]

    runner = AgentRunner(provider)
    runner._snip_history = MagicMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]
    result = await runner.run(AgentRunSpec(
        initial_messages=initial_messages,
        tools=tools,
        model="test-model",
        max_iterations=1,
        max_tool_result_chars=_MAX_TOOL_RESULT_CHARS,
    ))

    assert result.final_content == "done"
    assert captured_messages == initial_messages








@pytest.mark.asyncio
async def test_runner_keeps_going_when_tool_result_persistence_fails():
    from cloakbot.agent.runner import AgentRunner, AgentRunSpec

    provider = MagicMock()
    captured_second_call: list[dict] = []
    call_count = {"n": 0}

    async def chat_with_retry(*, messages, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return LLMResponse(
                content="working",
                tool_calls=[ToolCallRequest(id="call_1", name="list_dir", arguments={"path": "."})],
                usage={"prompt_tokens": 5, "completion_tokens": 3},
            )
        captured_second_call[:] = messages
        return LLMResponse(content="done", tool_calls=[], usage={})

    provider.chat_with_retry = chat_with_retry
    tools = MagicMock()
    tools.get_definitions.return_value = []
    tools.execute = AsyncMock(return_value="tool result")

    runner = AgentRunner(provider)
    with patch("cloakbot.agent.runner.maybe_persist_tool_result", side_effect=RuntimeError("disk full")):
        result = await runner.run(AgentRunSpec(
            initial_messages=[{"role": "user", "content": "do task"}],
            tools=tools,
            model="test-model",
            max_iterations=2,
            max_tool_result_chars=_MAX_TOOL_RESULT_CHARS,
        ))

    assert result.final_content == "done"
    tool_message = next(msg for msg in captured_second_call if msg.get("role") == "tool")
    assert tool_message["content"] == "tool result"


class _DelayTool(Tool):
    def __init__(self, name: str, *, delay: float, read_only: bool, shared_events: list[str]):
        self._name = name
        self._delay = delay
        self._read_only = read_only
        self._shared_events = shared_events

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._name

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}, "required": []}

    @property
    def read_only(self) -> bool:
        return self._read_only

    async def execute(self, **kwargs):
        self._shared_events.append(f"start:{self._name}")
        await asyncio.sleep(self._delay)
        self._shared_events.append(f"end:{self._name}")
        return self._name




@pytest.mark.asyncio
async def test_runner_blocks_repeated_external_fetches():
    from cloakbot.agent.runner import AgentRunner, AgentRunSpec

    provider = MagicMock()
    captured_final_call: list[dict] = []
    call_count = {"n": 0}

    async def chat_with_retry(*, messages, **kwargs):
        call_count["n"] += 1
        if call_count["n"] <= 3:
            return LLMResponse(
                content="working",
                tool_calls=[ToolCallRequest(id=f"call_{call_count['n']}", name="web_fetch", arguments={"url": "https://example.com"})],
                usage={},
            )
        captured_final_call[:] = messages
        return LLMResponse(content="done", tool_calls=[], usage={})

    provider.chat_with_retry = chat_with_retry
    tools = MagicMock()
    tools.get_definitions.return_value = []
    tools.execute = AsyncMock(return_value="page content")

    runner = AgentRunner(provider)
    result = await runner.run(AgentRunSpec(
        initial_messages=[{"role": "user", "content": "research task"}],
        tools=tools,
        model="test-model",
        max_iterations=4,
        max_tool_result_chars=_MAX_TOOL_RESULT_CHARS,
    ))

    assert result.final_content == "done"
    assert tools.execute.await_count == 2
    blocked_tool_message = [
        msg for msg in captured_final_call
        if msg.get("role") == "tool" and msg.get("tool_call_id") == "call_3"
    ][0]
    assert "repeated external lookup blocked" in blocked_tool_message["content"]










@pytest.mark.asyncio
async def test_runner_tool_error_sets_final_content():
    from cloakbot.agent.runner import AgentRunner, AgentRunSpec

    provider = MagicMock()

    async def chat_with_retry(*, messages, **kwargs):
        return LLMResponse(
            content="working",
            tool_calls=[ToolCallRequest(id="call_1", name="read_file", arguments={"path": "x"})],
            usage={},
        )

    provider.chat_with_retry = chat_with_retry
    tools = MagicMock()
    tools.get_definitions.return_value = []
    tools.execute = AsyncMock(side_effect=RuntimeError("boom"))

    runner = AgentRunner(provider)
    result = await runner.run(AgentRunSpec(
        initial_messages=[{"role": "user", "content": "do task"}],
        tools=tools,
        model="test-model",
        max_iterations=1,
        max_tool_result_chars=_MAX_TOOL_RESULT_CHARS,
        fail_on_tool_error=True,
    ))

    assert result.final_content == "Error: RuntimeError: boom"
    assert result.stop_reason == "tool_error"




@pytest.mark.asyncio
async def test_runner_accumulates_usage_and_preserves_cached_tokens():
    """Runner should accumulate prompt/completion tokens across iterations
    and preserve cached_tokens from provider responses."""
    from cloakbot.agent.runner import AgentRunner, AgentRunSpec

    provider = MagicMock()
    call_count = {"n": 0}

    async def chat_with_retry(*, messages, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return LLMResponse(
                content="thinking",
                tool_calls=[ToolCallRequest(id="call_1", name="read_file", arguments={"path": "x"})],
                usage={"prompt_tokens": 100, "completion_tokens": 10, "cached_tokens": 80},
            )
        return LLMResponse(
            content="done",
            tool_calls=[],
            usage={"prompt_tokens": 200, "completion_tokens": 20, "cached_tokens": 150},
        )

    provider.chat_with_retry = chat_with_retry
    tools = MagicMock()
    tools.get_definitions.return_value = []
    tools.execute = AsyncMock(return_value="file content")

    runner = AgentRunner(provider)
    result = await runner.run(AgentRunSpec(
        initial_messages=[{"role": "user", "content": "do task"}],
        tools=tools,
        model="test-model",
        max_iterations=3,
        max_tool_result_chars=_MAX_TOOL_RESULT_CHARS,
    ))

    # Usage should be accumulated across iterations
    assert result.usage["prompt_tokens"] == 300  # 100 + 200
    assert result.usage["completion_tokens"] == 30  # 10 + 20
    assert result.usage["cached_tokens"] == 230  # 80 + 150


@pytest.mark.asyncio
async def test_runner_passes_cached_tokens_to_hook_context():
    """Hook context.usage should contain cached_tokens."""
    from cloakbot.agent.hook import AgentHook, AgentHookContext
    from cloakbot.agent.runner import AgentRunner, AgentRunSpec

    provider = MagicMock()
    captured_usage: list[dict] = []

    class UsageHook(AgentHook):
        async def after_iteration(self, context: AgentHookContext) -> None:
            captured_usage.append(dict(context.usage))

    async def chat_with_retry(**kwargs):
        return LLMResponse(
            content="done",
            tool_calls=[],
            usage={"prompt_tokens": 200, "completion_tokens": 20, "cached_tokens": 150},
        )

    provider.chat_with_retry = chat_with_retry
    tools = MagicMock()
    tools.get_definitions.return_value = []

    runner = AgentRunner(provider)
    await runner.run(AgentRunSpec(
        initial_messages=[],
        tools=tools,
        model="test-model",
        max_iterations=1,
        max_tool_result_chars=_MAX_TOOL_RESULT_CHARS,
        hook=UsageHook(),
    ))

    assert len(captured_usage) == 1
    assert captured_usage[0]["cached_tokens"] == 150

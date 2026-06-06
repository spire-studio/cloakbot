"""End-to-end: the loop's streaming closure restores <<TAG_N>> deltas (Bug 1).

Proves the exact reported failure is fixed — a placeholder split across stream
chunks (``<<PER`` | ``SON_1>>``) reaches the webui as the restored real value, not
the raw token — by driving the real ``_dispatch`` streaming wiring.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cloakbot.agent.loop import AgentLoop
from cloakbot.bus.events import InboundMessage
from cloakbot.bus.queue import MessageBus
from cloakbot.privacy.core.state import vault


def _make_loop(tmp_path: Path) -> AgentLoop:
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    return AgentLoop(bus=MessageBus(), provider=provider, workspace=tmp_path, model="test-model")


@pytest.mark.asyncio
async def test_streaming_deltas_are_restored_end_to_end(tmp_path, monkeypatch):
    loop = _make_loop(tmp_path)  # AgentLoop.__init__ points the vault at tmp_path
    key = "websocket:abc"

    smap = vault.get_map(key)
    smap.get_or_create_placeholder("Alice Chen", "PERSON", turn_id="t1")
    vault.save_map(key, smap)

    captured: list[str] = []

    async def _capture(msg):
        if msg.metadata.get("_stream_delta"):
            captured.append(msg.content)

    monkeypatch.setattr(loop.bus, "publish_outbound", _capture)

    async def _fake_process(msg, *, on_stream=None, on_stream_end=None, pending_queue=None, **kw):
        # Simulate the runner streaming a placeholder split across two chunks.
        await on_stream("Your name is <<PER")
        await on_stream("SON_1>>.")
        await on_stream_end(resuming=False)
        return None

    monkeypatch.setattr(loop, "_process_message", _fake_process)

    msg = InboundMessage(
        channel="websocket", sender_id="u1", chat_id="abc", content="hi",
        metadata={"_wants_stream": True},
    )
    await loop._dispatch(msg)

    joined = "".join(captured)
    assert joined == "Your name is Alice Chen."
    assert "<<" not in joined and "PERSON_1" not in joined

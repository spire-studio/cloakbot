from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Neutralize the developer's global git config (e.g. commit.gpgsign + an SSH
# signing key driven by 1Password) so dulwich-backed GitStore tests don't try to
# sign commits in the sandbox. Harmless in CI (no global config there).
os.environ.setdefault("GIT_CONFIG_GLOBAL", os.devnull)
os.environ.setdefault("GIT_CONFIG_SYSTEM", os.devnull)
os.environ["GIT_CONFIG_NOSYSTEM"] = "1"

# Fork tests whose target module the rebase removed/deferred (see
# docs/exec-plans/active/nanobot-rebase.md, W0-tail). They fail at import time, so
# they must be ignored at collection rather than xfailed.
collect_ignore = [
    # cloakbot.heartbeat was a fork-only feature dropped in the upstream lay-down;
    # restore it (and this test) if the heartbeat feature is still wanted.
    "tests/agent/test_heartbeat_service.py",
    # cloakbot.channels.webui (bespoke FastAPI webui channel) is discarded for the
    # rebase; re-homing onto the upstream gateway is W2.
    "tests/channels/test_webui_history.py",
]


@pytest.fixture(autouse=True)
def _transparent_local_detector():
    """Make the local privacy detector *available-but-empty* in tests.

    Privacy detection calls a local LLM (Gemma/vLLM) that is absent in unit
    tests. Input sanitization fail-opens on an unavailable detector, but
    tool-output sanitization fail-*closes* (correct in production) — which would
    turn every tool call in the upstream loop tests into an error now that the
    privacy seam is wired in. Patch the four detection entry points to a
    transparent no-op so privacy is ON but inert by default; tests that exercise
    redaction patch these themselves inside the test body, overriding this.
    """
    from cloakbot.privacy.hooks.context import Intent

    async def _noop_input(prompt, *args, **kwargs):
        return prompt, False, [], None

    async def _available_empty_detection(text, session_key, *args, **kwargs):
        """Available-but-empty detector that still applies KNOWN vault mappings.

        Mirrors the real detector's available-but-no-new-entities behavior: the
        per-turn pipeline always runs ``replace_known_originals`` before calling
        the model, so already-minted placeholders are reused even when the model
        finds nothing new. The plain ``_noop_input`` skips this; the goal-at-rest
        seam needs it so a session's known surface forms still tokenize.
        """
        from cloakbot.privacy.core.state.vault import get_map

        smap = get_map(session_key)
        swapped, modified = smap.replace_known_originals(text)
        return swapped, modified, [], None

    async def _noop_tool(text, *args, **kwargs):
        return text, False, []

    async def _noop_tool_chunked(text, *args, **kwargs):
        return text, False, [], False

    async def _chat_intent(*args, **kwargs):
        return Intent.CHAT

    async def _noop_visual_blocks(blocks, *args, **kwargs):
        # Cap E: transparent pass-through of the visual egress pipeline so the
        # image-gen gate is on-but-inert by default (no vLLM/OCR in unit tests).
        # Redaction tests patch this namespace themselves.
        from cloakbot.privacy.visual_redaction import VisualBlocksResult

        return VisualBlocksResult(
            redacted_blocks=list(blocks),
            sanitized_text="",
            modified=False,
        )

    with (
        patch("cloakbot.privacy.runtime.pipeline.sanitize_input_with_detection", new=_noop_input),
        patch("cloakbot.privacy.runtime.pipeline.analyze_user_intent", new=_chat_intent),
        patch("cloakbot.privacy.runtime.tool_interceptor.sanitize_tool_output", new=_noop_tool),
        patch(
            "cloakbot.privacy.runtime.tool_interceptor.sanitize_tool_output_chunked",
            new=_noop_tool_chunked,
        ),
        # Cap A: the StreamingSanitizer (exec_session / shell / long_task carry-over
        # window) calls sanitize_tool_output through its own module namespace, so it
        # needs the same transparent-but-available no-op or every streamed exec poll
        # would fail-closed on the absent local detector.
        patch("cloakbot.privacy.runtime.streaming_sanitizer.sanitize_tool_output", new=_noop_tool),
        # Cap D: the compaction guard (consolidation / autocompact boundary) calls
        # sanitize_tool_output through its own module namespace for the
        # pre-summarize tokenize backstop and the post-summarize raw-value
        # re-tokenize; same transparent-but-available no-op so compaction is
        # on-but-inert by default (redaction tests patch it themselves).
        patch("cloakbot.privacy.compaction.sanitize_tool_output", new=_noop_tool),
        # Cap E: the image-gen visual egress gate placeholders the prompt and
        # routes reference images through process_visual_blocks (vLLM + OCR).
        # Patch both namespaces it uses so the gate is on-but-inert by default;
        # redaction/fail-closed tests patch these in the test body.
        patch(
            "cloakbot.privacy.visual_egress_gate.sanitize_input_with_detection",
            new=_noop_input,
        ),
        patch(
            "cloakbot.privacy.visual_egress_gate.process_visual_blocks",
            new=_noop_visual_blocks,
        ),
        # Cap C / H2: the at-rest /goal objective sanitizer routes the objective
        # through the per-turn detector (fail-closed). Patch its namespace with an
        # available-but-empty detector that still applies known vault mappings so
        # the seam is on-but-inert by default; fail-closed tests patch it to raise.
        patch(
            "cloakbot.privacy.goal_at_rest.sanitize_input_with_detection",
            new=_available_empty_detection,
        ),
    ):
        yield


# Known-failing fork tests after the upstream rebase, xfailed (strict=False) with a
# specific reason each. Add entries here as {path: (reason, {test names})} when a
# rebase leaves a test pending. Currently empty: the stale pre-rebase duplicates
# were deleted (their behavior is covered by the post-rebase split test files) and
# the sandbox-network probe tests were made hermetic.
_REBASE_XFAIL: dict[str, tuple[str, set[str]]] = {}


def pytest_collection_modifyitems(config, items):
    import pytest

    for item in items:
        fspath = str(getattr(item, "fspath", ""))
        name = getattr(item, "originalname", None) or item.name
        for path, (reason, names) in _REBASE_XFAIL.items():
            if path in fspath and name in names:
                item.add_marker(pytest.mark.xfail(reason=reason, strict=False))
                break

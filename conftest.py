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

    async def _noop_tool(text, *args, **kwargs):
        return text, False, []

    async def _noop_tool_chunked(text, *args, **kwargs):
        return text, False, [], False

    async def _chat_intent(*args, **kwargs):
        return Intent.CHAT

    with (
        patch("cloakbot.privacy.runtime.pipeline.sanitize_input_with_detection", new=_noop_input),
        patch("cloakbot.privacy.runtime.pipeline.analyze_user_intent", new=_chat_intent),
        patch("cloakbot.privacy.runtime.tool_interceptor.sanitize_tool_output", new=_noop_tool),
        patch(
            "cloakbot.privacy.runtime.tool_interceptor.sanitize_tool_output_chunked",
            new=_noop_tool_chunked,
        ),
    ):
        yield

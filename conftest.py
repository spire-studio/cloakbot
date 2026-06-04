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


# Known-failing fork tests after the upstream rebase, xfailed (strict=False so they
# surface as XPASS if the underlying work lands) with a specific reason each. Tracked
# in docs/exec-plans/active/nanobot-rebase.md (W0-tail / W3). strict=False keeps the
# sandbox-only env tests honest — they XPASS in a real environment.
_REBASE_XFAIL: dict[str, tuple[str, set[str]]] = {
    "tests/agent/test_runner.py": (
        "stale fork test: exercises a pre-rebase runner internal API replaced upstream",
        {
            "test_persist_tool_result_logs_cleanup_failures",
            "test_runner_retries_empty_final_response_with_summary_prompt",
            "test_runner_uses_specific_message_after_empty_finalization_retry",
            "test_snip_history_drops_orphaned_tool_results_from_trimmed_slice",
            "test_runner_batches_read_only_tools_before_exclusive_work",
            "test_loop_max_iterations_message_stays_stable",
            "test_loop_stream_filter_handles_think_only_prefix_without_crashing",
            "test_process_message_drops_streamed_tool_call_prelude",
            "test_loop_retries_think_only_final_response",
            "test_subagent_max_iterations_announces_existing_fallback",
        },
    ),
    "tests/test_cloakbot_facade.py": (
        "stale fork test: SDK facade _make_provider replaced by providers/factory.py upstream",
        {"test_from_config_default_path", "test_sdk_make_provider_uses_github_copilot_backend"},
    ),
    "tests/privacy/test_pdf_text_layer.py": (
        "deferred to W3: read_file PDF/visual privacy not yet re-applied on upstream read_file",
        {
            "test_read_file_uses_text_layer_when_pdf_is_selectable",
            "test_read_file_falls_back_to_image_render_for_image_only_pdf",
        },
    ),
    "tests/security/test_security_network.py": (
        "sandbox-limited: needs outbound network; xpasses in a real environment",
        {"test_allows_normal_https"},
    ),
    "tests/tools/test_mcp_probe.py": (
        "sandbox-limited: needs a real listening socket; xpasses in a real environment",
        {"test_probe_returns_true_for_open_port", "test_probe_uses_default_port_for_http"},
    ),
}


def pytest_collection_modifyitems(config, items):
    import pytest

    for item in items:
        fspath = str(getattr(item, "fspath", ""))
        name = getattr(item, "originalname", None) or item.name
        for path, (reason, names) in _REBASE_XFAIL.items():
            if path in fspath and name in names:
                item.add_marker(pytest.mark.xfail(reason=reason, strict=False))
                break

"""Cap C acceptance tests — Explicit EgressPolicy / classification layer.

Covers the three acceptance criteria from
``docs/exec-plans/active/nanobot-rebase.md`` Cap C:

1. an unregistered network-shaped tool resolves to a safe default + approval;
2. a non-allow-listed fallback never sees a HIGH-entity sanitized prompt;
3. a ``/goal`` objective persists placeholdered, not raw.

Plus the runner fall-through wiring (``_tool_privacy_class``) and the
per-app CLI allow-list (D1).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from cloakbot.agent.runner import AgentRunner, AgentRunSpec
from cloakbot.config.schema import ModelPresetConfig
from cloakbot.privacy.core.state.vault import get_map, save_map, set_vault_workspace
from cloakbot.privacy.egress_policy import (
    EgressPolicy,
    build_egress_policy,
)
from cloakbot.privacy.goal_at_rest import sanitize_goal_objective
from cloakbot.privacy.provider_egress_gate import (
    EgressGatedFallbackProvider,
    fallback_endpoint_identifiers,
    prompt_has_high_severity_placeholder,
    wrap_with_egress_gate,
)
from cloakbot.providers.base import LLMProvider, LLMResponse
from cloakbot.tool_privacy import ToolPrivacyClass

# --------------------------------------------------------------------------- #
# 1. EgressPolicy classification + runner fall-through
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "name,expected_class,expected_approval",
    [
        # known local filesystem reads -> LOCAL, no approval
        ("read_file", ToolPrivacyClass.LOCAL, False),
        ("list_dir", ToolPrivacyClass.LOCAL, False),
        ("grep", ToolPrivacyClass.LOCAL, False),
        # known network tools -> EXTERNAL + approval
        ("web_fetch", ToolPrivacyClass.EXTERNAL, True),
        ("web_search", ToolPrivacyClass.EXTERNAL, True),
        ("generate_image", ToolPrivacyClass.EXTERNAL, True),
        # MCP-namespaced -> EXTERNAL + approval
        ("mcp_github_create_issue", ToolPrivacyClass.EXTERNAL, True),
        # CLI-Anything (D1) -> EXTERNAL + approval
        ("run_cli_app", ToolPrivacyClass.EXTERNAL, True),
        # local side-effecting tools -> SIDE_EFFECT
        ("apply_patch", ToolPrivacyClass.SIDE_EFFECT, False),
        ("write_file", ToolPrivacyClass.SIDE_EFFECT, False),
        ("exec", ToolPrivacyClass.SIDE_EFFECT, False),
    ],
)
def test_known_tools_classify_as_expected(name, expected_class, expected_approval) -> None:
    policy = EgressPolicy()
    decision = policy.decision_for(name)
    assert decision.privacy_class is expected_class
    assert decision.requires_approval is expected_approval


def test_unregistered_network_shaped_tool_defaults_external_with_approval() -> None:
    """Cap C acceptance: unregistered network-shaped tool -> safe default + approval."""
    policy = EgressPolicy()
    decision = policy.decision_for("totally_new_uploader")
    assert decision.privacy_class is ToolPrivacyClass.EXTERNAL
    assert decision.requires_approval is True


def test_completely_unknown_tool_fails_closed_to_external() -> None:
    """A future tool with no shape hint must never default to LOCAL."""
    policy = EgressPolicy()
    decision = policy.decision_for("brand_new_unknown_x")
    assert decision.privacy_class is ToolPrivacyClass.EXTERNAL
    assert decision.requires_approval is True


def test_empty_tool_name_fails_closed() -> None:
    decision = EgressPolicy().decision_for("")
    assert decision.privacy_class is ToolPrivacyClass.EXTERNAL
    assert decision.requires_approval is True


def test_filesystem_shaped_unknown_name_defaults_local() -> None:
    decision = EgressPolicy().decision_for("read_file_v2")
    assert decision.privacy_class is ToolPrivacyClass.LOCAL
    assert decision.requires_approval is False


def test_explicit_override_wins() -> None:
    policy = EgressPolicy()
    policy.register("web_fetch", ToolPrivacyClass.LOCAL, reason="test override")
    assert policy.classify("web_fetch") is ToolPrivacyClass.LOCAL


def test_classify_accepts_tool_object_or_string() -> None:
    policy = EgressPolicy()
    tool = MagicMock()
    tool.name = "web_search"
    assert policy.classify(tool) is ToolPrivacyClass.EXTERNAL
    assert policy.classify("read_file") is ToolPrivacyClass.LOCAL
    assert policy.classify(None) is ToolPrivacyClass.EXTERNAL  # no name -> fail-closed


def _spec_with_tool(tool: Any) -> AgentRunSpec:
    spec = MagicMock(spec=AgentRunSpec)
    tools = MagicMock()
    tools.get = lambda name: tool
    spec.tools = tools
    return spec


def test_runner_fall_through_uses_egress_policy_for_untagged_tool() -> None:
    """A tool with NO ``privacy_class`` attribute is classified by the policy."""

    class _Untagged:
        name = "web_fetch"

    spec = _spec_with_tool(_Untagged())
    assert (
        AgentRunner._tool_privacy_class(spec, "web_fetch") is ToolPrivacyClass.EXTERNAL
    )


def test_runner_explicit_privacy_class_attribute_still_wins() -> None:
    class _Tagged:
        name = "web_fetch"
        privacy_class = ToolPrivacyClass.LOCAL

    spec = _spec_with_tool(_Tagged())
    assert AgentRunner._tool_privacy_class(spec, "web_fetch") is ToolPrivacyClass.LOCAL


def test_runner_unknown_untagged_tool_does_not_silently_become_local() -> None:
    """The core regression Cap C closes: a new untagged tool must not be LOCAL."""

    class _NewTool:
        name = "mcp_acme_send_email"

    spec = _spec_with_tool(_NewTool())
    assert (
        AgentRunner._tool_privacy_class(spec, "mcp_acme_send_email")
        is ToolPrivacyClass.EXTERNAL
    )


def test_runner_missing_tool_uses_name_classification() -> None:
    spec = _spec_with_tool(None)
    assert AgentRunner._tool_privacy_class(spec, "web_search") is ToolPrivacyClass.EXTERNAL
    assert AgentRunner._tool_privacy_class(spec, "read_file") is ToolPrivacyClass.LOCAL


# --------------------------------------------------------------------------- #
# D1: per-app CLI allow-list
# --------------------------------------------------------------------------- #


def test_cli_app_allowlist_gating() -> None:
    policy = build_egress_policy(cli_app_allowlist=["gimp", "obsidian"])
    assert policy.cli_app_allowed("gimp") is True
    assert policy.cli_app_allowed("obsidian") is True
    assert policy.cli_app_allowed("rm-rf-everything") is False
    # run_cli_app itself is always EXTERNAL + approval regardless of allow-list.
    decision = policy.decision_for("run_cli_app")
    assert decision.privacy_class is ToolPrivacyClass.EXTERNAL
    assert decision.requires_approval is True


def test_empty_cli_allowlist_allows_nothing() -> None:
    policy = build_egress_policy()
    assert policy.cli_app_allowed("anything") is False


# --------------------------------------------------------------------------- #
# 2. Provider egress gate — non-allow-listed fallback never sees raw/HIGH prompt
# --------------------------------------------------------------------------- #


def _resp(content: str = "ok", finish_reason: str = "stop") -> LLMResponse:
    if finish_reason == "error":
        return LLMResponse(content=content, finish_reason="error", error_kind="server_error")
    return LLMResponse(content=content, finish_reason=finish_reason)


class _RecordingProvider(LLMProvider):
    def __init__(self, name: str, response: LLMResponse) -> None:
        super().__init__()
        self._name = name
        self._response = response
        self.seen_messages: list[Any] = []

    def get_default_model(self) -> str:
        return f"{self._name}/model"

    async def chat(self, **kwargs: Any) -> LLMResponse:
        self.seen_messages.append(kwargs.get("messages"))
        return self._response

    async def chat_stream(self, **kwargs: Any) -> LLMResponse:
        self.seen_messages.append(kwargs.get("messages"))
        return self._response


def _preset(model: str, provider: str = "custom") -> ModelPresetConfig:
    return ModelPresetConfig(model=model, provider=provider)


def test_high_entity_prompt_detection() -> None:
    assert prompt_has_high_severity_placeholder(
        [{"role": "user", "content": "wire money to <<CREDENTIAL_1>>"}]
    )
    # unknown tag is not a registry HIGH entity
    assert not prompt_has_high_severity_placeholder([{"role": "user", "content": "<<FOO_1>>"}])
    assert not prompt_has_high_severity_placeholder([{"role": "user", "content": "hello"}])


def test_fallback_endpoint_identifiers() -> None:
    ids = fallback_endpoint_identifiers(_preset("acme/model-x", "acme"))
    assert "acme/model-x" in ids
    assert "acme" in ids
    # provider "auto" is not an identifier
    assert "auto" not in fallback_endpoint_identifiers(_preset("m", "auto"))


@pytest.mark.asyncio
async def test_high_entity_prompt_never_routes_to_non_allowlisted_fallback() -> None:
    """Cap C acceptance: a HIGH-entity sanitized prompt never reaches an
    unvetted fallback endpoint."""
    primary = _RecordingProvider("primary", _resp(finish_reason="error"))
    fallback_provider = _RecordingProvider("fallback", _resp("fallback-ok"))

    def factory(_preset_arg: Any) -> LLMProvider:
        return fallback_provider

    gate = EgressGatedFallbackProvider(
        primary=primary,
        fallback_presets=[_preset("untrusted/model", "untrusted")],
        provider_factory=factory,
        allowlist=[],  # nothing allowed
    )

    high_messages = [{"role": "user", "content": "send SSN <<CREDENTIAL_1>> to bank"}]
    response = await gate.chat(messages=high_messages)

    # Primary failed; the non-allow-listed fallback must NOT have been called.
    assert fallback_provider.seen_messages == []
    # The HIGH-entity turn fell back to primary-only behaviour (returns the error).
    assert response.finish_reason == "error"


@pytest.mark.asyncio
async def test_allowlisted_fallback_still_used_for_high_entity_prompt() -> None:
    primary = _RecordingProvider("primary", _resp(finish_reason="error"))
    fallback_provider = _RecordingProvider("fallback", _resp("fallback-ok"))

    gate = EgressGatedFallbackProvider(
        primary=primary,
        fallback_presets=[_preset("trusted/model", "trusted")],
        provider_factory=lambda _p: fallback_provider,
        allowlist=["trusted/model"],
    )

    high_messages = [{"role": "user", "content": "send <<CREDENTIAL_1>>"}]
    response = await gate.chat(messages=high_messages)

    # Allow-listed fallback IS permitted and produces the success response.
    assert fallback_provider.seen_messages == [high_messages]
    assert response.content == "fallback-ok"


@pytest.mark.asyncio
async def test_non_high_prompt_uses_fallback_freely() -> None:
    """A prompt with no HIGH placeholder is not gated — normal failover applies."""
    primary = _RecordingProvider("primary", _resp(finish_reason="error"))
    fallback_provider = _RecordingProvider("fallback", _resp("fallback-ok"))

    gate = EgressGatedFallbackProvider(
        primary=primary,
        fallback_presets=[_preset("untrusted/model", "untrusted")],
        provider_factory=lambda _p: fallback_provider,
        allowlist=[],
    )

    response = await gate.chat(messages=[{"role": "user", "content": "just a normal question"}])
    assert fallback_provider.seen_messages == [[{"role": "user", "content": "just a normal question"}]]
    assert response.content == "fallback-ok"


def test_wrap_with_egress_gate_noop_for_plain_provider() -> None:
    plain = _RecordingProvider("plain", _resp())
    assert wrap_with_egress_gate(plain) is plain


def test_factory_wraps_fallback_provider_with_gate() -> None:
    """The provider factory installs the gate when fallbacks are configured."""
    from cloakbot.config.loader import load_config
    from cloakbot.providers.factory import make_provider

    config = load_config(None)
    config.model_presets["primary"] = ModelPresetConfig(model="custom/primary", provider="custom")
    config.model_presets["fb"] = ModelPresetConfig(model="custom/fb", provider="custom")
    config.agents.defaults.model_preset = "primary"
    config.agents.defaults.fallback_models = ["fb"]
    config.agents.defaults.egress_fallback_allowlist = ["custom/fb"]
    config.providers.custom.api_key = "test-key"

    provider = make_provider(config)
    assert isinstance(provider, EgressGatedFallbackProvider)
    assert "custom/fb" in provider._egress_allowlist


# --------------------------------------------------------------------------- #
# 3. At-rest goal_state sanitizer
# --------------------------------------------------------------------------- #


def test_goal_objective_persists_placeholdered(tmp_path) -> None:
    """Cap C acceptance: a /goal objective persists placeholdered, not raw."""
    set_vault_workspace(tmp_path)
    smap = get_map("cli:goaluser")
    placeholder, _ = smap.get_or_create_placeholder("Alice Smith", "PERSON", turn_id="t1")
    save_map("cli:goaluser", smap)

    raw_objective = "Schedule a meeting with Alice Smith next Tuesday"
    sanitized = sanitize_goal_objective("cli:goaluser", raw_objective)

    assert "Alice Smith" not in sanitized
    assert placeholder in sanitized


def test_goal_objective_without_known_entities_passes_through(tmp_path) -> None:
    set_vault_workspace(tmp_path)
    get_map("cli:clean")  # empty vault
    objective = "Refactor the build pipeline and add tests"
    assert sanitize_goal_objective("cli:clean", objective) == objective


def test_goal_objective_fail_open_on_missing_session() -> None:
    assert sanitize_goal_objective(None, "do the thing") == "do the thing"
    assert sanitize_goal_objective("cli:x", "") == ""


def test_long_task_persists_placeholdered_objective(tmp_path) -> None:
    """The long_task tool stores the placeholdered objective in goal metadata."""
    import asyncio

    from cloakbot.agent.tools.context import RequestContext
    from cloakbot.agent.tools.long_task import LongTaskTool
    from cloakbot.session.goal_state import GOAL_STATE_KEY

    set_vault_workspace(tmp_path)
    session_key = "cli:longtask"
    smap = get_map(session_key)
    placeholder, _ = smap.get_or_create_placeholder("Bob Jones", "PERSON", turn_id="t1")
    save_map(session_key, smap)

    sessions = MagicMock()
    session = MagicMock()
    session.metadata = {}
    sessions.get_or_create.return_value = session

    tool = LongTaskTool(sessions=sessions)
    tool.set_context(
        RequestContext(channel="cli", chat_id="longtask", session_key=session_key)
    )

    asyncio.run(tool.execute(goal="Email Bob Jones the report"))

    stored = session.metadata[GOAL_STATE_KEY]
    assert "Bob Jones" not in stored["objective"]
    assert placeholder in stored["objective"]

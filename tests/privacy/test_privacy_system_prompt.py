"""Privacy-mode system prompt: deployment-level always-on banner, config
off-switch, and the privacy-agnostic ``extra_sections`` seam in ContextBuilder.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cloakbot.agent.context import ContextBuilder
from cloakbot.config.schema import Config, PrivacyDetectorConfig
from cloakbot.privacy.prompting import build_privacy_system_section, privacy_mode_active
from cloakbot.privacy.prompting import system_prompt as _sp


@pytest.fixture(autouse=True)
def _clear_activation_cache():
    # Activation is process-cached (deployment switch); reset around each test.
    _sp._injection_enabled.cache_clear()
    yield
    _sp._injection_enabled.cache_clear()


def _point_config(monkeypatch, tmp_path, cfg: Config | None) -> None:
    """Route config resolution at a tmp path; ``cfg=None`` means 'no config file'."""
    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr("cloakbot.config.loader.get_config_path", lambda: cfg_path)
    if cfg is not None:
        cfg_path.write_text("{}", encoding="utf-8")  # so .exists() is True
        monkeypatch.setattr("cloakbot.config.loader.load_config", lambda *a, **k: cfg)


def _workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True)
    return ws


# --- activation -------------------------------------------------------------


def test_active_by_default_when_no_config(monkeypatch, tmp_path):
    _point_config(monkeypatch, tmp_path, None)
    assert privacy_mode_active() is True
    section = build_privacy_system_section()
    assert section is not None
    assert "<<PERSON_1>>" in section
    assert "privacy mode" in section.lower()


def test_active_when_toggle_true(monkeypatch, tmp_path):
    cfg = Config()
    cfg.privacy = PrivacyDetectorConfig(inject_system_prompt=True)
    _point_config(monkeypatch, tmp_path, cfg)
    assert privacy_mode_active() is True
    assert build_privacy_system_section() is not None


def test_disabled_when_toggle_false(monkeypatch, tmp_path):
    cfg = Config()
    cfg.privacy = PrivacyDetectorConfig(inject_system_prompt=False)
    _point_config(monkeypatch, tmp_path, cfg)
    assert privacy_mode_active() is False
    assert build_privacy_system_section() is None


def test_banner_contains_no_raw_example_values(monkeypatch, tmp_path):
    _point_config(monkeypatch, tmp_path, None)
    section = build_privacy_system_section()
    # The banner must reference only token *names*, never example cleartext.
    for leak in ("Alice", "acme.com", "TargetCorp", "205 million"):
        assert leak not in section


# --- core seam (ContextBuilder is privacy-agnostic) -------------------------


def test_seam_injects_section_after_identity(tmp_path):
    builder = ContextBuilder(_workspace(tmp_path))
    marker = "# Privacy Mode (CloakBot)"
    prompt = builder.build_system_prompt(extra_sections=[marker + "\n\nbody"])
    # Parts are joined by the section separator. identity.md has no separator of
    # its own, so part[0] is identity and the injected section is the next part.
    sections = prompt.split("\n\n---\n\n")
    assert "memory/history.jsonl" in sections[0]  # identity block first
    assert sections[1].startswith(marker)  # privacy section immediately after


def test_seam_none_is_noop(tmp_path):
    builder = ContextBuilder(_workspace(tmp_path))
    assert builder.build_system_prompt(extra_sections=None) == builder.build_system_prompt()


def test_seam_skips_empty_sections(tmp_path):
    builder = ContextBuilder(_workspace(tmp_path))
    base = builder.build_system_prompt()
    # Empty/None entries are filtered, so the result equals the no-section build.
    assert builder.build_system_prompt(extra_sections=["", None]) == base  # type: ignore[list-item]


def test_build_messages_forwards_section_into_system_message(tmp_path):
    builder = ContextBuilder(_workspace(tmp_path))
    marker = "# Privacy Mode (CloakBot)"
    messages = builder.build_messages(
        history=[],
        current_message="hello",
        extra_system_sections=[marker + "\n\nbody"],
    )
    assert messages[0]["role"] == "system"
    assert marker in messages[0]["content"]

"""Privacy-detector endpoint resolution: env (.env) overrides onboard config.

The local PII detector reads GEMMA_* env vars first (back-compat with .env),
then falls back to the saved config's ``privacy`` section (written by
``cloakbot onboard`` → [D] Privacy Detector), and otherwise errors clearly.
"""

from __future__ import annotations

import pytest

from cloakbot.config.loader import load_config, save_config
from cloakbot.config.schema import Config, PrivacyDetectorConfig
from cloakbot.providers import vllm


@pytest.fixture(autouse=True)
def _clear_detector_cache():
    vllm._settings.cache_clear()
    yield
    vllm._settings.cache_clear()


def _clear_gemma_env(monkeypatch):
    for key in ("GEMMA_BASE_URL", "GEMMA_API_KEY", "GEMMA_MODEL"):
        monkeypatch.delenv(key, raising=False)


def test_env_vars_take_precedence(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # no stray .env
    monkeypatch.setenv("GEMMA_BASE_URL", "http://env:8000/v1")
    monkeypatch.setenv("GEMMA_API_KEY", "env-key")
    monkeypatch.setenv("GEMMA_MODEL", "env-model")

    s = vllm._settings()
    assert s.base_url == "http://env:8000/v1"
    assert s.api_key == "env-key"
    assert s.model == "env-model"
    assert vllm.get_vllm_model() == "env-model"


def test_falls_back_to_onboard_config(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _clear_gemma_env(monkeypatch)

    cfg = Config()
    cfg.privacy = PrivacyDetectorConfig(
        base_url="http://127.0.0.1:11434/v1", api_key="ollama", model="gemma4:e2b"
    )
    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr("cloakbot.config.loader.get_config_path", lambda: cfg_path)
    monkeypatch.setattr("cloakbot.config.loader.load_config", lambda *a, **k: cfg)
    cfg_path.write_text("{}", encoding="utf-8")  # so .exists() is True

    s = vllm._settings()
    assert s.base_url == "http://127.0.0.1:11434/v1"
    assert s.api_key == "ollama"
    assert s.model == "gemma4:e2b"


def test_env_base_url_wins_over_config(monkeypatch, tmp_path):
    """A partial env (only base_url) still triggers the config fallback for the
    missing api_key, but the env base_url is kept."""
    monkeypatch.chdir(tmp_path)
    _clear_gemma_env(monkeypatch)
    monkeypatch.setenv("GEMMA_BASE_URL", "http://env-only:8000/v1")

    cfg = Config()
    cfg.privacy = PrivacyDetectorConfig(
        base_url="http://config:11434/v1", api_key="cfg-key", model="cfg-model"
    )
    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr("cloakbot.config.loader.get_config_path", lambda: cfg_path)
    monkeypatch.setattr("cloakbot.config.loader.load_config", lambda *a, **k: cfg)
    cfg_path.write_text("{}", encoding="utf-8")

    s = vllm._settings()
    assert s.base_url == "http://env-only:8000/v1"  # env kept
    assert s.api_key == "cfg-key"  # filled from config
    assert s.model == "cfg-model"


def test_raises_when_unconfigured(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _clear_gemma_env(monkeypatch)
    monkeypatch.setattr(
        "cloakbot.config.loader.get_config_path", lambda: tmp_path / "nope.json"
    )

    with pytest.raises(RuntimeError, match="not configured"):
        vllm._settings()


def test_default_model_when_unset(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _clear_gemma_env(monkeypatch)
    monkeypatch.setenv("GEMMA_BASE_URL", "http://env:8000/v1")
    monkeypatch.setenv("GEMMA_API_KEY", "env-key")
    # no GEMMA_MODEL

    assert vllm.get_vllm_model() == "google/gemma-4-E2B-it"


def test_onboard_config_privacy_section_roundtrips(tmp_path):
    """The new config.privacy section persists through save/load (so onboard's
    Privacy Detector edits survive)."""
    path = tmp_path / "config.json"
    cfg = Config()
    cfg.privacy = PrivacyDetectorConfig(
        base_url="https://openrouter.ai/api/v1",
        api_key="sk-or-test",
        model="google/gemma-3-27b-it",
    )
    save_config(cfg, config_path=path)
    loaded = load_config(config_path=path)
    assert loaded.privacy.base_url == "https://openrouter.ai/api/v1"
    assert loaded.privacy.api_key == "sk-or-test"
    assert loaded.privacy.model == "google/gemma-3-27b-it"

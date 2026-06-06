"""Privacy-detector endpoint resolution from the saved config.

The local PII detector resolves its connection settings solely from the saved
config's ``privacy`` section (written by ``cloakbot onboard`` -> [D] Privacy
Detector, or the WebUI Settings -> Privacy tab). There is no ``.env`` / ``GEMMA_*``
path anymore — ``config.privacy`` is the single source of truth.
"""

from __future__ import annotations

import pytest

from cloakbot.config.loader import load_config, save_config
from cloakbot.config.schema import Config, PrivacyDetectorConfig
from cloakbot.providers import detector


@pytest.fixture(autouse=True)
def _clear_detector_cache():
    detector._settings.cache_clear()
    yield
    detector._settings.cache_clear()


def _patch_config(monkeypatch, cfg: Config) -> None:
    monkeypatch.setattr("cloakbot.config.loader.load_config", lambda *a, **k: cfg)


def test_resolves_from_config(monkeypatch):
    cfg = Config()
    cfg.privacy = PrivacyDetectorConfig(
        base_url="http://127.0.0.1:11434/v1", api_key="ollama", model="gemma4:e2b"
    )
    _patch_config(monkeypatch, cfg)

    s = detector._settings()
    assert s.base_url == "http://127.0.0.1:11434/v1"
    assert s.api_key == "ollama"
    assert s.model == "gemma4:e2b"
    assert detector.get_detector_model() == "gemma4:e2b"


def test_default_model_when_config_model_empty(monkeypatch):
    cfg = Config()
    # base_url + api_key set, but model cleared -> falls back to the default tag.
    cfg.privacy = PrivacyDetectorConfig(
        base_url="http://127.0.0.1:8000/v1", api_key="tok", model=""
    )
    _patch_config(monkeypatch, cfg)

    assert detector.get_detector_model() == "google/gemma-4-E2B-it"


def test_raises_when_unconfigured(monkeypatch):
    # Default config has no detector base_url / api_key.
    _patch_config(monkeypatch, Config())

    with pytest.raises(RuntimeError, match="not configured"):
        detector._settings()


def test_raises_when_api_key_missing(monkeypatch):
    cfg = Config()
    cfg.privacy = PrivacyDetectorConfig(base_url="http://127.0.0.1:11434/v1", api_key=None)
    _patch_config(monkeypatch, cfg)

    with pytest.raises(RuntimeError, match="not configured"):
        detector._settings()


def test_onboard_config_privacy_section_roundtrips(tmp_path):
    """The config.privacy section persists through save/load (so onboard's
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

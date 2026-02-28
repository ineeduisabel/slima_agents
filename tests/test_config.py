"""Tests for Config loading and precedence."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from slima_agents.config import (
    Config,
    ConfigError,
    CREDENTIALS_PATH,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    _load_credentials,
)


# ---------- Config.load() ----------


def test_load_from_env_var(monkeypatch):
    """SLIMA_API_TOKEN env var should be used when set."""
    monkeypatch.setenv("SLIMA_API_TOKEN", "tok_env")
    monkeypatch.delenv("SLIMA_BASE_URL", raising=False)
    monkeypatch.delenv("SLIMA_AGENTS_MODEL", raising=False)
    config = Config.load()
    assert config.slima_api_token == "tok_env"
    assert config.slima_base_url == DEFAULT_BASE_URL
    assert config.model == DEFAULT_MODEL


def test_load_base_url_from_env(monkeypatch):
    """SLIMA_BASE_URL env var should override default."""
    monkeypatch.setenv("SLIMA_API_TOKEN", "tok_env")
    monkeypatch.setenv("SLIMA_BASE_URL", "https://custom.api")
    config = Config.load()
    assert config.slima_base_url == "https://custom.api"


def test_load_model_from_env(monkeypatch):
    """SLIMA_AGENTS_MODEL env var should set model."""
    monkeypatch.setenv("SLIMA_API_TOKEN", "tok_env")
    monkeypatch.delenv("SLIMA_BASE_URL", raising=False)
    monkeypatch.setenv("SLIMA_AGENTS_MODEL", "claude-sonnet-4-6")
    config = Config.load()
    assert config.model == "claude-sonnet-4-6"


def test_model_override_takes_precedence(monkeypatch):
    """model_override parameter should override env var."""
    monkeypatch.setenv("SLIMA_API_TOKEN", "tok_env")
    monkeypatch.setenv("SLIMA_AGENTS_MODEL", "claude-sonnet-4-6")
    config = Config.load(model_override="claude-haiku-4-5-20251001")
    assert config.model == "claude-haiku-4-5-20251001"


def test_load_from_credentials_file(monkeypatch, tmp_path):
    """Falls back to credentials.json when env var not set."""
    monkeypatch.delenv("SLIMA_API_TOKEN", raising=False)
    monkeypatch.delenv("SLIMA_BASE_URL", raising=False)
    monkeypatch.delenv("SLIMA_AGENTS_MODEL", raising=False)

    cred_file = tmp_path / "credentials.json"
    cred_file.write_text(json.dumps({
        "apiToken": "tok_file",
        "baseUrl": "https://file.api",
    }))

    with patch("slima_agents.config.CREDENTIALS_PATH", cred_file):
        config = Config.load()

    assert config.slima_api_token == "tok_file"
    assert config.slima_base_url == "https://file.api"


def test_env_var_overrides_credentials_file(monkeypatch, tmp_path):
    """Env var should take priority over credentials.json."""
    monkeypatch.setenv("SLIMA_API_TOKEN", "tok_env")
    monkeypatch.delenv("SLIMA_BASE_URL", raising=False)

    cred_file = tmp_path / "credentials.json"
    cred_file.write_text(json.dumps({"apiToken": "tok_file"}))

    with patch("slima_agents.config.CREDENTIALS_PATH", cred_file):
        config = Config.load()

    assert config.slima_api_token == "tok_env"


def test_raises_config_error_when_no_token(monkeypatch, tmp_path):
    """Should raise ConfigError when no token is found anywhere."""
    monkeypatch.delenv("SLIMA_API_TOKEN", raising=False)
    monkeypatch.delenv("SLIMA_BASE_URL", raising=False)

    # Point to non-existent credentials file
    with patch("slima_agents.config.CREDENTIALS_PATH", tmp_path / "nope.json"):
        with pytest.raises(ConfigError):
            Config.load()


# ---------- _load_credentials() ----------


def test_load_credentials_missing_file(tmp_path):
    """Should return empty strings if file doesn't exist."""
    with patch("slima_agents.config.CREDENTIALS_PATH", tmp_path / "nope.json"):
        token, base_url = _load_credentials()
    assert token == ""
    assert base_url == ""


def test_load_credentials_invalid_json(tmp_path):
    """Should return empty strings on malformed JSON."""
    cred_file = tmp_path / "credentials.json"
    cred_file.write_text("not json {{{")

    with patch("slima_agents.config.CREDENTIALS_PATH", cred_file):
        token, base_url = _load_credentials()
    assert token == ""
    assert base_url == ""


def test_load_credentials_partial_keys(tmp_path):
    """Should return available keys, empty for missing ones."""
    cred_file = tmp_path / "credentials.json"
    cred_file.write_text(json.dumps({"apiToken": "tok_only"}))

    with patch("slima_agents.config.CREDENTIALS_PATH", cred_file):
        token, base_url = _load_credentials()
    assert token == "tok_only"
    assert base_url == ""

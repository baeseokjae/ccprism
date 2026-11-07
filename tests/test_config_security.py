"""Secure defaults and actual YAML/environment/CLI precedence."""

import argparse
import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from src.cli.commands import _cmd_start
from src.config import GatewaySettings, get_settings, load_gateway_config

KEY = "test-master-" + "x" * 32


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    with patch.dict(os.environ, os.environ.copy(), clear=True):
        yield
    get_settings.cache_clear()


def test_default_and_shipped_settings_are_secure():
    for settings in (GatewaySettings(), load_gateway_config()):
        assert settings.server.host == "127.0.0.1"
        assert settings.auth.enabled is True
        assert settings.auth.local_mode is False


def test_nested_environment_overrides_yaml(monkeypatch, tmp_path):
    config = tmp_path / "gateway.yaml"
    config.write_text(
        "server:\n  host: 0.0.0.0\n  port: 8080\n"
        "auth:\n  enabled: false\n  local_mode: true\n  gateway_master_key: yaml-key\n"
    )
    monkeypatch.setenv("CCPRISM_SERVER__HOST", "127.0.0.1")
    monkeypatch.setenv("CCPRISM_SERVER__PORT", "9090")
    monkeypatch.setenv("CCPRISM_AUTH__ENABLED", "true")
    monkeypatch.setenv("CCPRISM_AUTH__LOCAL_MODE", "false")
    monkeypatch.setenv("CCPRISM_AUTH__GATEWAY_MASTER_KEY", KEY)
    settings = load_gateway_config(config)
    assert settings.server.host == "127.0.0.1"
    assert settings.server.port == 9090
    assert settings.auth.enabled is True
    assert settings.auth.local_mode is False
    assert settings.gateway_master_key == KEY


def test_partial_environment_override_preserves_yaml_siblings(monkeypatch, tmp_path):
    config = tmp_path / "gateway.yaml"
    config.write_text("server:\n  host: 127.0.0.2\n  port: 9090\n")
    monkeypatch.setenv("CCPRISM_SERVER__PORT", "9091")
    settings = load_gateway_config(config)
    assert settings.server.host == "127.0.0.2"
    assert settings.server.port == 9091


def test_cli_uses_custom_config_and_passes_secure_uvicorn_options(monkeypatch, tmp_path):
    config = tmp_path / "gateway.yaml"
    config.write_text(
        yaml.safe_dump(
            {"server": {"host": "127.0.0.2", "port": 9090}, "auth": {"gateway_master_key": KEY}}
        )
    )
    args = argparse.Namespace(config=str(config), host=None, port=None, reload=True)
    with patch("uvicorn.run") as run:
        _cmd_start(args)
    run.assert_called_once_with(
        "src.main:app", host="127.0.0.2", port=9090, reload=True, proxy_headers=False
    )
    assert get_settings().server.port == 9090


def test_cli_rejects_remote_bind_when_auth_disabled(monkeypatch, tmp_path):
    config = tmp_path / "gateway.yaml"
    config.write_text("auth:\n  enabled: false\n  local_mode: true\n")
    args = argparse.Namespace(config=str(config), host="0.0.0.0", port=8080, reload=False)
    with patch("uvicorn.run") as run, pytest.raises(SystemExit, match="Unsafe gateway"):
        _cmd_start(args)
    run.assert_not_called()


def test_cli_host_override_cannot_be_lost_in_reload(monkeypatch):
    monkeypatch.setenv("CCPRISM_AUTH__GATEWAY_MASTER_KEY", KEY)
    args = argparse.Namespace(config=None, host="127.0.0.2", port=9000, reload=True)
    with patch("uvicorn.run"):
        _cmd_start(args)
    get_settings.cache_clear()
    assert get_settings().server.host == "127.0.0.2"
    assert get_settings().server.port == 9000


def test_compose_exposes_only_loopback_and_requires_authentication():
    root = Path(__file__).resolve().parent.parent
    compose = yaml.safe_load((root / "docker-compose.yaml").read_text())
    service = compose["services"]["ccprism"]
    assert service["ports"] == ["127.0.0.1:8080:8080"]
    assert "CCPRISM_AUTH__ENABLED=true" in service["environment"]
    assert "CCPRISM_AUTH__LOCAL_MODE=false" in service["environment"]
    assert any(
        value.startswith("CCPRISM_AUTH__GATEWAY_MASTER_KEY=${CCPRISM_AUTH__GATEWAY_MASTER_KEY:?")
        for value in service["environment"]
    )
    assert '"--no-proxy-headers"' in (root / "Dockerfile").read_text()

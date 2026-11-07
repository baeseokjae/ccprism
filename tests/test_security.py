"""Tests for security startup checks."""

import os
from pathlib import Path
from unittest.mock import patch

from src.security.startup_checks import (
    check_environment_secrets,
    check_file_permissions,
    run_startup_security_checks,
)


class TestCheckFilePermissions:
    def test_no_warnings_when_files_missing(self) -> None:
        with patch(
            "src.security.startup_checks.SENSITIVE_FILES",
            [("/nonexistent/path/to/file", "test file")],
        ):
            warnings = check_file_permissions()
            assert warnings == []

    def test_warning_on_wrong_permissions(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test_creds"
        test_file.write_text("secret")
        test_file.chmod(0o644)

        with patch(
            "src.security.startup_checks.SENSITIVE_FILES",
            [(str(test_file), "test credentials")],
        ):
            warnings = check_file_permissions()
            assert len(warnings) == 1
            assert "0o644" in warnings[0]

    def test_no_warning_on_correct_permissions(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test_creds"
        test_file.write_text("secret")
        test_file.chmod(0o600)

        with patch(
            "src.security.startup_checks.SENSITIVE_FILES",
            [(str(test_file), "test credentials")],
        ):
            warnings = check_file_permissions()
            assert warnings == []


class TestCheckEnvironmentSecrets:
    def test_detects_set_api_keys(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test12345678"}):
            exposed = check_environment_secrets()
            assert "OPENAI_API_KEY" in exposed

    def test_ignores_unset_keys(self) -> None:
        env_copy = os.environ.copy()
        for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY"):
            env_copy.pop(k, None)
        with patch.dict(os.environ, env_copy, clear=True):
            exposed = check_environment_secrets()
            for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY"):
                assert k not in exposed

    def test_ignores_dollar_prefixed_values(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": "$VAULT_REF"}):
            exposed = check_environment_secrets()
            assert "OPENAI_API_KEY" not in exposed


class TestRunStartupSecurityChecks:
    def test_returns_permission_warnings(self) -> None:
        with patch(
            "src.security.startup_checks.SENSITIVE_FILES",
            [("/nonexistent/file", "test")],
        ):
            result = run_startup_security_checks()
            assert isinstance(result, list)


def test_environment_secret_values_are_never_logged(caplog):
    import logging

    for secret in ("tiny", "sk-secret-long-value-not-for-logs"):
        caplog.clear()
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": secret}, clear=True),
            caplog.at_level(logging.INFO, logger="ccprism.security"),
        ):
            check_environment_secrets()
        assert "OPENAI_API_KEY" in caplog.text
        assert secret not in caplog.text
        assert secret[:8] not in caplog.text

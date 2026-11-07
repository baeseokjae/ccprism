"""Security startup checks for ccprism gateway."""

import logging
import os
from pathlib import Path

logger = logging.getLogger("ccprism.security")

SENSITIVE_FILES = [
    ("~/.codex/auth.json", "Codex OAuth token"),
    ("~/.ccprism/credentials.enc", "Encrypted API Key store"),
    ("~/.ccprism/gateway.yaml", "Gateway master key (possible)"),
]


def check_file_permissions() -> list[str]:
    """Verify sensitive files have 0600 permissions at runtime."""
    warnings: list[str] = []
    for file_path, description in SENSITIVE_FILES:
        path = Path(file_path).expanduser()
        if not path.exists():
            continue

        perms = path.stat().st_mode & 0o777
        if perms != 0o600:
            msg = (
                f"Security warning: {path} ({description}) has permissions "
                f"{oct(perms)}. Should be 0600. Fix with: chmod 600 {path}"
            )
            logger.warning(msg)
            warnings.append(msg)

    return warnings


def check_environment_secrets() -> list[str]:
    """Check if sensitive API keys are present in environment variables."""
    exposed: list[str] = []
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY"):
        val = os.environ.get(key, "")
        if val and not val.startswith("$"):
            logger.info("Environment variable %s is set (value redacted)", key)
            exposed.append(key)
    return exposed


def run_startup_security_checks() -> list[str]:
    """Run all security checks at gateway startup. Warns but does not block."""
    logger.info("=== ccprism security check started ===")
    perm_warnings = check_file_permissions()
    check_environment_secrets()
    logger.info("=== Security check complete: %d warning(s) ===", len(perm_warnings))
    return perm_warnings

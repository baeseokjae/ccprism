"""Gateway configuration loading with Pydantic BaseSettings."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings

logger = logging.getLogger("ccprism.config")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class ServerSettings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8080


class AuthSettings(BaseSettings):
    enabled: bool = False
    local_mode: bool = True
    jwt_secret_key: str = ""
    gateway_master_key: str = ""


class BudgetSettings(BaseSettings):
    monthly_usd: float = 0.0
    cost_db_path: str = "~/.ccprism/costs.db"
    retention_days: int = 90


class LoggingSettings(BaseSettings):
    level: str = "INFO"
    format: str = "json"
    file: str = ""


class MonitoringSettings(BaseSettings):
    slack_webhook_url: str = ""
    alert_level: str = "CRITICAL"


class GatewaySettings(BaseSettings):
    """Main gateway settings, loaded from gateway.yaml + env overrides."""

    model_config = {"env_prefix": "CCPRISM_"}

    server: ServerSettings = Field(default_factory=ServerSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    budget: BudgetSettings = Field(default_factory=BudgetSettings)
    monitoring: MonitoringSettings = Field(default_factory=MonitoringSettings)

    rules_dir: str = str(_PROJECT_ROOT / "rules")
    providers_dir: str = str(_PROJECT_ROOT / "providers")
    config_dir: str = str(_PROJECT_ROOT / "config")
    litellm_config_path: str = str(_PROJECT_ROOT / "config" / "litellm_config.yaml")

    # Convenience properties derived from auth
    @property
    def auth_enabled(self) -> bool:
        return self.auth.enabled

    @property
    def auth_local_mode(self) -> bool:
        return self.auth.local_mode

    @property
    def jwt_secret_key(self) -> str:
        return self.auth.jwt_secret_key

    @property
    def gateway_master_key(self) -> str:
        return self.auth.gateway_master_key


def load_gateway_config(config_path: str | Path | None = None) -> GatewaySettings:
    """Load gateway settings from YAML file with environment variable overrides."""
    if config_path is None:
        config_path = _PROJECT_ROOT / "config" / "gateway.yaml"
    else:
        config_path = Path(config_path)

    data: dict = {}
    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        logger.info(f"Loaded gateway config from {config_path}")
    else:
        logger.warning(f"Gateway config not found at {config_path}, using defaults")

    return GatewaySettings(**data)


@lru_cache
def get_settings() -> GatewaySettings:
    """Get cached gateway settings singleton."""
    return load_gateway_config()


def load_litellm_config(config_path: str | Path | None = None) -> dict:
    """Load LiteLLM configuration from YAML file."""
    if config_path is None:
        config_path = _PROJECT_ROOT / "config" / "litellm_config.yaml"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        logger.warning(f"LiteLLM config not found at {config_path}")
        return {}

    with open(config_path) as f:
        config = yaml.safe_load(f) or {}

    model_count = len(config.get("model_list", []))
    logger.info(f"Loaded LiteLLM config from {config_path} ({model_count} models)")
    return config

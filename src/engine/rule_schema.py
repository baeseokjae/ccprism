"""Pydantic v2 models for rule configuration."""

from typing import Literal

from pydantic import BaseModel, Field


class MatchConfig(BaseModel):
    """Configuration for request matching."""

    type: Literal[
        "thinking",
        "token_count",
        "tool",
        "model",
        "keyword",
        "always",
        "custom",
        "content_type",
        "time_range",
        "ab_test",
    ]
    keywords: list[str] = Field(default_factory=list)
    threshold: int = Field(default=0, ge=0)
    tool_name: str = ""
    model_pattern: str = ""
    content_types: list[str] = Field(default_factory=list)
    script_path: str = ""
    start_hour: int = 0
    end_hour: int = 0
    timezone: str = "UTC"
    percentage: int = Field(default=0, ge=0, le=100)
    experiment_name: str = ""

    model_config = {"extra": "allow"}


class RouteTarget(BaseModel):
    """A single routing target (provider + model)."""

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    auth: str = Field(default="api_key")


class RouteConfig(BaseModel):
    """Routing configuration with primary and fallback targets."""

    primary: RouteTarget
    fallback: list[RouteTarget] = Field(default_factory=list)


class RuleSchema(BaseModel):
    """Top-level rule schema parsed from YAML frontmatter."""

    name: str = Field(pattern=r"^[a-z0-9_-]+$")
    priority: int = Field(ge=0, le=999)
    enabled: bool = True
    description: str = ""
    match: MatchConfig
    route: RouteConfig
    tags: list[str] = Field(default_factory=list)

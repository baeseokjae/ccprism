"""Tests for rule schema Pydantic models."""

import pytest
from pydantic import ValidationError

from src.engine.rule_schema import MatchConfig, RouteConfig, RouteTarget, RuleSchema


class TestMatchConfig:
    def test_valid_match_config(self) -> None:
        cfg = MatchConfig(type="thinking")
        assert cfg.type == "thinking"
        assert cfg.keywords == []
        assert cfg.threshold == 0

    def test_extra_fields_allowed(self) -> None:
        cfg = MatchConfig(type="custom", custom_field="value")
        assert cfg.custom_field == "value"  # type: ignore[attr-defined]

    def test_negative_threshold_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MatchConfig(type="token_count", threshold=-1)

    def test_invalid_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MatchConfig(type="nonexistent")  # type: ignore[arg-type]


class TestRouteTarget:
    def test_valid_target(self) -> None:
        t = RouteTarget(provider="anthropic", model="claude-sonnet-4-6")
        assert t.auth == "api_key"

    def test_empty_provider_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RouteTarget(provider="", model="gpt-4")

    def test_empty_model_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RouteTarget(provider="openai", model="")


class TestRuleSchema:
    def test_valid_schema(self) -> None:
        schema = RuleSchema(
            name="my-rule",
            priority=10,
            match=MatchConfig(type="always"),
            route=RouteConfig(
                primary=RouteTarget(provider="anthropic", model="claude-sonnet-4-6"),
            ),
        )
        assert schema.name == "my-rule"
        assert schema.enabled is True
        assert schema.tags == []

    def test_invalid_name_pattern(self) -> None:
        with pytest.raises(ValidationError):
            RuleSchema(
                name="Invalid Name!",
                priority=10,
                match=MatchConfig(type="always"),
                route=RouteConfig(
                    primary=RouteTarget(provider="anthropic", model="claude-sonnet-4-6"),
                ),
            )

    def test_priority_too_high(self) -> None:
        with pytest.raises(ValidationError):
            RuleSchema(
                name="test",
                priority=1000,
                match=MatchConfig(type="always"),
                route=RouteConfig(
                    primary=RouteTarget(provider="anthropic", model="claude-sonnet-4-6"),
                ),
            )

    def test_priority_negative(self) -> None:
        with pytest.raises(ValidationError):
            RuleSchema(
                name="test",
                priority=-1,
                match=MatchConfig(type="always"),
                route=RouteConfig(
                    primary=RouteTarget(provider="anthropic", model="claude-sonnet-4-6"),
                ),
            )

    def test_missing_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            RuleSchema(name="test", priority=10)  # type: ignore[call-arg]

    def test_with_fallbacks_and_tags(self) -> None:
        schema = RuleSchema(
            name="full-rule",
            priority=50,
            description="A full rule",
            match=MatchConfig(type="keyword", keywords=["test"]),
            route=RouteConfig(
                primary=RouteTarget(provider="anthropic", model="claude-sonnet-4-6"),
                fallback=[RouteTarget(provider="openai", model="gpt-4.1")],
            ),
            tags=["test", "example"],
        )
        assert len(schema.route.fallback) == 1
        assert schema.tags == ["test", "example"]

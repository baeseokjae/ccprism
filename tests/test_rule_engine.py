"""Tests for the rule engine."""

from pathlib import Path

import pytest

from src.engine.rule_engine import RoutingDecision, RoutingRule, RuleEngine


@pytest.fixture
def rules_dir(tmp_path: Path) -> Path:
    """Create a temporary rules directory with sample rule files."""
    # Rule priority 10 - thinking
    (tmp_path / "10-thinking.md").write_text(
        """---
name: thinking-rule
enabled: true
priority: 10

match:
  type: thinking

route:
  primary:
    provider: anthropic
    model: claude-opus-4-6
  fallback:
    - provider: openai
      model: o3
---

# Thinking Rule
""",
        encoding="utf-8",
    )

    # Rule priority 20 - keyword
    (tmp_path / "20-keyword.md").write_text(
        """---
name: coding-rule
enabled: true
priority: 20

match:
  type: keyword
  keywords:
    - implement
    - refactor

route:
  primary:
    provider: openai
    model: gpt-5.2-codex

tags:
  - coding
---

# Coding Rule
""",
        encoding="utf-8",
    )

    # Rule priority 999 - default
    (tmp_path / "99-default.md").write_text(
        """---
name: default
enabled: true
priority: 999

match:
  type: always

route:
  primary:
    provider: anthropic
    model: claude-sonnet-4-6
  fallback:
    - provider: openai
      model: gpt-4.1

tags:
  - default
---

# Default
""",
        encoding="utf-8",
    )

    # Disabled rule priority 5
    (tmp_path / "05-disabled.md").write_text(
        """---
name: disabled-rule
enabled: false
priority: 5

match:
  type: always

route:
  primary:
    provider: ollama
    model: llama3

---

# Disabled Rule
""",
        encoding="utf-8",
    )

    return tmp_path


class TestRuleEngine:
    def test_rules_load_in_priority_order(self, rules_dir: Path) -> None:
        engine = RuleEngine(rules_dir)
        priorities = [r.priority for r in engine.rules]
        assert priorities == sorted(priorities)

    def test_all_rules_loaded(self, rules_dir: Path) -> None:
        engine = RuleEngine(rules_dir)
        assert len(engine.rules) == 4

    def test_first_match_wins(self, rules_dir: Path) -> None:
        engine = RuleEngine(rules_dir)
        request = {"thinking": {"enabled": True}}
        decision = engine.evaluate(request)

        assert decision.matched_by == "thinking-rule"
        assert decision.primary["provider"] == "anthropic"
        assert decision.primary["model"] == "claude-opus-4-6"

    def test_default_catches_all(self, rules_dir: Path) -> None:
        engine = RuleEngine(rules_dir)
        request = {"messages": [{"role": "user", "content": "hello world"}]}
        decision = engine.evaluate(request)

        assert decision.matched_by == "default"
        assert decision.primary["provider"] == "anthropic"
        assert decision.primary["model"] == "claude-sonnet-4-6"

    def test_disabled_rules_skipped(self, rules_dir: Path) -> None:
        engine = RuleEngine(rules_dir)
        # Even though the disabled rule has priority 5 (lowest/first), it should be skipped
        # and the next matching enabled rule wins
        request = {"messages": [{"role": "user", "content": "something random"}]}
        decision = engine.evaluate(request)

        assert decision.matched_by != "disabled-rule"

    def test_keyword_match(self, rules_dir: Path) -> None:
        engine = RuleEngine(rules_dir)
        request = {"messages": [{"role": "user", "content": "please implement this feature"}]}
        decision = engine.evaluate(request)

        assert decision.matched_by == "coding-rule"
        assert decision.primary["model"] == "gpt-5.2-codex"

    def test_fallbacks_included(self, rules_dir: Path) -> None:
        engine = RuleEngine(rules_dir)
        request = {"thinking": {"enabled": True}}
        decision = engine.evaluate(request)

        assert len(decision.fallbacks) == 1
        assert decision.fallbacks[0]["model"] == "o3"

    def test_empty_rules_dir(self, tmp_path: Path) -> None:
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        engine = RuleEngine(empty_dir)

        assert len(engine.rules) == 0
        decision = engine.evaluate({"messages": []})
        assert decision.matched_by == "default"

    def test_nonexistent_rules_dir(self, tmp_path: Path) -> None:
        engine = RuleEngine(tmp_path / "nonexistent")
        assert len(engine.rules) == 0

    def test_rule_has_source_file(self, rules_dir: Path) -> None:
        engine = RuleEngine(rules_dir)
        for rule in engine.rules:
            assert rule.source_file != ""

    def test_rule_has_documentation(self, rules_dir: Path) -> None:
        engine = RuleEngine(rules_dir)
        thinking_rule = next(r for r in engine.rules if r.name == "thinking-rule")
        assert "Thinking Rule" in thinking_rule.documentation


class TestRoutingDecision:
    def test_default_decision(self) -> None:
        decision = RoutingDecision.default()
        assert decision.rule is None
        assert decision.primary["provider"] == "anthropic"
        assert decision.primary["model"] == "claude-sonnet-4-6"
        assert decision.fallbacks == []
        assert decision.matched_by == "default"


class TestRoutingRule:
    def test_routing_rule_defaults(self) -> None:
        rule = RoutingRule(
            name="test",
            enabled=True,
            priority=10,
            match_type="always",
            match_params={},
            route_primary={"provider": "anthropic", "model": "claude-sonnet-4-6"},
            route_fallbacks=[],
        )
        assert rule.tags == []
        assert rule.documentation == ""
        assert rule.source_file == ""

"""Integration tests for routing scenarios."""

from pathlib import Path

import pytest

from src.engine.rule_engine import RuleEngine


@pytest.fixture
def engine() -> RuleEngine:
    """Create a RuleEngine from the project's rules/ directory."""
    rules_dir = Path(__file__).parent.parent / "rules"
    return RuleEngine(rules_dir)


class TestRoutingScenarios:
    """Test end-to-end routing scenarios with the project's rule files."""

    def test_thinking_routes_to_opus(self, engine: RuleEngine) -> None:
        request = {
            "model": "claude-sonnet-4-6",
            "messages": [{"role": "user", "content": "Explain quantum computing"}],
            "thinking": {"enabled": True},
        }
        decision = engine.evaluate(request)
        assert decision.matched_by == "thinking-requests"
        assert decision.primary["model"] == "claude-opus-4-6"
        assert decision.primary["provider"] == "anthropic"

    def test_web_search_tool_routes_to_gpt(self, engine: RuleEngine) -> None:
        request = {
            "model": "claude-sonnet-4-6",
            "messages": [{"role": "user", "content": "Search for latest news"}],
            "tools": [{"function": {"name": "WebSearch", "description": "Search the web"}}],
            "thinking": {},
        }
        decision = engine.evaluate(request)
        assert decision.matched_by == "web-search"
        assert decision.primary["model"] == "gpt-4.1"
        assert decision.primary["provider"] == "openai"

    def test_haiku_model_routes_to_deepseek(self, engine: RuleEngine) -> None:
        request = {
            "model": "claude-3-5-haiku-latest",
            "messages": [{"role": "user", "content": "Summarize this file"}],
            "thinking": {},
        }
        decision = engine.evaluate(request)
        assert decision.matched_by == "background-tasks"
        assert decision.primary["model"] == "deepseek-chat"
        assert decision.primary["provider"] == "deepseek"

    def test_coding_keyword_routes_to_codex(self, engine: RuleEngine) -> None:
        request = {
            "model": "claude-sonnet-4-6",
            "messages": [{"role": "user", "content": "Please implement a login form"}],
            "thinking": {},
        }
        decision = engine.evaluate(request)
        assert decision.matched_by == "codex-coding"
        assert decision.primary["model"] == "gpt-5.2-codex"

    def test_default_routes_to_sonnet(self, engine: RuleEngine) -> None:
        request = {
            "model": "claude-sonnet-4-6",
            "messages": [{"role": "user", "content": "Hello, how are you?"}],
            "thinking": {},
        }
        decision = engine.evaluate(request)
        assert decision.matched_by == "default"
        assert decision.primary["model"] == "claude-sonnet-4-6"
        assert decision.primary["provider"] == "anthropic"

    def test_default_has_fallbacks(self, engine: RuleEngine) -> None:
        request = {
            "model": "claude-sonnet-4-6",
            "messages": [{"role": "user", "content": "Hi"}],
            "thinking": {},
        }
        decision = engine.evaluate(request)
        assert len(decision.fallbacks) >= 1

    def test_priority_order(self, engine: RuleEngine) -> None:
        """Verify thinking (priority 10) wins over keyword (priority 15)."""
        request = {
            "model": "claude-sonnet-4-6",
            "messages": [{"role": "user", "content": "implement a feature"}],
            "thinking": {"enabled": True},
        }
        decision = engine.evaluate(request)
        assert decision.matched_by == "thinking-requests"

    def test_image_content_routes_to_sonnet(self, engine: RuleEngine) -> None:
        request = {
            "model": "claude-sonnet-4-6",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What is in this image?"},
                        {"type": "image", "source": {"type": "base64", "data": "..."}},
                    ],
                }
            ],
            "thinking": {},
        }
        decision = engine.evaluate(request)
        assert decision.matched_by == "image-routing"
        assert decision.primary["model"] == "claude-sonnet-4-6"
        assert decision.primary["provider"] == "anthropic"

    def test_cost_saving_routes_to_deepseek(self, engine: RuleEngine) -> None:
        request = {
            "model": "claude-sonnet-4-6",
            "messages": [{"role": "user", "content": "summarize this article for me"}],
            "thinking": {},
        }
        decision = engine.evaluate(request)
        assert decision.matched_by == "cost-saving"
        assert decision.primary["model"] == "deepseek-chat"
        assert decision.primary["provider"] == "deepseek"

    def test_all_rules_loaded(self, engine: RuleEngine) -> None:
        """All 9 rule files should be loaded."""
        assert len(engine.rules) == 9
        names = {r.name for r in engine.rules}
        expected = {
            "thinking-requests",
            "long-context",
            "codex-coding",
            "web-search",
            "background-tasks",
            "image-routing",
            "cost-saving",
            "night-saving",
            "default",
        }
        assert names == expected


class TestHotReload:
    def test_rules_reload_on_file_change(self, tmp_path: Path) -> None:
        """Test that _load_all_rules() picks up new files."""
        # Start with one rule
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
---
Default
""",
            encoding="utf-8",
        )

        engine = RuleEngine(tmp_path)
        assert len(engine.rules) == 1

        # Add a new rule
        (tmp_path / "10-new.md").write_text(
            """---
name: new-rule
enabled: true
priority: 10
match:
  type: thinking
route:
  primary:
    provider: anthropic
    model: claude-opus-4-6
---
New
""",
            encoding="utf-8",
        )

        engine._load_all_rules()
        assert len(engine.rules) == 2

    def test_reload_handles_invalid_file(self, tmp_path: Path) -> None:
        """Invalid files should be skipped without affecting other rules."""
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
---
Default
""",
            encoding="utf-8",
        )
        (tmp_path / "10-broken.md").write_text("no frontmatter here", encoding="utf-8")

        engine = RuleEngine(tmp_path)
        assert len(engine.rules) == 1
        assert engine.rules[0].name == "default"

    def test_reload_after_file_deletion(self, tmp_path: Path) -> None:
        """Rules should be removed when their file is deleted."""
        rule_file = tmp_path / "10-temp.md"
        rule_file.write_text(
            """---
name: temp-rule
enabled: true
priority: 10
match:
  type: always
route:
  primary:
    provider: anthropic
    model: claude-opus-4-6
---
Temp
""",
            encoding="utf-8",
        )

        engine = RuleEngine(tmp_path)
        assert len(engine.rules) == 1

        rule_file.unlink()
        engine._load_all_rules()
        assert len(engine.rules) == 0

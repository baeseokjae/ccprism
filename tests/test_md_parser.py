"""Tests for Markdown rule file parser."""

from pathlib import Path

import pytest

from src.engine.md_parser import parse_rule_file


@pytest.fixture
def tmp_rule(tmp_path: Path):
    """Helper to create temporary rule files."""

    def _create(content: str, name: str = "test.md") -> Path:
        p = tmp_path / name
        p.write_text(content, encoding="utf-8")
        return p

    return _create


class TestParseRuleFile:
    def test_valid_md_parses(self, tmp_rule) -> None:
        content = """---
name: test-rule
priority: 10

match:
  type: always

route:
  primary:
    provider: anthropic
    model: claude-sonnet-4-6
---

# Test Rule

Some documentation here.
"""
        path = tmp_rule(content)
        result = parse_rule_file(path)

        assert result.ok
        assert result.schema is not None
        assert result.schema.name == "test-rule"
        assert result.schema.priority == 10
        assert result.body == "# Test Rule\n\nSome documentation here."

    def test_missing_frontmatter(self, tmp_rule) -> None:
        path = tmp_rule("# Just markdown\nNo frontmatter here.")
        result = parse_rule_file(path)

        assert not result.ok
        assert "missing frontmatter" in result.error

    def test_missing_closing_delimiter(self, tmp_rule) -> None:
        content = """---
name: test
priority: 10
"""
        path = tmp_rule(content)
        result = parse_rule_file(path)

        assert not result.ok
        assert "missing closing frontmatter" in result.error

    def test_invalid_yaml(self, tmp_rule) -> None:
        content = """---
name: [invalid yaml
  broken: {
---
body
"""
        path = tmp_rule(content)
        result = parse_rule_file(path)

        assert not result.ok
        assert "invalid YAML" in result.error

    def test_validation_error(self, tmp_rule) -> None:
        content = """---
name: Invalid Name!
priority: 10

match:
  type: always

route:
  primary:
    provider: anthropic
    model: claude-sonnet-4-6
---

body
"""
        path = tmp_rule(content)
        result = parse_rule_file(path)

        assert not result.ok
        assert "validation error" in result.error

    def test_frontmatter_not_a_mapping(self, tmp_rule) -> None:
        content = """---
- list
- item
---
body
"""
        path = tmp_rule(content)
        result = parse_rule_file(path)

        assert not result.ok
        assert "must be a YAML mapping" in result.error

    def test_nonexistent_file(self) -> None:
        result = parse_rule_file(Path("/nonexistent/file.md"))

        assert not result.ok
        assert "cannot read file" in result.error

    def test_frontmatter_preserved(self, tmp_rule) -> None:
        content = """---
name: test-rule
priority: 50

match:
  type: keyword
  keywords:
    - hello
    - world

route:
  primary:
    provider: openai
    model: gpt-4.1

tags:
  - test
---

# Docs
"""
        path = tmp_rule(content)
        result = parse_rule_file(path)

        assert result.ok
        assert result.frontmatter is not None
        assert result.frontmatter["name"] == "test-rule"
        assert result.schema.match.keywords == ["hello", "world"]
        assert result.schema.tags == ["test"]

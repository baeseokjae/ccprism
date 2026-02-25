"""Tests for all matcher functions."""

from src.engine.matchers import (
    MATCHER_REGISTRY,
    match_always,
    match_content_type,
    match_keyword,
    match_model,
    match_thinking,
    match_token_count,
    match_tool,
)


class TestThinkingMatcher:
    def test_thinking_enabled_true(self) -> None:
        request = {"thinking": {"enabled": True}}
        assert match_thinking(request, {}) is True

    def test_thinking_type_enabled(self) -> None:
        request = {"thinking": {"type": "enabled"}}
        assert match_thinking(request, {}) is True

    def test_thinking_disabled(self) -> None:
        request = {"thinking": {"enabled": False}}
        assert match_thinking(request, {}) is False

    def test_no_thinking(self) -> None:
        request = {"messages": [{"role": "user", "content": "hi"}]}
        assert match_thinking(request, {}) is False

    def test_thinking_empty_dict(self) -> None:
        request = {"thinking": {}}
        assert match_thinking(request, {}) is False


class TestTokenCountMatcher:
    def test_below_threshold(self) -> None:
        request = {"messages": [{"role": "user", "content": "short text"}]}
        assert match_token_count(request, {"threshold": 80000}) is False

    def test_zero_threshold(self) -> None:
        request = {"messages": [{"role": "user", "content": "anything"}]}
        assert match_token_count(request, {"threshold": 0}) is False

    def test_above_threshold_with_long_text(self) -> None:
        long_text = "word " * 50000
        request = {"messages": [{"role": "user", "content": long_text}]}
        assert match_token_count(request, {"threshold": 100}) is True


class TestToolMatcher:
    def test_matching_tool(self) -> None:
        request = {
            "tools": [
                {"function": {"name": "WebSearch", "description": "Search the web"}}
            ]
        }
        assert match_tool(request, {"tool_name": "WebSearch"}) is True

    def test_non_matching_tool(self) -> None:
        request = {
            "tools": [
                {"function": {"name": "Calculator", "description": "Calculate"}}
            ]
        }
        assert match_tool(request, {"tool_name": "WebSearch"}) is False

    def test_no_tools(self) -> None:
        request = {"messages": [{"role": "user", "content": "hi"}]}
        assert match_tool(request, {"tool_name": "WebSearch"}) is False

    def test_empty_tool_name(self) -> None:
        request = {"tools": [{"function": {"name": "Foo"}}]}
        assert match_tool(request, {"tool_name": ""}) is False


class TestModelMatcher:
    def test_exact_match(self) -> None:
        request = {"model": "claude-3-5-haiku-latest"}
        assert match_model(request, {"model_pattern": "claude-3-5-haiku.*"}) is True

    def test_no_match(self) -> None:
        request = {"model": "gpt-4.1"}
        assert match_model(request, {"model_pattern": "claude-3-5-haiku.*"}) is False

    def test_no_model_in_request(self) -> None:
        request = {"messages": []}
        assert match_model(request, {"model_pattern": "claude.*"}) is False

    def test_empty_pattern(self) -> None:
        request = {"model": "gpt-4"}
        assert match_model(request, {"model_pattern": ""}) is False

    def test_invalid_regex(self) -> None:
        request = {"model": "gpt-4"}
        assert match_model(request, {"model_pattern": "[invalid"}) is False


class TestKeywordMatcher:
    def test_keyword_found(self) -> None:
        request = {"messages": [{"role": "user", "content": "Please implement this feature"}]}
        assert match_keyword(request, {"keywords": ["implement"]}) is True

    def test_case_insensitive(self) -> None:
        request = {"messages": [{"role": "user", "content": "IMPLEMENT this"}]}
        assert match_keyword(request, {"keywords": ["implement"]}) is True

    def test_multi_word_keyword(self) -> None:
        request = {"messages": [{"role": "user", "content": "can you fix bug in login?"}]}
        assert match_keyword(request, {"keywords": ["fix bug"]}) is True

    def test_no_match(self) -> None:
        request = {"messages": [{"role": "user", "content": "tell me a joke"}]}
        assert match_keyword(request, {"keywords": ["implement", "refactor"]}) is False

    def test_empty_keywords(self) -> None:
        request = {"messages": [{"role": "user", "content": "anything"}]}
        assert match_keyword(request, {"keywords": []}) is False

    def test_content_blocks(self) -> None:
        request = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "please refactor the code"},
                        {"type": "image_url", "url": "http://example.com/img.png"},
                    ],
                }
            ]
        }
        assert match_keyword(request, {"keywords": ["refactor"]}) is True


class TestAlwaysMatcher:
    def test_always_matches(self) -> None:
        assert match_always({}, {}) is True

    def test_always_with_any_request(self) -> None:
        request = {"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]}
        assert match_always(request, {}) is True


class TestContentTypeMatcher:
    def test_image_block_matches(self) -> None:
        request = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What is in this image?"},
                        {"type": "image", "source": {"type": "base64", "data": "..."}},
                    ],
                }
            ]
        }
        assert match_content_type(request, {"content_types": ["image"]}) is True

    def test_image_url_block_matches(self) -> None:
        request = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe this"},
                        {"type": "image_url", "url": "http://example.com/img.png"},
                    ],
                }
            ]
        }
        assert match_content_type(request, {"content_types": ["image_url"]}) is True

    def test_no_image_does_not_match(self) -> None:
        request = {
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "Hello"}]}
            ]
        }
        assert match_content_type(request, {"content_types": ["image"]}) is False

    def test_string_content_does_not_match(self) -> None:
        request = {
            "messages": [{"role": "user", "content": "Plain text message"}]
        }
        assert match_content_type(request, {"content_types": ["image"]}) is False

    def test_empty_content_types_does_not_match(self) -> None:
        request = {
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "image", "source": {}}],
                }
            ]
        }
        assert match_content_type(request, {"content_types": []}) is False

    def test_multiple_content_types(self) -> None:
        request = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "url": "http://example.com/img.png"},
                    ],
                }
            ]
        }
        assert match_content_type(request, {"content_types": ["image", "image_url"]}) is True

    def test_no_messages_does_not_match(self) -> None:
        request: dict = {"messages": []}
        assert match_content_type(request, {"content_types": ["image"]}) is False


class TestMatcherRegistry:
    def test_all_matchers_registered(self) -> None:
        expected = {
            "thinking",
            "token_count",
            "tool",
            "model",
            "keyword",
            "always",
            "content_type",
            "custom",
            "time_range",
            "ab_test",
        }
        assert set(MATCHER_REGISTRY.keys()) == expected

    def test_registry_values_are_callable(self) -> None:
        for name, fn in MATCHER_REGISTRY.items():
            assert callable(fn), f"Matcher '{name}' is not callable"

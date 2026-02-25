"""Matcher functions for evaluating requests against rule conditions."""

import hashlib
import importlib.util
import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


def _extract_messages_text(request: dict) -> str:
    """Extract all text content from messages in a request."""
    messages = request.get("messages", [])
    parts: list[str] = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
    return "\n".join(parts)


def _estimate_tokens_cjk(text: str) -> int:
    """Estimate token count with CJK-aware heuristic.

    CJK characters typically map to ~1 token each,
    while English words average ~0.75 tokens per word (4 chars per token).
    """
    cjk_count = 0
    other_chars: list[str] = []
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff" or "\u3040" <= ch <= "\u30ff" or "\uac00" <= ch <= "\ud7af":
            cjk_count += 1
        else:
            other_chars.append(ch)
    english_tokens = len("".join(other_chars).split()) * 4 // 3
    return cjk_count + english_tokens


def _count_tokens(request: dict, model: str | None = None) -> int:
    """Count tokens using litellm, tiktoken fallback, or CJK-corrected estimate."""
    text = _extract_messages_text(request)
    messages = request.get("messages", [])

    # Try litellm first
    try:
        from litellm import token_counter  # type: ignore[import-untyped]

        return token_counter(model=model or "gpt-4", messages=messages)
    except Exception:
        pass

    # Try tiktoken
    try:
        import tiktoken  # type: ignore[import-untyped]

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        pass

    # CJK-corrected fallback
    return _estimate_tokens_cjk(text)


def match_thinking(request: dict, params: dict) -> bool:
    """Match requests with extended thinking enabled."""
    thinking = request.get("thinking", {})
    if isinstance(thinking, dict):
        if thinking.get("enabled") is True:
            return True
        if thinking.get("type") == "enabled":
            return True
    return False


def match_token_count(request: dict, params: dict) -> bool:
    """Match requests exceeding a token count threshold."""
    threshold = params.get("threshold", 0)
    if threshold <= 0:
        return False
    count = _count_tokens(request, model=request.get("model"))
    logger.debug("Token count: %d, threshold: %d", count, threshold)
    return count >= threshold


def match_tool(request: dict, params: dict) -> bool:
    """Match requests containing a specific tool."""
    tool_name = params.get("tool_name", "")
    if not tool_name:
        return False
    tools = request.get("tools", [])
    for tool in tools:
        fn = tool.get("function", {})
        if fn.get("name") == tool_name:
            return True
    return False


def match_model(request: dict, params: dict) -> bool:
    """Match requests by model name regex pattern."""
    pattern = params.get("model_pattern", "")
    if not pattern:
        return False
    model = request.get("model", "")
    if not model:
        return False
    try:
        return bool(re.search(pattern, model))
    except re.error:
        logger.warning("Invalid model regex pattern: %s", pattern)
        return False


def match_keyword(request: dict, params: dict) -> bool:
    """Match requests containing any of the specified keywords (case-insensitive)."""
    keywords = params.get("keywords", [])
    if not keywords:
        return False
    text = _extract_messages_text(request).lower()
    return any(kw.lower() in text for kw in keywords)


def match_always(request: dict, params: dict) -> bool:
    """Always matches. Used for default/catch-all rules."""
    return True


def match_content_type(request: dict, params: dict) -> bool:
    """Match requests containing specific content block types (e.g., image).

    Checks message content blocks for matching 'type' fields.
    Supports both Anthropic format (type: "image") and OpenAI format (type: "image_url").
    """
    content_types = params.get("content_types", [])
    if not content_types:
        return False

    messages = request.get("messages", [])
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    block_type = block.get("type", "")
                    if block_type in content_types:
                        return True
    return False


def match_custom(request: dict, params: dict) -> bool:
    """Match requests using an external Python script.

    The script must export a ``def match(request: dict) -> bool`` function.
    Returns False if the script path is missing, the file does not exist,
    or the script does not define a ``match`` function.
    """
    script_path = params.get("script_path", "")
    if not script_path:
        return False
    try:
        spec = importlib.util.spec_from_file_location("_custom_matcher", script_path)
        if spec is None or spec.loader is None:
            logger.warning("Cannot load custom matcher script: %s", script_path)
            return False
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        match_fn = getattr(module, "match", None)
        if not callable(match_fn):
            logger.warning("Custom matcher script has no callable 'match' function: %s", script_path)
            return False
        return bool(match_fn(request))
    except FileNotFoundError:
        logger.warning("Custom matcher script not found: %s", script_path)
        return False
    except Exception:
        logger.exception("Error executing custom matcher script: %s", script_path)
        return False


def match_time_range(request: dict, params: dict) -> bool:
    """Match requests that arrive within a specified hour range.

    Supports overnight ranges where ``start_hour`` > ``end_hour``
    (e.g. start_hour=22, end_hour=6 matches 22:00–06:00).
    """
    start_hour: int = params.get("start_hour", 0)
    end_hour: int = params.get("end_hour", 0)
    timezone: str = params.get("timezone", "UTC")
    try:
        tz = ZoneInfo(timezone)
    except Exception:
        logger.warning("Invalid timezone '%s', falling back to UTC", timezone)
        tz = ZoneInfo("UTC")
    current_hour = datetime.now(tz=tz).hour
    if start_hour <= end_hour:
        return start_hour <= current_hour < end_hour
    # Overnight range: e.g. 22 <= hour or hour < 6
    return current_hour >= start_hour or current_hour < end_hour


def match_ab_test(request: dict, params: dict) -> bool:
    """Deterministically assign requests to an A/B test bucket.

    Uses a hash of ``experiment_name`` concatenated with the first message's
    content so that identical requests always land in the same bucket.
    Returns True when ``hash % 100 < percentage``.
    """
    percentage: int = params.get("percentage", 0)
    if percentage <= 0:
        return False
    if percentage >= 100:
        return True
    experiment_name: str = params.get("experiment_name", "")
    messages = request.get("messages", [])
    first_content = ""
    if messages:
        content = messages[0].get("content", "")
        if isinstance(content, str):
            first_content = content
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    first_content = block.get("text", "")
                    break
    raw = f"{experiment_name}:{first_content}"
    digest = hashlib.sha256(raw.encode()).hexdigest()
    bucket = int(digest[:8], 16) % 100
    return bucket < percentage


MATCHER_REGISTRY: dict[str, callable] = {
    "thinking": match_thinking,
    "token_count": match_token_count,
    "tool": match_tool,
    "model": match_model,
    "keyword": match_keyword,
    "always": match_always,
    "content_type": match_content_type,
    "custom": match_custom,
    "time_range": match_time_range,
    "ab_test": match_ab_test,
}

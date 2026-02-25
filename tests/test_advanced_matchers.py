"""Tests for advanced matcher functions: custom, time_range, ab_test."""

import textwrap
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from src.engine.matchers import (
    MATCHER_REGISTRY,
    match_ab_test,
    match_custom,
    match_time_range,
)


# ---------------------------------------------------------------------------
# TestCustomMatcher
# ---------------------------------------------------------------------------


class TestCustomMatcher:
    def test_custom_matcher_with_valid_script(self, tmp_path: pytest.TempPathFactory) -> None:
        """A script that always returns True should cause the matcher to return True."""
        script = tmp_path / "always_true.py"
        script.write_text(
            textwrap.dedent("""\
                def match(request: dict) -> bool:
                    return True
            """)
        )
        request = {"messages": [{"role": "user", "content": "hello"}]}
        assert match_custom(request, {"script_path": str(script)}) is True

    def test_custom_matcher_with_false_script(self, tmp_path: pytest.TempPathFactory) -> None:
        """A script that always returns False should cause the matcher to return False."""
        script = tmp_path / "always_false.py"
        script.write_text(
            textwrap.dedent("""\
                def match(request: dict) -> bool:
                    return False
            """)
        )
        request = {"messages": [{"role": "user", "content": "hello"}]}
        assert match_custom(request, {"script_path": str(script)}) is False

    def test_custom_matcher_missing_file(self) -> None:
        """A non-existent script path must return False."""
        assert match_custom({}, {"script_path": "/nonexistent/path/matcher.py"}) is False

    def test_custom_matcher_no_match_function(self, tmp_path: pytest.TempPathFactory) -> None:
        """A script without a 'match' function must return False."""
        script = tmp_path / "no_match.py"
        script.write_text("x = 42\n")
        assert match_custom({}, {"script_path": str(script)}) is False

    def test_custom_matcher_empty_path(self) -> None:
        """An empty script_path must return False without errors."""
        assert match_custom({}, {"script_path": ""}) is False
        assert match_custom({}, {}) is False


# ---------------------------------------------------------------------------
# TestTimeRangeMatcher
# ---------------------------------------------------------------------------


class TestTimeRangeMatcher:
    def test_within_range(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When the current hour falls inside start..end, return True."""
        fixed = datetime(2024, 6, 15, 14, 30, tzinfo=ZoneInfo("UTC"))
        monkeypatch.setattr("src.engine.matchers.datetime", _FakeDatetime(fixed))
        assert match_time_range({}, {"start_hour": 9, "end_hour": 18, "timezone": "UTC"}) is True

    def test_outside_range(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When the current hour falls outside start..end, return False."""
        fixed = datetime(2024, 6, 15, 20, 0, tzinfo=ZoneInfo("UTC"))
        monkeypatch.setattr("src.engine.matchers.datetime", _FakeDatetime(fixed))
        assert match_time_range({}, {"start_hour": 9, "end_hour": 18, "timezone": "UTC"}) is False

    def test_overnight_range_within(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """start_hour=22, end_hour=6: hour 23 should match."""
        fixed = datetime(2024, 6, 15, 23, 0, tzinfo=ZoneInfo("UTC"))
        monkeypatch.setattr("src.engine.matchers.datetime", _FakeDatetime(fixed))
        assert match_time_range({}, {"start_hour": 22, "end_hour": 6, "timezone": "UTC"}) is True

    def test_overnight_range_outside(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """start_hour=22, end_hour=6: hour 12 should NOT match."""
        fixed = datetime(2024, 6, 15, 12, 0, tzinfo=ZoneInfo("UTC"))
        monkeypatch.setattr("src.engine.matchers.datetime", _FakeDatetime(fixed))
        assert match_time_range({}, {"start_hour": 22, "end_hour": 6, "timezone": "UTC"}) is False

    def test_default_timezone_utc(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When timezone is not provided, UTC must be used."""
        fixed = datetime(2024, 6, 15, 10, 0, tzinfo=ZoneInfo("UTC"))
        monkeypatch.setattr("src.engine.matchers.datetime", _FakeDatetime(fixed))
        # no 'timezone' key in params → should default to UTC and match 9..18
        assert match_time_range({}, {"start_hour": 9, "end_hour": 18}) is True


# ---------------------------------------------------------------------------
# TestAbTestMatcher
# ---------------------------------------------------------------------------


class TestAbTestMatcher:
    _request = {"messages": [{"role": "user", "content": "hello world"}]}

    def test_within_percentage(self) -> None:
        """percentage=100 must always return True."""
        assert match_ab_test(self._request, {"percentage": 100, "experiment_name": "exp"}) is True

    def test_zero_percentage(self) -> None:
        """percentage=0 must always return False."""
        assert match_ab_test(self._request, {"percentage": 0, "experiment_name": "exp"}) is False

    def test_deterministic(self) -> None:
        """The same request must always produce the same result."""
        params = {"percentage": 50, "experiment_name": "stable_exp"}
        results = {match_ab_test(self._request, params) for _ in range(10)}
        # All 10 calls must return the identical value → set has exactly 1 element
        assert len(results) == 1

    def test_different_experiments(self) -> None:
        """Different experiment names can produce different hash buckets."""
        import hashlib

        def _bucket(exp: str) -> int:
            content = "hello world"
            raw = f"{exp}:{content}"
            digest = hashlib.sha256(raw.encode()).hexdigest()
            return int(digest[:8], 16) % 100

        bucket_a = _bucket("experiment_a")
        bucket_b = _bucket("experiment_b")
        # The buckets are deterministic and (in general) differ for distinct names
        assert bucket_a != bucket_b


# ---------------------------------------------------------------------------
# TestMatcherRegistry (updated)
# ---------------------------------------------------------------------------


class TestMatcherRegistryAdvanced:
    def test_new_matchers_registered(self) -> None:
        """custom, time_range, and ab_test must be present in the registry."""
        assert "custom" in MATCHER_REGISTRY
        assert "time_range" in MATCHER_REGISTRY
        assert "ab_test" in MATCHER_REGISTRY

    def test_new_matchers_callable(self) -> None:
        for name in ("custom", "time_range", "ab_test"):
            assert callable(MATCHER_REGISTRY[name]), f"Matcher '{name}' is not callable"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class _FakeDatetime:
    """Minimal datetime replacement that returns a fixed 'now'."""

    def __init__(self, fixed: datetime) -> None:
        self._fixed = fixed

    def now(self, tz: ZoneInfo | None = None) -> datetime:
        if tz is not None:
            return self._fixed.astimezone(tz)
        return self._fixed

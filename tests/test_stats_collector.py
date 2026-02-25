"""Tests for the stats collector."""

from src.engine.stats_collector import StatsCollector


class TestStatsCollector:
    def test_initial_state(self) -> None:
        collector = StatsCollector()
        snap = collector.snapshot()
        assert snap["total_requests"] == 0
        assert snap["success_count"] == 0
        assert snap["failure_count"] == 0
        assert snap["rule_matches"] == {}
        assert snap["provider_calls"] == {}

    def test_record_request(self) -> None:
        collector = StatsCollector()
        collector.record_request("thinking-requests", "anthropic")
        collector.record_request("default", "anthropic")
        collector.record_request("thinking-requests", "openai")

        snap = collector.snapshot()
        assert snap["total_requests"] == 3
        assert snap["rule_matches"]["thinking-requests"] == 2
        assert snap["rule_matches"]["default"] == 1
        assert snap["provider_calls"]["anthropic"] == 2
        assert snap["provider_calls"]["openai"] == 1

    def test_record_success_failure(self) -> None:
        collector = StatsCollector()
        collector.record_success()
        collector.record_success()
        collector.record_failure()

        snap = collector.snapshot()
        assert snap["success_count"] == 2
        assert snap["failure_count"] == 1

    def test_uptime(self) -> None:
        collector = StatsCollector()
        snap = collector.snapshot()
        assert snap["uptime_seconds"] >= 0

    def test_snapshot_returns_copy(self) -> None:
        collector = StatsCollector()
        collector.record_request("rule-a", "provider-a")
        snap1 = collector.snapshot()
        collector.record_request("rule-b", "provider-b")
        snap2 = collector.snapshot()

        assert snap1["total_requests"] == 1
        assert snap2["total_requests"] == 2

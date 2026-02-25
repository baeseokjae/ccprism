"""Lightweight in-memory statistics collector for the gateway."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from threading import Lock

logger = logging.getLogger("ccprism.stats")


class StatsCollector:
    """Thread-safe in-memory counter for request statistics."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._total_requests: int = 0
        self._rule_matches: dict[str, int] = defaultdict(int)
        self._provider_calls: dict[str, int] = defaultdict(int)
        self._success_count: int = 0
        self._failure_count: int = 0
        self._start_time: float = time.time()

    def record_request(self, rule_name: str, provider: str) -> None:
        """Record a routing decision."""
        with self._lock:
            self._total_requests += 1
            self._rule_matches[rule_name] += 1
            self._provider_calls[provider] += 1

    def record_success(self) -> None:
        """Record a successful API call."""
        with self._lock:
            self._success_count += 1

    def record_failure(self) -> None:
        """Record a failed API call."""
        with self._lock:
            self._failure_count += 1

    def snapshot(self) -> dict:
        """Return a point-in-time snapshot of all stats."""
        with self._lock:
            return {
                "total_requests": self._total_requests,
                "success_count": self._success_count,
                "failure_count": self._failure_count,
                "uptime_seconds": round(time.time() - self._start_time, 1),
                "rule_matches": dict(self._rule_matches),
                "provider_calls": dict(self._provider_calls),
            }

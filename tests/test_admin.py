"""Tests for admin API endpoints."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.config import get_settings
from src.engine.rule_engine import RuleEngine
from src.engine.stats_collector import StatsCollector
from src.main import create_app


@pytest.fixture
def app_with_state(monkeypatch):
    """Create a test app with rule engine and stats collector."""
    monkeypatch.setenv("CCPRISM_AUTH__GATEWAY_MASTER_KEY", "test-admin-key-" + "a" * 32)
    get_settings.cache_clear()
    app = create_app()
    rules_dir = Path(__file__).parent.parent / "rules"
    app.state.rule_engine = RuleEngine(rules_dir)
    app.state.stats_collector = StatsCollector()

    mock_cm = MagicMock()
    mock_cm._adapters = {}
    app.state.credential_manager = mock_cm

    yield app
    get_settings.cache_clear()


@pytest.fixture
def client(app_with_state):
    return TestClient(
        app_with_state, raise_server_exceptions=False,
        headers={"x-api-key": "test-admin-key-" + "a" * 32},
    )


class TestAdminRules:
    def test_list_rules(self, client: TestClient) -> None:
        response = client.get("/admin/rules")
        assert response.status_code == 200
        data = response.json()
        assert "rules" in data
        assert "total" in data
        assert data["total"] >= 6

    def test_get_rule_by_name(self, client: TestClient) -> None:
        response = client.get("/admin/rules/default")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "default"
        assert "documentation" in data
        assert "match_params" in data

    def test_get_nonexistent_rule(self, client: TestClient) -> None:
        response = client.get("/admin/rules/nonexistent")
        assert response.status_code == 404

    def test_reload_rules(self, client: TestClient) -> None:
        response = client.post("/admin/rules/reload")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "reloaded"
        assert "current_count" in data


class TestAdminStats:
    def test_get_stats(self, client: TestClient) -> None:
        response = client.get("/admin/stats")
        assert response.status_code == 200
        data = response.json()
        assert "stats" in data

    def test_stats_with_recorded_data(self, app_with_state, client: TestClient) -> None:
        stats = app_with_state.state.stats_collector
        stats.record_request("default", "anthropic")
        stats.record_success()

        response = client.get("/admin/stats")
        data = response.json()
        assert data["stats"]["total_requests"] == 1
        assert data["stats"]["success_count"] == 1


class TestAdminProviders:
    def test_get_providers(self, client: TestClient) -> None:
        response = client.get("/admin/providers")
        assert response.status_code == 200
        data = response.json()
        assert "providers" in data
        assert "total" in data

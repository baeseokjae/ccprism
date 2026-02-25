"""Tests for the cost database."""

import time

import pytest

from src.storage.cost_db import CostDB


@pytest.fixture
async def db(tmp_path):
    """Create a temporary CostDB for testing."""
    db_path = str(tmp_path / "test_costs.db")
    db = CostDB(db_path=db_path)
    await db.open()
    yield db
    await db.close()


class TestCostDB:
    async def test_record_and_daily_summary(self, db: CostDB) -> None:
        await db.record("default", "anthropic", "claude-sonnet-4-6", 100, 50, 0.001)
        await db.record("default", "anthropic", "claude-sonnet-4-6", 200, 100, 0.002)

        rows = await db.get_daily_summary(days=1)
        assert len(rows) == 1
        assert rows[0]["requests"] == 2
        assert rows[0]["input_tokens"] == 300
        assert rows[0]["output_tokens"] == 150
        assert rows[0]["total_cost"] == 0.003

    async def test_provider_summary(self, db: CostDB) -> None:
        await db.record("rule-a", "anthropic", "claude-sonnet-4-6", 100, 50, 0.01)
        await db.record("rule-b", "openai", "gpt-4.1", 200, 100, 0.05)
        await db.record("rule-a", "anthropic", "claude-opus-4-6", 300, 150, 0.02)

        rows = await db.get_provider_summary(days=30)
        assert len(rows) == 2
        # openai has higher cost, should be first
        assert rows[0]["provider"] == "openai"
        assert rows[0]["total_cost"] == 0.05
        assert rows[1]["provider"] == "anthropic"
        assert rows[1]["total_cost"] == 0.03

    async def test_rule_summary(self, db: CostDB) -> None:
        await db.record("thinking", "anthropic", "claude-opus-4-6", 100, 50, 0.05)
        await db.record("default", "anthropic", "claude-sonnet-4-6", 200, 100, 0.01)
        await db.record("thinking", "openai", "o3", 150, 75, 0.03)

        rows = await db.get_rule_summary(days=30)
        assert len(rows) == 2
        assert rows[0]["rule_name"] == "thinking"
        assert rows[0]["total_cost"] == 0.08
        assert rows[0]["requests"] == 2

    async def test_monthly_total(self, db: CostDB) -> None:
        await db.record("default", "anthropic", "claude-sonnet-4-6", 100, 50, 0.123)
        await db.record("default", "openai", "gpt-4.1", 200, 100, 0.456)

        total = await db.get_monthly_total()
        assert total == 0.579

    async def test_empty_db_returns_empty(self, db: CostDB) -> None:
        assert await db.get_daily_summary() == []
        assert await db.get_provider_summary() == []
        assert await db.get_rule_summary() == []
        assert await db.get_monthly_total() == 0.0

    async def test_purge_old_records(self, db: CostDB) -> None:
        # Insert a record with an old timestamp directly
        old_ts = time.time() - 100 * 86400  # 100 days ago
        await db._db.execute(
            "INSERT INTO cost_log (timestamp, rule_name, provider, model, input_tokens, output_tokens, cost_usd) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (old_ts, "old-rule", "anthropic", "claude-sonnet-4-6", 100, 50, 0.001),
        )
        await db._db.commit()

        # Insert a recent record
        await db.record("new-rule", "anthropic", "claude-sonnet-4-6", 100, 50, 0.002)

        deleted = await db.purge_old_records(retention_days=90)
        assert deleted == 1

        # Only the recent record should remain
        rows = await db.get_rule_summary(days=365)
        assert len(rows) == 1
        assert rows[0]["rule_name"] == "new-rule"

    async def test_closed_db_returns_defaults(self) -> None:
        db = CostDB(db_path="/tmp/nonexistent_test.db")
        # Not opened — should return safe defaults
        assert await db.get_daily_summary() == []
        assert await db.get_monthly_total() == 0.0
        await db.close()  # Should not raise

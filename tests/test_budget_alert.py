"""Tests for budget alerting."""

from unittest.mock import AsyncMock

import pytest

from src.engine.budget_alert import BudgetAlert


class TestBudgetAlert:
    async def test_no_db_returns_disabled(self) -> None:
        alert = BudgetAlert(cost_db=None, monthly_budget_usd=100.0)
        result = await alert.check()
        assert result == {"enabled": False}

    async def test_no_budget_returns_disabled(self) -> None:
        mock_db = AsyncMock()
        alert = BudgetAlert(cost_db=mock_db, monthly_budget_usd=0.0)
        result = await alert.check()
        assert result == {"enabled": False}

    async def test_under_budget_ok(self) -> None:
        mock_db = AsyncMock()
        mock_db.get_monthly_total.return_value = 50.0

        alert = BudgetAlert(cost_db=mock_db, monthly_budget_usd=100.0)
        result = await alert.check()
        assert result["status"] == "ok"
        assert result["percentage"] == 50.0
        assert result["monthly_spent_usd"] == 50.0

    async def test_warning_at_80_pct(self) -> None:
        mock_db = AsyncMock()
        mock_db.get_monthly_total.return_value = 85.0

        alert = BudgetAlert(cost_db=mock_db, monthly_budget_usd=100.0)
        result = await alert.check()
        assert result["status"] == "warning"
        assert result["percentage"] == 85.0

    async def test_exceeded_at_100_pct(self) -> None:
        mock_db = AsyncMock()
        mock_db.get_monthly_total.return_value = 120.0

        alert = BudgetAlert(cost_db=mock_db, monthly_budget_usd=100.0)
        result = await alert.check()
        assert result["status"] == "exceeded"
        assert result["percentage"] == 120.0

    async def test_no_duplicate_alerts(self) -> None:
        mock_db = AsyncMock()
        mock_db.get_monthly_total.return_value = 85.0

        alert = BudgetAlert(cost_db=mock_db, monthly_budget_usd=100.0)
        result1 = await alert.check()
        assert result1["status"] == "warning"

        # Second call at same level should be "ok" (already alerted)
        result2 = await alert.check()
        assert result2["status"] == "ok"

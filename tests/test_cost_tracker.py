"""Tests for the cost tracker."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.engine.cost_tracker import CostTracker


class TestCostTracker:
    async def test_record_from_response(self) -> None:
        mock_db = AsyncMock()
        tracker = CostTracker(cost_db=mock_db)

        response = MagicMock()
        response.usage.prompt_tokens = 100
        response.usage.completion_tokens = 50
        response._hidden_params = {"response_cost": 0.0025}

        await tracker.record_from_response(
            rule_name="default",
            model="anthropic/claude-sonnet-4-6",
            response_obj=response,
            kwargs={},
        )

        mock_db.record.assert_called_once_with(
            rule_name="default",
            provider="anthropic",
            model="anthropic/claude-sonnet-4-6",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.0025,
        )

    async def test_no_db_is_noop(self) -> None:
        tracker = CostTracker(cost_db=None)
        response = MagicMock()
        # Should not raise
        await tracker.record_from_response(
            rule_name="default",
            model="anthropic/claude-sonnet-4-6",
            response_obj=response,
            kwargs={},
        )

    async def test_no_usage_records_zeros(self) -> None:
        mock_db = AsyncMock()
        tracker = CostTracker(cost_db=mock_db)

        response = MagicMock(spec=[])  # No usage attribute
        response._hidden_params = {}

        await tracker.record_from_response(
            rule_name="default",
            model="openai/gpt-4.1",
            response_obj=response,
            kwargs={},
        )

        call_kwargs = mock_db.record.call_args.kwargs
        assert call_kwargs["input_tokens"] == 0
        assert call_kwargs["output_tokens"] == 0

    async def test_provider_extracted_from_model(self) -> None:
        mock_db = AsyncMock()
        tracker = CostTracker(cost_db=mock_db)

        response = MagicMock()
        response.usage.prompt_tokens = 10
        response.usage.completion_tokens = 5
        response._hidden_params = {"response_cost": 0.001}

        await tracker.record_from_response(
            rule_name="test",
            model="deepseek/deepseek-chat",
            response_obj=response,
            kwargs={},
        )

        call_kwargs = mock_db.record.call_args.kwargs
        assert call_kwargs["provider"] == "deepseek"

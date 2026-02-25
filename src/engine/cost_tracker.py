"""Cost tracking module that bridges LiteLLM responses to the cost database."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..storage.cost_db import CostDB

logger = logging.getLogger("ccprism.cost_tracker")


class CostTracker:
    """Extracts cost data from LiteLLM responses and persists to CostDB."""

    def __init__(self, cost_db: CostDB | None = None) -> None:
        self._db = cost_db

    async def record_from_response(
        self,
        rule_name: str,
        model: str,
        response_obj: Any,
        kwargs: dict,
    ) -> None:
        """Extract cost info from a LiteLLM response and record it."""
        if not self._db:
            return

        provider = model.split("/")[0] if "/" in model else "unknown"

        # Extract token usage
        usage = getattr(response_obj, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
        output_tokens = getattr(usage, "completion_tokens", 0) if usage else 0

        # Extract cost — LiteLLM adds _hidden_params with response_cost
        hidden = getattr(response_obj, "_hidden_params", {}) or {}
        cost_usd = hidden.get("response_cost", 0.0) or 0.0

        # Fallback: try litellm.completion_cost()
        if cost_usd == 0.0 and (input_tokens or output_tokens):
            try:
                from litellm import completion_cost

                cost_usd = completion_cost(
                    model=model,
                    prompt_tokens=input_tokens,
                    completion_tokens=output_tokens,
                )
            except Exception:
                pass

        await self._db.record(
            rule_name=rule_name,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )

        logger.debug(
            "Cost recorded: rule=%s model=%s in=%d out=%d cost=$%.6f",
            rule_name, model, input_tokens, output_tokens, cost_usd,
        )

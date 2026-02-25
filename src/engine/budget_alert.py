"""Budget alerting based on cost thresholds."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..storage.cost_db import CostDB

logger = logging.getLogger("ccprism.budget")


class BudgetAlert:
    """Monitors spending against configured budgets and logs warnings."""

    def __init__(
        self,
        cost_db: CostDB | None = None,
        monthly_budget_usd: float = 0.0,
    ) -> None:
        self._db = cost_db
        self.monthly_budget_usd = monthly_budget_usd
        self._last_alert_pct: float = 0.0

    async def check(self) -> dict:
        """Check current spending against budget. Returns status dict."""
        if not self._db or self.monthly_budget_usd <= 0:
            return {"enabled": False}

        monthly_total = await self._db.get_monthly_total()
        pct = (monthly_total / self.monthly_budget_usd) * 100 if self.monthly_budget_usd > 0 else 0

        status = "ok"
        if pct >= 100 and self._last_alert_pct < 100:
            logger.critical(
                "Monthly budget EXCEEDED: $%.2f / $%.2f (%.1f%%)",
                monthly_total, self.monthly_budget_usd, pct,
            )
            status = "exceeded"
            self._last_alert_pct = pct
        elif pct >= 80 and self._last_alert_pct < 80:
            logger.warning(
                "Monthly budget at 80%%: $%.2f / $%.2f (%.1f%%)",
                monthly_total, self.monthly_budget_usd, pct,
            )
            status = "warning"
            self._last_alert_pct = pct

        return {
            "enabled": True,
            "monthly_budget_usd": self.monthly_budget_usd,
            "monthly_spent_usd": round(monthly_total, 6),
            "percentage": round(pct, 1),
            "status": status,
        }

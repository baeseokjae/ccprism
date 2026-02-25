"""SQLite-based cost logging with async access via aiosqlite."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import aiosqlite

logger = logging.getLogger("ccprism.storage.cost_db")

_DEFAULT_DB_PATH = "~/.ccprism/costs.db"
_RETENTION_DAYS = 90

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS cost_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    rule_name TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0.0
);
"""

_CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_cost_log_timestamp ON cost_log (timestamp);
"""


class CostDB:
    """Async SQLite store for per-request cost records."""

    def __init__(self, db_path: str = _DEFAULT_DB_PATH) -> None:
        self._path = Path(db_path).expanduser()
        self._db: aiosqlite.Connection | None = None

    async def open(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self._path))
        await self._db.execute(_CREATE_TABLE)
        await self._db.execute(_CREATE_INDEX)
        await self._db.commit()
        logger.info("Cost DB opened at %s", self._path)

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    async def record(
        self,
        rule_name: str,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
    ) -> None:
        if not self._db:
            return
        await self._db.execute(
            "INSERT INTO cost_log (timestamp, rule_name, provider, model, input_tokens, output_tokens, cost_usd) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (time.time(), rule_name, provider, model, input_tokens, output_tokens, cost_usd),
        )
        await self._db.commit()

    async def get_daily_summary(self, days: int = 7) -> list[dict]:
        if not self._db:
            return []
        cutoff = time.time() - days * 86400
        cursor = await self._db.execute(
            "SELECT date(timestamp, 'unixepoch') AS day, "
            "COUNT(*) AS requests, "
            "SUM(input_tokens) AS input_tokens, "
            "SUM(output_tokens) AS output_tokens, "
            "SUM(cost_usd) AS total_cost "
            "FROM cost_log WHERE timestamp >= ? "
            "GROUP BY day ORDER BY day",
            (cutoff,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "day": r[0],
                "requests": r[1],
                "input_tokens": r[2],
                "output_tokens": r[3],
                "total_cost": round(r[4], 6),
            }
            for r in rows
        ]

    async def get_provider_summary(self, days: int = 30) -> list[dict]:
        if not self._db:
            return []
        cutoff = time.time() - days * 86400
        cursor = await self._db.execute(
            "SELECT provider, COUNT(*) AS requests, "
            "SUM(input_tokens) AS input_tokens, "
            "SUM(output_tokens) AS output_tokens, "
            "SUM(cost_usd) AS total_cost "
            "FROM cost_log WHERE timestamp >= ? "
            "GROUP BY provider ORDER BY total_cost DESC",
            (cutoff,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "provider": r[0],
                "requests": r[1],
                "input_tokens": r[2],
                "output_tokens": r[3],
                "total_cost": round(r[4], 6),
            }
            for r in rows
        ]

    async def get_rule_summary(self, days: int = 30) -> list[dict]:
        if not self._db:
            return []
        cutoff = time.time() - days * 86400
        cursor = await self._db.execute(
            "SELECT rule_name, COUNT(*) AS requests, "
            "SUM(cost_usd) AS total_cost "
            "FROM cost_log WHERE timestamp >= ? "
            "GROUP BY rule_name ORDER BY total_cost DESC",
            (cutoff,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "rule_name": r[0],
                "requests": r[1],
                "total_cost": round(r[2], 6),
            }
            for r in rows
        ]

    async def get_monthly_total(self) -> float:
        """Get total cost for the current calendar month."""
        if not self._db:
            return 0.0
        cursor = await self._db.execute(
            "SELECT COALESCE(SUM(cost_usd), 0.0) FROM cost_log "
            "WHERE date(timestamp, 'unixepoch') >= date('now', 'start of month')"
        )
        row = await cursor.fetchone()
        return round(row[0], 6) if row else 0.0

    async def purge_old_records(self, retention_days: int = _RETENTION_DAYS) -> int:
        if not self._db:
            return 0
        cutoff = time.time() - retention_days * 86400
        cursor = await self._db.execute(
            "DELETE FROM cost_log WHERE timestamp < ?", (cutoff,)
        )
        await self._db.commit()
        deleted = cursor.rowcount
        if deleted:
            logger.info("Purged %d cost records older than %d days", deleted, retention_days)
        return deleted

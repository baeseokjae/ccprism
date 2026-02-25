"""Alert handler for forwarding critical log records to external services."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    pass


class AlertHandler(logging.Handler):
    """Logging handler that forwards critical records to a Slack webhook."""

    def __init__(self, webhook_url: str, min_level: int = logging.CRITICAL) -> None:
        super().__init__(level=min_level)
        self.webhook_url = webhook_url
        self.min_level = min_level
        self._client = httpx.Client(timeout=5.0)

    def emit(self, record: logging.LogRecord) -> None:
        """Send the log record to the configured webhook if level meets threshold."""
        if record.levelno < self.min_level:
            return

        payload = {"text": f":rotating_light: [ccprism ALERT] {record.getMessage()}"}
        try:
            self._client.post(self.webhook_url, json=payload)
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(
                f"AlertHandler: failed to send webhook to {self.webhook_url!r}: {exc}\n"
            )

    def close(self) -> None:
        """Close the underlying HTTP client and clean up resources."""
        try:
            self._client.close()
        except Exception:  # noqa: BLE001
            pass
        super().close()


def setup_alert_handler(webhook_url: str | None) -> AlertHandler | None:
    """Attach an AlertHandler to the 'ccprism' logger if a webhook URL is provided.

    Returns the created handler, or None if no URL was given.
    """
    if not webhook_url:
        return None

    handler = AlertHandler(webhook_url=webhook_url)
    logging.getLogger("ccprism").addHandler(handler)
    return handler

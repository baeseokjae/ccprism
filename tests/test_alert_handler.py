"""Tests for monitoring AlertHandler."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from src.monitoring.alert_handler import AlertHandler, setup_alert_handler


class TestAlertHandler:
    def test_handler_emits_on_critical(self) -> None:
        """CRITICAL log records trigger an HTTP POST to the webhook."""
        handler = AlertHandler(webhook_url="https://hooks.slack.com/test")

        with patch.object(handler._client, "post") as mock_post:
            record = logging.LogRecord(
                name="ccprism",
                level=logging.CRITICAL,
                pathname="",
                lineno=0,
                msg="budget exceeded",
                args=(),
                exc_info=None,
            )
            handler.emit(record)

        mock_post.assert_called_once()

    def test_handler_ignores_below_level(self) -> None:
        """Records below the minimum level are silently dropped."""
        handler = AlertHandler(webhook_url="https://hooks.slack.com/test")

        with patch.object(handler._client, "post") as mock_post:
            record = logging.LogRecord(
                name="ccprism",
                level=logging.WARNING,
                pathname="",
                lineno=0,
                msg="just a warning",
                args=(),
                exc_info=None,
            )
            handler.emit(record)

        mock_post.assert_not_called()

    def test_handler_payload_format(self) -> None:
        """POST payload must be Slack-compatible and contain the alert emoji."""
        handler = AlertHandler(webhook_url="https://hooks.slack.com/test")

        with patch.object(handler._client, "post") as mock_post:
            record = logging.LogRecord(
                name="ccprism",
                level=logging.CRITICAL,
                pathname="",
                lineno=0,
                msg="something broke",
                args=(),
                exc_info=None,
            )
            handler.emit(record)

        _, kwargs = mock_post.call_args
        payload = kwargs.get("json") or mock_post.call_args[0][1] if mock_post.call_args[0][1:] else kwargs.get("json")
        # Support both positional and keyword argument styles
        call_kwargs = mock_post.call_args.kwargs
        call_args = mock_post.call_args.args
        json_payload = call_kwargs.get("json") if call_kwargs else None
        if json_payload is None and len(call_args) > 1:
            json_payload = call_args[1]

        assert json_payload is not None
        assert ":rotating_light:" in json_payload["text"]
        assert "ccprism ALERT" in json_payload["text"]
        assert "something broke" in json_payload["text"]

    def test_handler_tolerates_network_error(self) -> None:
        """A network failure in emit() must not raise an exception."""
        handler = AlertHandler(webhook_url="https://hooks.slack.com/test")

        with patch.object(handler._client, "post", side_effect=Exception("connection refused")):
            record = logging.LogRecord(
                name="ccprism",
                level=logging.CRITICAL,
                pathname="",
                lineno=0,
                msg="error",
                args=(),
                exc_info=None,
            )
            # Must not raise
            handler.emit(record)

    def test_setup_returns_none_without_url(self) -> None:
        """setup_alert_handler returns None when no webhook URL is provided."""
        result = setup_alert_handler(None)
        assert result is None

    def test_setup_returns_none_for_empty_string(self) -> None:
        """setup_alert_handler returns None for an empty webhook URL string."""
        result = setup_alert_handler("")
        assert result is None

    def test_setup_adds_handler_to_logger(self) -> None:
        """setup_alert_handler attaches an AlertHandler to the 'ccprism' logger."""
        ccprism_logger = logging.getLogger("ccprism")
        initial_count = len(ccprism_logger.handlers)

        handler = setup_alert_handler("https://hooks.slack.com/test")
        assert handler is not None
        assert isinstance(handler, AlertHandler)

        try:
            assert handler in ccprism_logger.handlers
            assert len(ccprism_logger.handlers) == initial_count + 1
        finally:
            ccprism_logger.removeHandler(handler)
            handler.close()

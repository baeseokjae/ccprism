"""LiteLLM pre/post call hooks for credential injection and logging.

Role: Credential injection + metadata/header manipulation ONLY.
Model selection is handled by litellm_routing.py (CustomRoutingStrategyBase).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..auth.credential_manager import CredentialManager
    from .cost_tracker import CostTracker
    from .stats_collector import StatsCollector

logger = logging.getLogger("ccprism.hooks")


class GatewayHooks:
    """LiteLLM callback hooks for ccprism gateway.

    Handles:
    - Credential injection (pre-call)
    - Success/failure logging (post-call)

    Does NOT handle model selection (that's MDRuleBasedRouting's job).
    """

    def __init__(
        self,
        credential_manager: CredentialManager,
        stats_collector: StatsCollector | None = None,
        cost_tracker: CostTracker | None = None,
    ) -> None:
        self.credential_manager = credential_manager
        self.stats_collector = stats_collector
        self.cost_tracker = cost_tracker

    async def async_pre_call_hook(
        self,
        user_api_key_dict: dict,
        cache: Any,
        data: dict,
        call_type: str,
    ) -> dict:
        """Inject credentials before LiteLLM makes the API call.

        Called after routing strategy has selected the deployment.
        Only injects credentials - never changes the model.
        """
        model = data.get("model", "")
        provider = model.split("/")[0] if "/" in model else ""

        try:
            if "codex" in model.lower():
                creds = await self.credential_manager.get_credentials("openai_codex")
                data["api_key"] = creds["api_key"]
                if "api_base" in creds:
                    data["api_base"] = creds["api_base"]
                data.setdefault("metadata", {})["auth_type"] = "codex_oauth"

            elif provider in ("vertex_ai", "gemini"):
                creds = await self.credential_manager.get_credentials("google_vertex")
                if creds.get("vertex_credentials"):
                    data["vertex_credentials"] = creds["vertex_credentials"]

            elif provider == "ollama":
                pass  # No auth needed

            elif provider:
                creds = await self.credential_manager.get_credentials(provider)
                if creds.get("api_key"):
                    data["api_key"] = creds["api_key"]
                if creds.get("api_base"):
                    data["api_base"] = creds["api_base"]

        except Exception as e:
            logger.warning(
                f"Credential injection failed ({provider}): {e}. "
                "LiteLLM will use config defaults or fallback."
            )

        data.setdefault("metadata", {})["gateway_version"] = "ccprism-0.1.0"

        if self.stats_collector:
            rule = data.get("metadata", {}).get("routing_rule", "unknown")
            self.stats_collector.record_request(rule, provider or "unknown")

        return data

    async def async_log_success_event(
        self,
        kwargs: dict,
        response_obj: Any,
        start_time: Any,
        end_time: Any,
    ) -> None:
        """Log successful API calls."""
        rule = kwargs.get("metadata", {}).get("routing_rule", "unknown")
        model = kwargs.get("model", "unknown")
        duration = (end_time - start_time).total_seconds() if start_time and end_time else 0
        logger.info(f"[SUCCESS] rule={rule} model={model} latency={duration:.2f}s")
        if self.stats_collector:
            self.stats_collector.record_success()
        if self.cost_tracker:
            try:
                await self.cost_tracker.record_from_response(
                    rule_name=rule,
                    model=model,
                    response_obj=response_obj,
                    kwargs=kwargs,
                )
            except Exception as e:
                logger.debug("Cost tracking failed: %s", e)

    async def async_log_failure_event(
        self,
        kwargs: dict,
        response_obj: Any,
        start_time: Any,
        end_time: Any,
    ) -> None:
        """Log failed API calls with provider-specific warnings."""
        model = kwargs.get("model", "unknown")
        rule = kwargs.get("metadata", {}).get("routing_rule", "unknown")
        status_code = getattr(response_obj, "status_code", None)
        duration = (end_time - start_time).total_seconds() if start_time and end_time else 0

        if "codex" in model.lower() and status_code in (401, 403):
            logger.error(
                f"[CODEX AUTH FAIL] rule={rule} model={model} status={status_code} "
                f"latency={duration:.2f}s. "
                "Codex OAuth token may be expired or blocked. "
                "Run 'codex --full-auto' to re-authenticate. "
                "Falling back to API Key providers."
            )
        else:
            logger.warning(
                f"[FAILURE] rule={rule} model={model} status={status_code} "
                f"latency={duration:.2f}s"
            )
        if self.stats_collector:
            self.stats_collector.record_failure()

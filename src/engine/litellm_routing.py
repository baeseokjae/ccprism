"""Custom LiteLLM routing strategy based on MD rules.

Role: Rule evaluation + deployment selection ONLY.
Credential injection is handled by hooks.py (async_pre_call_hook).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .rule_engine import RuleEngine

logger = logging.getLogger("ccprism.routing")


class MDRuleBasedRouting:
    """MD rule-based custom routing strategy for LiteLLM Router.

    Evaluates routing rules from MD files and selects the appropriate
    deployment from LiteLLM's model list. Does NOT inject credentials.
    """

    def __init__(self, rule_engine: RuleEngine) -> None:
        self.rule_engine = rule_engine
        self.router_instance: Any = None

    async def async_get_available_deployment(
        self,
        model: str,
        messages: list | None = None,
        input: str | None = None,  # noqa: A002
        specific_deployment: bool = False,
        request_kwargs: dict | None = None,
    ) -> dict | None:
        """Select a deployment based on MD routing rules.

        Called by LiteLLM Router internally. Returns a deployment dict
        or None to fall back to LiteLLM's default routing.
        """
        # Build request context for rule evaluation
        request = {
            "model": model,
            "messages": messages or [],
            "tools": (request_kwargs or {}).get("tools", []),
            "thinking": (request_kwargs or {}).get("thinking", {}),
        }

        # Evaluate MD rules
        decision = self.rule_engine.evaluate(request)
        target_model = f"{decision.primary['provider']}/{decision.primary['model']}"

        logger.info(f"[ROUTING] rule={decision.matched_by} -> {target_model}")

        # Store routing metadata
        if request_kwargs is not None:
            metadata = request_kwargs.setdefault("metadata", {})
            metadata["routing_rule"] = decision.matched_by

        # Search for target deployment
        deployment = self._find_deployment(target_model)
        if deployment:
            return deployment

        # Try fallback chain
        for fallback in decision.fallbacks:
            fallback_model = f"{fallback['provider']}/{fallback['model']}"
            deployment = self._find_deployment(fallback_model)
            if deployment:
                logger.info(f"[FALLBACK] {target_model} -> {fallback_model}")
                return deployment

        # No deployment found - let LiteLLM handle it
        logger.warning(
            f"[ROUTING] No deployment found for {target_model}, "
            "delegating to LiteLLM default routing"
        )
        return None

    def _find_deployment(self, target_model: str) -> dict | None:
        """Find a deployment by model name, preferring healthy ones."""
        if not self.router_instance:
            return None

        # Check healthy deployments first
        healthy = getattr(self, "healthy_deployments", None) or []
        for deployment in healthy:
            if deployment.get("litellm_params", {}).get("model") == target_model:
                return deployment

        # Fall back to all deployments
        all_deployments = getattr(self.router_instance, "model_list", [])
        for deployment in all_deployments:
            if deployment.get("litellm_params", {}).get("model") == target_model:
                return deployment

        # Also try matching by model_name
        for deployment in all_deployments:
            if deployment.get("model_name") == target_model:
                return deployment

        return None

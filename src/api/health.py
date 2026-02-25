"""Health check endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health_check(request: Request) -> dict:
    """Health check endpoint."""
    rule_engine = getattr(request.app.state, "rule_engine", None)
    litellm_router = getattr(request.app.state, "litellm_router", None)

    rules_count = len(rule_engine.rules) if rule_engine else 0
    has_models = litellm_router and hasattr(litellm_router, "model_list")
    models_count = len(litellm_router.model_list) if has_models else 0

    return {
        "status": "healthy",
        "version": "0.1.0",
        "rules_loaded": rules_count,
        "models_configured": models_count,
        "litellm_router": "active" if litellm_router else "inactive",
    }

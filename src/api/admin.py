"""Admin API endpoints for ccprism gateway management."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ..auth.gateway_auth import require_gateway_admin

logger = logging.getLogger("ccprism.api.admin")

router = APIRouter(dependencies=[Depends(require_gateway_admin)], prefix="/admin", tags=["admin"])


@router.get("/rules")
async def list_rules(request: Request) -> dict[str, Any]:
    """List all loaded routing rules, sorted by priority."""
    rule_engine = getattr(request.app.state, "rule_engine", None)
    if not rule_engine:
        raise HTTPException(status_code=503, detail="Rule engine not initialized")

    rules = []
    for rule in rule_engine.rules:
        rules.append({
            "name": rule.name,
            "enabled": rule.enabled,
            "priority": rule.priority,
            "match_type": rule.match_type,
            "route_primary": rule.route_primary,
            "fallbacks_count": len(rule.route_fallbacks),
            "tags": rule.tags,
            "source_file": rule.source_file,
        })

    return {"rules": rules, "total": len(rules)}


@router.get("/rules/{name}")
async def get_rule(request: Request, name: str) -> dict[str, Any]:
    """Get detailed information about a single rule."""
    rule_engine = getattr(request.app.state, "rule_engine", None)
    if not rule_engine:
        raise HTTPException(status_code=503, detail="Rule engine not initialized")

    for rule in rule_engine.rules:
        if rule.name == name:
            return {
                "name": rule.name,
                "enabled": rule.enabled,
                "priority": rule.priority,
                "match_type": rule.match_type,
                "match_params": rule.match_params,
                "route_primary": rule.route_primary,
                "route_fallbacks": rule.route_fallbacks,
                "tags": rule.tags,
                "documentation": rule.documentation,
                "source_file": rule.source_file,
            }

    raise HTTPException(status_code=404, detail=f"Rule '{name}' not found")


@router.post("/rules/reload")
async def reload_rules(request: Request) -> dict[str, Any]:
    """Force reload all routing rules from disk."""
    rule_engine = getattr(request.app.state, "rule_engine", None)
    if not rule_engine:
        raise HTTPException(status_code=503, detail="Rule engine not initialized")

    previous_count = len(rule_engine.rules)
    rule_engine._load_all_rules()
    current_count = len(rule_engine.rules)

    logger.info("Rules reloaded: %d -> %d", previous_count, current_count)

    return {
        "status": "reloaded",
        "previous_count": previous_count,
        "current_count": current_count,
        "rules": [r.name for r in rule_engine.rules],
    }


@router.get("/stats")
async def get_stats(request: Request) -> dict[str, Any]:
    """Get basic request statistics."""
    stats_collector = getattr(request.app.state, "stats_collector", None)
    if not stats_collector:
        return {"stats": {}, "message": "Stats collector not initialized"}

    return {"stats": stats_collector.snapshot()}


@router.get("/costs/daily")
async def get_costs_daily(request: Request, days: int = 7) -> dict[str, Any]:
    """Get daily cost summary."""
    cost_db = getattr(request.app.state, "cost_db", None)
    if not cost_db:
        return {"daily": [], "message": "Cost tracking not initialized"}
    data = await cost_db.get_daily_summary(days=days)
    return {"daily": data, "days": days}


@router.get("/costs/by-provider")
async def get_costs_by_provider(request: Request, days: int = 30) -> dict[str, Any]:
    """Get cost summary grouped by provider."""
    cost_db = getattr(request.app.state, "cost_db", None)
    if not cost_db:
        return {"providers": [], "message": "Cost tracking not initialized"}
    data = await cost_db.get_provider_summary(days=days)
    return {"providers": data, "days": days}


@router.get("/costs/by-rule")
async def get_costs_by_rule(request: Request, days: int = 30) -> dict[str, Any]:
    """Get cost summary grouped by rule."""
    cost_db = getattr(request.app.state, "cost_db", None)
    if not cost_db:
        return {"rules": [], "message": "Cost tracking not initialized"}
    data = await cost_db.get_rule_summary(days=days)
    return {"rules": data, "days": days}


@router.get("/costs/summary")
async def get_costs_summary(request: Request) -> dict[str, Any]:
    """Get current month cost summary with budget status."""
    cost_db = getattr(request.app.state, "cost_db", None)
    budget_alert = getattr(request.app.state, "budget_alert", None)

    if not cost_db:
        return {"message": "Cost tracking not initialized"}

    monthly_total = await cost_db.get_monthly_total()
    result: dict[str, Any] = {"monthly_total_usd": monthly_total}

    if budget_alert:
        result["budget"] = await budget_alert.check()

    return result


@router.get("/providers")
async def get_providers(request: Request) -> dict[str, Any]:
    """Get provider status and credential health."""
    credential_manager = getattr(request.app.state, "credential_manager", None)
    if not credential_manager:
        raise HTTPException(status_code=503, detail="Credential manager not initialized")

    providers: dict[str, dict] = {}
    for provider_name, adapter in credential_manager._adapters.items():
        try:
            creds = await adapter.get_credentials()
            providers[provider_name] = {
                "status": "ok",
                "has_credentials": bool(creds),
                "adapter_type": type(adapter).__name__,
            }
        except Exception as e:
            providers[provider_name] = {
                "status": "error",
                "error": str(e),
                "adapter_type": type(adapter).__name__,
            }

    return {"providers": providers, "total": len(providers)}

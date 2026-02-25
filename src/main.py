"""ccprism AI Gateway - FastAPI application entry point."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import get_settings, load_litellm_config

logger = logging.getLogger("ccprism")


def setup_logging() -> None:
    """Configure logging based on gateway settings."""
    settings = get_settings()
    level = getattr(logging, settings.logging.level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        stream=sys.stderr,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI lifespan context manager for startup/shutdown."""
    setup_logging()

    # Run security checks early, before any credential loading
    from .security.startup_checks import run_startup_security_checks

    run_startup_security_checks()

    settings = get_settings()
    logger.info("Starting ccprism AI Gateway...")

    # Initialize Rule Engine
    from .engine.rule_engine import RuleEngine

    rule_engine = RuleEngine(settings.rules_dir)
    app.state.rule_engine = rule_engine
    logger.info(f"Loaded {len(rule_engine.rules)} routing rules")

    # Initialize Credential Manager
    from .auth.credential_manager import CredentialManager

    credential_manager = CredentialManager()
    app.state.credential_manager = credential_manager

    # Initialize Stats Collector
    from .engine.stats_collector import StatsCollector

    stats_collector = StatsCollector()
    app.state.stats_collector = stats_collector

    # Initialize Cost DB + Tracker + Budget Alert
    from .engine.budget_alert import BudgetAlert
    from .engine.cost_tracker import CostTracker
    from .storage.cost_db import CostDB

    cost_db = CostDB(db_path=settings.budget.cost_db_path)
    await cost_db.open()
    app.state.cost_db = cost_db

    cost_tracker = CostTracker(cost_db=cost_db)
    app.state.cost_tracker = cost_tracker

    budget_alert = BudgetAlert(
        cost_db=cost_db,
        monthly_budget_usd=settings.budget.monthly_usd,
    )
    app.state.budget_alert = budget_alert

    # Initialize Alert Handler
    from .monitoring.alert_handler import setup_alert_handler

    alert_handler = setup_alert_handler(settings.monitoring.slack_webhook_url or None)

    # Initialize LiteLLM Router
    litellm_config = load_litellm_config(settings.litellm_config_path)
    router = _create_litellm_router(
        litellm_config, rule_engine, credential_manager, stats_collector, cost_tracker
    )
    app.state.litellm_router = router

    # Start file watcher for hot-reload
    from .engine.file_watcher import watch_rules_directory

    watcher_task = asyncio.create_task(
        watch_rules_directory(rule_engine, settings.rules_dir)
    )
    logger.info("File watcher started for hot-reload")

    yield

    # Shutdown
    logger.info("Shutting down ccprism AI Gateway...")
    watcher_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await watcher_task
    await credential_manager.close_all()
    cost_db = getattr(app.state, "cost_db", None)
    if cost_db:
        await cost_db.close()
    if alert_handler is not None:
        logging.getLogger("ccprism").removeHandler(alert_handler)
        alert_handler.close()
    logger.info("Shutdown complete")


def _create_litellm_router(
    litellm_config: dict,
    rule_engine: object,
    credential_manager: object,
    stats_collector: object | None = None,
    cost_tracker: object | None = None,
) -> object:
    """Create and configure LiteLLM Router with custom routing and hooks."""
    try:
        import litellm
        from litellm import Router

        from .engine.hooks import GatewayHooks
        from .engine.litellm_routing import MDRuleBasedRouting

        # Create custom routing strategy
        routing_strategy = MDRuleBasedRouting(rule_engine)  # type: ignore[arg-type]

        # Create hooks
        hooks = GatewayHooks(credential_manager, stats_collector=stats_collector, cost_tracker=cost_tracker)  # type: ignore[arg-type]

        # Configure LiteLLM
        litellm.callbacks = [hooks]

        model_list = litellm_config.get("model_list", [])
        router_settings = litellm_config.get("router_settings", {})
        litellm_settings = litellm_config.get("litellm_settings", {})

        # Create Router
        router = Router(
            model_list=model_list,
            routing_strategy="custom-routing-strategy-base",
            custom_routing_strategy=routing_strategy,
            num_retries=router_settings.get("num_retries", 2),
            cooldown_time=router_settings.get("cooldown_time", 30),
            retry_policy=router_settings.get("retry_policy"),
            allowed_fails_policy=router_settings.get("allowed_fails_policy"),
            fallbacks=litellm_settings.get("fallbacks", []),
            context_window_fallbacks=litellm_settings.get("context_window_fallbacks", []),
        )

        logger.info(
            f"LiteLLM Router initialized with {len(model_list)} model deployments"
        )
        return router

    except Exception as e:
        logger.error(f"Failed to initialize LiteLLM Router: {e}")
        logger.warning("Running without LiteLLM Router - proxy functionality disabled")
        return None


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(
        title="ccprism",
        description="AI Gateway for Claude Code - Dynamic routing to multiple AI providers",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Include routers
    from .api.health import router as health_router
    from .api.messages import router as messages_router

    app.include_router(health_router)
    app.include_router(messages_router)

    try:
        from .api.auth_routes import router as auth_router

        app.include_router(auth_router)
    except ImportError:
        logger.debug("Auth routes not available")

    try:
        from .api.admin import router as admin_router

        app.include_router(admin_router)
    except ImportError:
        logger.debug("Admin routes not available")

    return app


app = create_app()

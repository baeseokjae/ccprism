"""ccprism CLI tool."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="ccprism",
        description="ccprism AI Gateway - Dynamic routing for Claude Code",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ccprism start
    start_parser = subparsers.add_parser("start", help="Start the gateway server")
    start_parser.add_argument(
        "--host", default=None, help="Host to bind to (default: configured loopback)"
    )
    start_parser.add_argument("--port", type=int, default=None, help="Port to bind to")
    start_parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    start_parser.add_argument("--config", default=None, help="Path to gateway.yaml")

    # ccprism auth
    auth_parser = subparsers.add_parser("auth", help="Authentication management")
    auth_sub = auth_parser.add_subparsers(dest="auth_command")
    auth_sub.add_parser("status", help="Show credential status for all providers")
    auth_login = auth_sub.add_parser("login", help="Interactive login for a provider")
    auth_login.add_argument("provider", help="Provider name (e.g., openai_codex)")
    auth_add = auth_sub.add_parser("add", help="Add API key for a provider")
    auth_add.add_argument("provider", help="Provider name")
    auth_add.add_argument("--key", help="API key value")
    auth_add.add_argument(
        "--store",
        choices=["keychain", "vault", "env"],
        default="env",
        help="Storage backend (default: env)",
    )

    # ccprism rules
    rules_parser = subparsers.add_parser("rules", help="Rule management")
    rules_sub = rules_parser.add_subparsers(dest="rules_command")
    rules_sub.add_parser("list", help="List all loaded rules")
    rules_sub.add_parser("validate", help="Validate all rule files")
    rules_sub.add_parser("reload", help="Force reload rules")

    # ccprism costs
    costs_parser = subparsers.add_parser("costs", help="Cost tracking")
    costs_sub = costs_parser.add_subparsers(dest="costs_command")
    costs_sub.add_parser("summary", help="Show current month cost summary")
    costs_daily = costs_sub.add_parser("daily", help="Show daily cost breakdown")
    costs_daily.add_argument("--days", type=int, default=7, help="Number of days (default: 7)")

    # ccprism status
    subparsers.add_parser("status", help="Show gateway status")

    # ccprism test-route
    test_route = subparsers.add_parser("test-route", help="Dry-run routing for a prompt")
    test_route.add_argument("prompt", help="Test prompt to route")
    test_route.add_argument("--model", default="claude-sonnet-4-6", help="Model name")
    test_route.add_argument("--thinking", action="store_true", help="Enable thinking")
    test_route.add_argument(
        "--tools", nargs="*", default=[], help="Tool names to include"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "start":
        _cmd_start(args)
    elif args.command == "auth":
        asyncio.run(_cmd_auth(args))
    elif args.command == "rules":
        _cmd_rules(args)
    elif args.command == "costs":
        asyncio.run(_cmd_costs(args))
    elif args.command == "status":
        asyncio.run(_cmd_status(args))
    elif args.command == "test-route":
        _cmd_test_route(args)


def _cmd_start(args: argparse.Namespace) -> None:
    """Start the gateway server."""
    import uvicorn

    from ..auth.gateway_auth import validate_auth_settings
    from ..config import get_settings

    if args.config:
        os.environ["CCPRISM_CONFIG"] = str(Path(args.config).resolve())
    get_settings.cache_clear()
    settings = get_settings()
    host = args.host if args.host is not None else settings.server.host
    port = args.port if args.port is not None else settings.server.port
    try:
        validate_auth_settings(settings, host=host)
    except ValueError as exc:
        raise SystemExit(f"Unsafe gateway configuration: {exc}") from exc
    # Preserve overrides in Uvicorn reload workers as well as this process.
    os.environ["CCPRISM_SERVER__HOST"] = host
    os.environ["CCPRISM_SERVER__PORT"] = str(port)
    get_settings.cache_clear()
    print(f"Starting ccprism AI Gateway on {host}:{port}...")
    uvicorn.run(
        "src.main:app",
        host=host,
        port=port,
        reload=args.reload,
        proxy_headers=False,
    )


async def _cmd_auth(args: argparse.Namespace) -> None:
    """Handle auth subcommands."""
    if args.auth_command == "status":
        from ..auth.credential_manager import CredentialManager

        cm = CredentialManager()
        print("Provider Credential Status")
        print("=" * 60)
        for provider, adapter in cm._adapters.items():
            try:
                creds = await adapter.get_credentials()
                has_key = bool(creds.get("api_key") or creds.get("vertex_credentials"))
                status = "OK" if has_key else "No credentials"
            except Exception as e:
                status = f"Error: {e}"
            print(f"  {provider:20s} {status}")
    elif args.auth_command == "add":
        if not args.key:
            print("Use --key to provide the API key")
            return

        env_map = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "xai": "XAI_API_KEY",
            "groq": "GROQ_API_KEY",
            "together": "TOGETHERAI_API_KEY",
        }
        env_var = env_map.get(args.provider, f"{args.provider.upper()}_API_KEY")

        if args.store == "keychain":
            from ..auth.keychain import is_keyring_available, store_credential

            if not is_keyring_available():
                print("Error: OS keychain is not available on this system.")
                print("Use --store vault or --store env instead.")
                return
            if store_credential(env_var, args.key):
                print(f"Stored {args.provider} API key in OS keychain (key: {env_var})")
            else:
                print("Error: Failed to store credential in keychain.")

        elif args.store == "vault":
            from ..auth.vault import CredentialVault

            vault = CredentialVault()
            vault.store(env_var, args.key)
            print(f"Stored {args.provider} API key in encrypted vault (key: {env_var})")
            print(f"Vault location: {vault._path}")

        else:  # env
            print(f"To set via environment variable:")
            print(f"  export {env_var}={args.key}")
            print("Add to your shell profile for persistence.")
    else:
        print("Use: ccprism auth status|login|add")


def _cmd_rules(args: argparse.Namespace) -> None:
    """Handle rules subcommands."""
    from ..config import get_settings
    from ..engine.rule_engine import RuleEngine

    settings = get_settings()
    rules_dir = settings.rules_dir

    if args.rules_command == "list":
        engine = RuleEngine(rules_dir)
        print("Loaded Routing Rules")
        print("=" * 80)
        print(f"{'Priority':>8}  {'Name':<25}  {'Match Type':<15}  {'Provider/Model':<30}")
        print("-" * 80)
        for rule in engine.rules:
            provider = rule.route_primary.get('provider', '?')
            model = rule.route_primary.get('model', '?')
            target = f"{provider}/{model}"
            print(
                f"{rule.priority:>8}  {rule.name:<25}  {rule.match_type:<15}  {target:<30}"
            )
        print(f"\nTotal: {len(engine.rules)} rules loaded")

    elif args.rules_command == "validate":
        engine = RuleEngine(rules_dir)
        md_files = sorted(Path(rules_dir).glob("*.md"))
        errors = 0
        for md_file in md_files:
            rule = engine._parse_rule_file(md_file)
            if rule:
                print(f"  OK  {md_file.name}")
            else:
                print(f"  ERR {md_file.name}")
                errors += 1
        print(f"\nValidation: {len(md_files) - errors}/{len(md_files)} passed")
        if errors:
            sys.exit(1)

    elif args.rules_command == "reload":
        engine = RuleEngine(rules_dir)
        print(f"Reloaded {len(engine.rules)} rules from {rules_dir}")

    else:
        print("Use: ccprism rules list|validate|reload")


async def _cmd_costs(args: argparse.Namespace) -> None:
    """Handle costs subcommands."""
    from ..config import get_settings
    from ..storage.cost_db import CostDB

    settings = get_settings()
    db = CostDB(db_path=settings.budget.cost_db_path)
    await db.open()

    try:
        if args.costs_command == "summary":
            monthly = await db.get_monthly_total()
            providers = await db.get_provider_summary(days=30)
            print("Cost Summary (Current Month)")
            print("=" * 50)
            print(f"  Monthly Total: ${monthly:.4f}")
            if settings.budget.monthly_usd > 0:
                pct = (monthly / settings.budget.monthly_usd) * 100
                print(f"  Budget:        ${settings.budget.monthly_usd:.2f}")
                print(f"  Used:          {pct:.1f}%")
            print()
            if providers:
                print("  By Provider (30 days):")
                for p in providers:
                    print(f"    {p['provider']:<20s}  ${p['total_cost']:.4f}  ({p['requests']} reqs)")

        elif args.costs_command == "daily":
            days = args.days
            rows = await db.get_daily_summary(days=days)
            print(f"Daily Costs (last {days} days)")
            print("=" * 60)
            print(f"  {'Date':<12}  {'Requests':>8}  {'In Tokens':>10}  {'Out Tokens':>10}  {'Cost':>10}")
            print("-" * 60)
            total = 0.0
            for r in rows:
                total += r["total_cost"]
                print(
                    f"  {r['day']:<12}  {r['requests']:>8}  {r['input_tokens']:>10}  "
                    f"{r['output_tokens']:>10}  ${r['total_cost']:>9.4f}"
                )
            print("-" * 60)
            print(f"  {'Total':<12}  {'':>8}  {'':>10}  {'':>10}  ${total:>9.4f}")
        else:
            print("Use: ccprism costs summary|daily")
    finally:
        await db.close()


async def _cmd_status(args: argparse.Namespace) -> None:
    """Show gateway status."""
    import httpx

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:8080/health", timeout=5.0)
            data = resp.json()
            print("ccprism Gateway Status")
            print("=" * 40)
            for key, value in data.items():
                print(f"  {key}: {value}")
    except Exception:
        print("Gateway is not running or not reachable at localhost:8080")


def _cmd_test_route(args: argparse.Namespace) -> None:
    """Dry-run routing for a test prompt."""
    from ..config import get_settings
    from ..engine.rule_engine import RuleEngine

    settings = get_settings()
    engine = RuleEngine(settings.rules_dir)

    # Build test request
    request = {
        "model": args.model,
        "messages": [{"role": "user", "content": args.prompt}],
        "tools": [{"name": t} for t in args.tools],
        "thinking": {"enabled": True} if args.thinking else {},
    }

    # Evaluate
    decision = engine.evaluate(request)

    # Estimate token count
    try:
        from litellm import token_counter

        tokens = token_counter(model="gpt-4", messages=request["messages"])
    except Exception:
        tokens = len(args.prompt) // 4

    # Display results
    print("Routing Test Result")
    print("=" * 60)
    print(f"  Prompt:    {args.prompt[:80]}{'...' if len(args.prompt) > 80 else ''}")
    print(f"  Model:     {args.model}")
    print(f"  Tokens:    ~{tokens}")
    print(f"  Thinking:  {args.thinking}")
    print(f"  Tools:     {args.tools or 'none'}")
    print()
    print(f"  Matched Rule:  {decision.matched_by}")
    if decision.rule:
        print(f"  Match Type:    {decision.rule.match_type}")
        print(f"  Priority:      {decision.rule.priority}")
        print(f"  Source File:   {decision.rule.source_file}")
    print()
    p_provider = decision.primary.get('provider', '?')
    p_model = decision.primary.get('model', '?')
    print(f"  Primary:   {p_provider}/{p_model}")
    if decision.fallbacks:
        print("  Fallbacks:")
        for i, fb in enumerate(decision.fallbacks, 1):
            print(f"    {i}. {fb.get('provider', '?')}/{fb.get('model', '?')}")


if __name__ == "__main__":
    main()

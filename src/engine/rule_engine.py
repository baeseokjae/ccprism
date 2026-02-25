"""Core rule engine for request routing."""

import logging
from dataclasses import dataclass, field
from pathlib import Path

from .matchers import MATCHER_REGISTRY
from .md_parser import parse_rule_file

logger = logging.getLogger(__name__)


@dataclass
class RoutingRule:
    """A loaded routing rule ready for evaluation."""

    name: str
    enabled: bool
    priority: int
    match_type: str
    match_params: dict
    route_primary: dict
    route_fallbacks: list
    tags: list[str] = field(default_factory=list)
    documentation: str = ""
    source_file: str = ""


@dataclass
class RoutingDecision:
    """Result of evaluating a request against all rules."""

    rule: RoutingRule | None
    primary: dict
    fallbacks: list
    matched_by: str

    @classmethod
    def default(cls) -> "RoutingDecision":
        return cls(
            rule=None,
            primary={"provider": "anthropic", "model": "claude-sonnet-4-6"},
            fallbacks=[],
            matched_by="default",
        )


class RuleEngine:
    """Loads rules from Markdown files and evaluates requests."""

    def __init__(self, rules_dir: str | Path) -> None:
        self.rules_dir = Path(rules_dir)
        self.rules: list[RoutingRule] = []
        self._load_all_rules()

    def _load_all_rules(self) -> None:
        """Load all .md rule files from the rules directory, sorted by priority."""
        rules: list[RoutingRule] = []

        if not self.rules_dir.exists():
            logger.warning("Rules directory does not exist: %s", self.rules_dir)
            self.rules = []
            return

        for path in sorted(self.rules_dir.glob("*.md")):
            rule = self._parse_rule_file(path)
            if rule is not None:
                rules.append(rule)

        rules.sort(key=lambda r: r.priority)
        self.rules = rules
        logger.info("Loaded %d rules from %s", len(self.rules), self.rules_dir)

    def _parse_rule_file(self, path: Path) -> RoutingRule | None:
        """Parse a single rule file into a RoutingRule."""
        result = parse_rule_file(path)
        if not result.ok:
            logger.error("Failed to parse rule file %s: %s", path.name, result.error)
            return None

        schema = result.schema
        assert schema is not None

        match_params = schema.match.model_dump(exclude={"type"})

        return RoutingRule(
            name=schema.name,
            enabled=schema.enabled,
            priority=schema.priority,
            match_type=schema.match.type,
            match_params=match_params,
            route_primary=schema.route.primary.model_dump(),
            route_fallbacks=[fb.model_dump() for fb in schema.route.fallback],
            tags=schema.tags,
            documentation=result.body,
            source_file=str(path),
        )

    def evaluate(self, request: dict) -> RoutingDecision:
        """Evaluate a request against all rules and return a routing decision.

        Rules are checked in priority order (ascending). The first matching
        enabled rule wins. If no rule matches, returns the default decision.
        """
        for rule in self.rules:
            if not rule.enabled:
                logger.debug("Skipping disabled rule: %s", rule.name)
                continue

            matcher = MATCHER_REGISTRY.get(rule.match_type)
            if matcher is None:
                logger.warning("Unknown matcher type '%s' in rule '%s'", rule.match_type, rule.name)
                continue

            if matcher(request, rule.match_params):
                logger.info("Request matched rule '%s' (priority=%d)", rule.name, rule.priority)
                return RoutingDecision(
                    rule=rule,
                    primary=rule.route_primary,
                    fallbacks=rule.route_fallbacks,
                    matched_by=rule.name,
                )

        logger.info("No rule matched, using default routing")
        return RoutingDecision.default()

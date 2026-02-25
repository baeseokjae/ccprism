"""Hot-reload watcher for rule files."""

import logging
from pathlib import Path

from watchfiles import awatch

logger = logging.getLogger(__name__)


async def watch_rules_directory(rule_engine: "RuleEngine", rules_dir: str | Path) -> None:  # noqa: F821
    """Watch the rules directory for .md file changes and reload rules.

    Uses watchfiles.awatch for async file system monitoring.
    Runs indefinitely until cancelled.
    """
    rules_path = Path(rules_dir)
    logger.info("Watching rules directory for changes: %s", rules_path)

    async for changes in awatch(rules_path):
        md_changes = [
            (change_type, path)
            for change_type, path in changes
            if path.endswith(".md")
        ]

        if md_changes:
            for change_type, path in md_changes:
                logger.info("Rule file %s: %s", change_type.name, Path(path).name)

            logger.info("Reloading all rules...")
            rule_engine._load_all_rules()
            logger.info("Rules reloaded: %d active rules", len(rule_engine.rules))

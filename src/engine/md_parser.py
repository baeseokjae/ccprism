"""Parse Markdown files with YAML frontmatter into rule configurations."""

import logging
from pathlib import Path

import yaml
from pydantic import ValidationError

from .rule_schema import RuleSchema

logger = logging.getLogger(__name__)


class ParseResult:
    """Result of parsing a Markdown rule file."""

    def __init__(
        self,
        frontmatter: dict | None = None,
        body: str = "",
        schema: RuleSchema | None = None,
        error: str | None = None,
    ) -> None:
        self.frontmatter = frontmatter
        self.body = body
        self.schema = schema
        self.error = error

    @property
    def ok(self) -> bool:
        return self.schema is not None


def parse_rule_file(path: Path) -> ParseResult:
    """Parse a Markdown file with YAML frontmatter.

    Expected format:
        ---
        <yaml frontmatter>
        ---
        <markdown body>

    Returns a ParseResult with parsed schema or error details.
    """
    filename = path.name
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as e:
        return ParseResult(error=f"{filename}:0 - cannot read file: {e}")

    stripped = content.strip()
    if not stripped.startswith("---"):
        return ParseResult(error=f"{filename}:1 - missing frontmatter delimiter '---'")

    # Check for content before the opening ---
    first_line = content.split("\n", 1)[0]
    if first_line.strip() != "---":
        logger.warning("%s:1 - unexpected content before frontmatter delimiter", filename)

    parts = stripped.split("---", 2)
    # parts[0] is empty (before first ---), parts[1] is yaml, parts[2] is rest
    if len(parts) < 3:
        return ParseResult(error=f"{filename}:1 - missing closing frontmatter delimiter '---'")

    yaml_text = parts[1]
    body = parts[2].strip()

    # Parse YAML
    try:
        frontmatter = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        line = getattr(e, "problem_mark", None)
        line_num = line.line + 1 if line else 0
        return ParseResult(error=f"{filename}:{line_num} - invalid YAML: {e}")

    if not isinstance(frontmatter, dict):
        return ParseResult(error=f"{filename}:1 - frontmatter must be a YAML mapping")

    # Validate with Pydantic
    try:
        schema = RuleSchema(**frontmatter)
    except ValidationError as e:
        first_error = e.errors()[0]
        loc = ".".join(str(part) for part in first_error["loc"])
        msg = first_error["msg"]
        return ParseResult(
            frontmatter=frontmatter,
            body=body,
            error=f"{filename}:0 - validation error at '{loc}': {msg}",
        )

    return ParseResult(frontmatter=frontmatter, body=body, schema=schema)

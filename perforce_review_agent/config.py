"""Configuration handling for the Perforce Review Agent."""

import os
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class P4Config:
    """Perforce connection configuration."""

    port: str = field(default_factory=lambda: os.environ.get("P4PORT", "perforce:1666"))
    user: str = field(default_factory=lambda: os.environ.get("P4USER", ""))
    client: str = field(default_factory=lambda: os.environ.get("P4CLIENT", ""))
    password: str = field(default_factory=lambda: os.environ.get("P4PASSWD", ""))
    charset: str = field(default_factory=lambda: os.environ.get("P4CHARSET", "utf8"))


@dataclass
class ReviewConfig:
    """Code review configuration."""

    # Maximum number of lines in a single file diff to review
    max_diff_lines: int = field(
        default_factory=lambda: int(os.environ.get("REVIEW_MAX_DIFF_LINES", "5000"))
    )
    # File extensions to review (empty means all)
    include_extensions: List[str] = field(
        default_factory=lambda: _parse_list(os.environ.get("REVIEW_INCLUDE_EXTENSIONS", ""))
    )
    # File extensions to skip
    exclude_extensions: List[str] = field(
        default_factory=lambda: _parse_list(
            os.environ.get("REVIEW_EXCLUDE_EXTENSIONS", ".png,.jpg,.jpeg,.gif,.ico,.pdf,.zip,.tar,.gz")
        )
    )
    # Paths to exclude from review (glob patterns)
    exclude_paths: List[str] = field(
        default_factory=lambda: _parse_list(os.environ.get("REVIEW_EXCLUDE_PATHS", ""))
    )
    # Whether to fail on findings
    fail_on_findings: bool = field(
        default_factory=lambda: os.environ.get("REVIEW_FAIL_ON_FINDINGS", "false").lower() == "true"
    )
    # Output format: "text", "json", or "markdown"
    output_format: str = field(
        default_factory=lambda: os.environ.get("REVIEW_OUTPUT_FORMAT", "text")
    )


@dataclass
class AgentConfig:
    """Combined agent configuration."""

    p4: P4Config = field(default_factory=P4Config)
    review: ReviewConfig = field(default_factory=ReviewConfig)
    # Changelist number to review. "default" means the default changelist.
    changelist: Optional[str] = field(
        default_factory=lambda: os.environ.get("P4_CHANGELIST", None)
    )
    # Verbose output
    verbose: bool = field(
        default_factory=lambda: os.environ.get("AGENT_VERBOSE", "false").lower() == "true"
    )


def _parse_list(value: str) -> List[str]:
    """Parse a comma-separated list, stripping whitespace and empty entries."""
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def load_config() -> AgentConfig:
    """Load configuration from environment variables."""
    return AgentConfig()

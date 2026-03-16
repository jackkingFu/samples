"""Main entry point for the Perforce Review Agent."""

import argparse
import logging
import sys
from typing import Optional

from .config import AgentConfig, load_config
from .formatter import format_json, format_markdown, format_text
from .p4_client import P4Client, P4ClientError
from .reviewer import ReviewResult, Reviewer


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )


def run(config: Optional[AgentConfig] = None) -> ReviewResult:
    """Execute the review agent with the given (or auto-loaded) config.

    Returns the :class:`ReviewResult` so callers can inspect findings.
    """
    if config is None:
        config = load_config()

    _setup_logging(config.verbose)
    logger = logging.getLogger(__name__)

    logger.info("Connecting to Perforce at %s as %s", config.p4.port, config.p4.user)

    client = P4Client(config.p4)

    try:
        client.login()
    except P4ClientError as exc:
        logger.error("Login failed: %s", exc)
        sys.exit(1)

    if not client.check_connection():
        logger.error("Cannot connect to Perforce server at %s", config.p4.port)
        sys.exit(1)

    logger.info("Connected. Fetching diffs for changelist: %s", config.changelist or "default")

    try:
        file_diffs = client.get_file_diffs(config.changelist)
    except P4ClientError as exc:
        logger.error("Failed to retrieve diffs: %s", exc)
        sys.exit(1)

    if not file_diffs:
        logger.info("No file diffs found for changelist %s.", config.changelist or "default")
        result = ReviewResult()
    else:
        logger.info("Reviewing %d file(s)…", len(file_diffs))
        reviewer = Reviewer(config.review)
        result = reviewer.review(file_diffs)

    _write_output(result, config.review.output_format)

    if config.review.fail_on_findings and result.has_errors:
        logger.error("Exiting with failure due to error-level findings.")
        sys.exit(2)

    return result


def _write_output(result: ReviewResult, output_format: str) -> None:
    fmt = output_format.lower()
    if fmt == "json":
        format_json(result, sys.stdout)
    elif fmt in ("markdown", "md"):
        format_markdown(result, sys.stdout)
    else:
        format_text(result, sys.stdout)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="perforce-review-agent",
        description="Review code changes against a Perforce client.",
    )
    parser.add_argument(
        "-c",
        "--changelist",
        metavar="CL",
        help="Changelist number to review (default: opened/default changelist)",
    )
    parser.add_argument(
        "--p4port",
        metavar="PORT",
        help="Perforce server address (overrides P4PORT env var)",
    )
    parser.add_argument(
        "--p4user",
        metavar="USER",
        help="Perforce user (overrides P4USER env var)",
    )
    parser.add_argument(
        "--p4client",
        metavar="CLIENT",
        help="Perforce client workspace (overrides P4CLIENT env var)",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json", "markdown"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="Exit with code 2 if error-level findings are found",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose debug output",
    )
    args = parser.parse_args()

    config = load_config()
    if args.changelist:
        config.changelist = args.changelist
    if args.p4port:
        config.p4.port = args.p4port
    if args.p4user:
        config.p4.user = args.p4user
    if args.p4client:
        config.p4.client = args.p4client
    if args.format:
        config.review.output_format = args.format
    if args.fail_on_findings:
        config.review.fail_on_findings = True
    if args.verbose:
        config.verbose = True

    run(config)


if __name__ == "__main__":
    main()

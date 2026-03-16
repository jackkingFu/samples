"""Code review rules applied to Perforce diffs."""

import fnmatch
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from .config import ReviewConfig
from .p4_client import P4FileDiff

logger = logging.getLogger(__name__)


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Finding:
    """A single review finding on a file."""

    depot_path: str
    severity: Severity
    rule: str
    message: str
    line_number: Optional[int] = None
    line_content: Optional[str] = None


@dataclass
class ReviewResult:
    """The aggregated result of reviewing a set of file diffs."""

    findings: List[Finding] = field(default_factory=list)
    skipped_files: List[str] = field(default_factory=list)
    reviewed_files: List[str] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(f.severity == Severity.ERROR for f in self.findings)

    @property
    def has_warnings(self) -> bool:
        return any(f.severity == Severity.WARNING for f in self.findings)


# ---------------------------------------------------------------------------
# Individual review rules
# ---------------------------------------------------------------------------

class _Rule:
    """Base class for a review rule."""

    name: str = "base"

    def check(self, file_diff: P4FileDiff) -> List[Finding]:
        raise NotImplementedError


class _HardcodedSecretRule(_Rule):
    """Flag potential hard-coded secrets (passwords, tokens, keys)."""

    name = "hardcoded-secret"

    # Patterns that look like assignments of secret values
    _PATTERNS = [
        re.compile(
            r'(?i)(password|passwd|secret|api[_-]?key|auth[_-]?token|access[_-]?token'
            r'|private[_-]?key|client[_-]?secret)\s*=\s*["\'][^"\']{6,}["\']'
        ),
        re.compile(
            r'(?i)(password|passwd|secret|api[_-]?key|auth[_-]?token|access[_-]?token'
            r'|private[_-]?key|client[_-]?secret)\s*:\s*["\'][^"\']{6,}["\']'
        ),
    ]

    def check(self, file_diff: P4FileDiff) -> List[Finding]:
        if file_diff.is_binary or file_diff.action == "delete":
            return []
        findings = []
        for lineno, line in _added_lines(file_diff.diff):
            for pattern in self._PATTERNS:
                if pattern.search(line):
                    findings.append(
                        Finding(
                            depot_path=file_diff.depot_path,
                            severity=Severity.ERROR,
                            rule=self.name,
                            message="Possible hard-coded secret detected.",
                            line_number=lineno,
                            line_content=line.rstrip(),
                        )
                    )
                    break
        return findings


class _DebugCodeRule(_Rule):
    """Flag debug/trace statements that were added."""

    name = "debug-code"

    _PATTERNS = [
        re.compile(r'\bpdb\.set_trace\(\)'),
        re.compile(r'\bdebugger\b'),
        re.compile(r'\bconsole\.log\b'),
        re.compile(r'\bSystem\.out\.print'),
        re.compile(r'\bprint\s*\(.*\bDEBUG\b', re.IGNORECASE),
        re.compile(r'\bTODO\b|\bFIXME\b|\bHACK\b|\bXXX\b'),
    ]

    def check(self, file_diff: P4FileDiff) -> List[Finding]:
        if file_diff.is_binary or file_diff.action == "delete":
            return []
        findings = []
        for lineno, line in _added_lines(file_diff.diff):
            for pattern in self._PATTERNS:
                if pattern.search(line):
                    findings.append(
                        Finding(
                            depot_path=file_diff.depot_path,
                            severity=Severity.WARNING,
                            rule=self.name,
                            message=f"Debug / temporary code detected: {line.strip()!r}",
                            line_number=lineno,
                            line_content=line.rstrip(),
                        )
                    )
                    break
        return findings


class _LongLineRule(_Rule):
    """Warn about extremely long lines added in the diff."""

    name = "long-line"
    _MAX_LENGTH = 300

    def check(self, file_diff: P4FileDiff) -> List[Finding]:
        if file_diff.is_binary or file_diff.action == "delete":
            return []
        findings = []
        for lineno, line in _added_lines(file_diff.diff):
            if len(line.rstrip("\n")) > self._MAX_LENGTH:
                findings.append(
                    Finding(
                        depot_path=file_diff.depot_path,
                        severity=Severity.INFO,
                        rule=self.name,
                        message=(
                            f"Line exceeds {self._MAX_LENGTH} characters "
                            f"({len(line.rstrip())} chars)."
                        ),
                        line_number=lineno,
                        line_content=line.rstrip()[:120] + "...",
                    )
                )
        return findings


class _LargeFileDiffRule(_Rule):
    """Warn when a single file diff is very large."""

    name = "large-diff"
    _THRESHOLD = 1000  # added/removed lines

    def check(self, file_diff: P4FileDiff) -> List[Finding]:
        if file_diff.is_binary:
            return []
        added = sum(1 for _, _ in _added_lines(file_diff.diff))
        removed = sum(1 for _, _ in _removed_lines(file_diff.diff))
        total = added + removed
        if total > self._THRESHOLD:
            return [
                Finding(
                    depot_path=file_diff.depot_path,
                    severity=Severity.WARNING,
                    rule=self.name,
                    message=(
                        f"Large diff: {added} lines added, {removed} lines removed "
                        f"(total {total}). Consider splitting into smaller changes."
                    ),
                )
            ]
        return []


class _BinaryFileRule(_Rule):
    """Note binary files added or modified in the changelist."""

    name = "binary-file"

    def check(self, file_diff: P4FileDiff) -> List[Finding]:
        if file_diff.is_binary and file_diff.action in ("add", "edit", "branch"):
            return [
                Finding(
                    depot_path=file_diff.depot_path,
                    severity=Severity.INFO,
                    rule=self.name,
                    message="Binary file changed. Ensure this is intentional.",
                )
            ]
        return []


class _DeletedFileRule(_Rule):
    """Note file deletions."""

    name = "file-deletion"

    def check(self, file_diff: P4FileDiff) -> List[Finding]:
        if file_diff.action == "delete":
            return [
                Finding(
                    depot_path=file_diff.depot_path,
                    severity=Severity.INFO,
                    rule=self.name,
                    message="File is being deleted. Confirm this is intended.",
                )
            ]
        return []


# ---------------------------------------------------------------------------
# Reviewer
# ---------------------------------------------------------------------------

_ALL_RULES: List[_Rule] = [
    _HardcodedSecretRule(),
    _DebugCodeRule(),
    _LongLineRule(),
    _LargeFileDiffRule(),
    _BinaryFileRule(),
    _DeletedFileRule(),
]


class Reviewer:
    """Applies configured review rules to a list of file diffs."""

    def __init__(self, config: ReviewConfig) -> None:
        self._config = config
        self._rules = _ALL_RULES

    def review(self, file_diffs: List[P4FileDiff]) -> ReviewResult:
        result = ReviewResult()

        for file_diff in file_diffs:
            if self._should_skip(file_diff.depot_path):
                logger.debug("Skipping %s", file_diff.depot_path)
                result.skipped_files.append(file_diff.depot_path)
                continue

            if self._diff_too_large(file_diff.diff):
                logger.warning(
                    "Skipping %s: diff too large (>%d lines)",
                    file_diff.depot_path,
                    self._config.max_diff_lines,
                )
                result.skipped_files.append(file_diff.depot_path)
                continue

            result.reviewed_files.append(file_diff.depot_path)
            for rule in self._rules:
                try:
                    findings = rule.check(file_diff)
                    result.findings.extend(findings)
                except Exception:
                    logger.exception(
                        "Rule %r raised an exception on %s", rule.name, file_diff.depot_path
                    )

        return result

    def _should_skip(self, depot_path: str) -> bool:
        # Check extension exclusions first
        lower = depot_path.lower()
        for ext in self._config.exclude_extensions:
            if lower.endswith(ext.lower()):
                return True

        # If include_extensions is set, only review those
        if self._config.include_extensions:
            if not any(lower.endswith(ext.lower()) for ext in self._config.include_extensions):
                return True

        # Check path exclusion patterns
        for pattern in self._config.exclude_paths:
            if fnmatch.fnmatch(depot_path, pattern):
                return True

        return False

    def _diff_too_large(self, diff: str) -> bool:
        return diff.count("\n") > self._config.max_diff_lines


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _added_lines(diff: str):
    """Yield (line_number, content) for lines added in a unified diff."""
    lineno = 0
    hunk_new_start = 0
    offset = 0

    for raw_line in diff.splitlines(keepends=True):
        hunk_match = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", raw_line)
        if hunk_match:
            hunk_new_start = int(hunk_match.group(1))
            offset = 0
            continue
        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            lineno = hunk_new_start + offset
            yield lineno, raw_line[1:]
            offset += 1
        elif raw_line.startswith(" "):
            offset += 1


def _removed_lines(diff: str):
    """Yield (line_number, content) for lines removed in a unified diff."""
    lineno = 0
    hunk_old_start = 0
    offset = 0

    for raw_line in diff.splitlines(keepends=True):
        hunk_match = re.match(r"^@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@", raw_line)
        if hunk_match:
            hunk_old_start = int(hunk_match.group(1))
            offset = 0
            continue
        if raw_line.startswith("-") and not raw_line.startswith("---"):
            lineno = hunk_old_start + offset
            yield lineno, raw_line[1:]
            offset += 1
        elif raw_line.startswith(" "):
            offset += 1

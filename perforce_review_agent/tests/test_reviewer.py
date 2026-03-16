"""Unit tests for the reviewer module."""

import pytest

from perforce_review_agent.config import ReviewConfig
from perforce_review_agent.p4_client import P4FileDiff
from perforce_review_agent.reviewer import (
    Finding,
    ReviewResult,
    Reviewer,
    Severity,
    _HardcodedSecretRule,
    _DebugCodeRule,
    _LongLineRule,
    _LargeFileDiffRule,
    _BinaryFileRule,
    _DeletedFileRule,
    _added_lines,
    _removed_lines,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_diff(added: list[str], removed: list[str] | None = None) -> str:
    """Build a minimal unified diff string."""
    removed = removed or []
    ctx = ["@@ -1,{r} +1,{a} @@\n".format(r=len(removed), a=len(added))]
    for line in removed:
        ctx.append(f"-{line}\n")
    for line in added:
        ctx.append(f"+{line}\n")
    return "".join(ctx)


def make_file_diff(depot_path="//depot/main/foo.py", action="edit", diff="", is_binary=False):
    return P4FileDiff(depot_path=depot_path, action=action, diff=diff, is_binary=is_binary)


# ---------------------------------------------------------------------------
# _added_lines / _removed_lines
# ---------------------------------------------------------------------------

class TestAddedRemovedLines:
    def test_added_lines(self):
        diff = make_diff(["hello world", "second line"])
        lines = list(_added_lines(diff))
        assert len(lines) == 2
        assert lines[0][1].strip() == "hello world"
        assert lines[1][1].strip() == "second line"

    def test_removed_lines(self):
        diff = make_diff([], ["old line"])
        lines = list(_removed_lines(diff))
        assert len(lines) == 1
        assert lines[0][1].strip() == "old line"

    def test_no_added_lines(self):
        diff = make_diff([])
        assert list(_added_lines(diff)) == []

    def test_ignores_diff_header(self):
        """Lines starting with +++ / --- should not be yielded."""
        diff = "+++ //depot/file.py\n--- //depot/file.py\n@@ -0,0 +1 @@\n+real content\n"
        lines = list(_added_lines(diff))
        # Only "real content" should appear, not the +++ header
        contents = [l.strip() for _, l in lines]
        assert "real content" in contents
        assert "//depot/file.py" not in contents


# ---------------------------------------------------------------------------
# Individual rules
# ---------------------------------------------------------------------------

class TestHardcodedSecretRule:
    rule = _HardcodedSecretRule()

    def test_detects_password_assignment(self):
        diff = make_diff(['password = "super_secret_123"'])
        fd = make_file_diff(diff=diff)
        findings = self.rule.check(fd)
        assert len(findings) == 1
        assert findings[0].severity == Severity.ERROR
        assert findings[0].rule == "hardcoded-secret"

    def test_detects_api_key(self):
        diff = make_diff(["api_key = 'ABCDEFGHIJ123456'"])
        fd = make_file_diff(diff=diff)
        findings = self.rule.check(fd)
        assert len(findings) == 1

    def test_no_false_positive_on_empty(self):
        diff = make_diff(["x = 1"])
        fd = make_file_diff(diff=diff)
        assert self.rule.check(fd) == []

    def test_skips_binary(self):
        fd = make_file_diff(diff=make_diff(['password = "secret"']), is_binary=True)
        assert self.rule.check(fd) == []

    def test_skips_delete_action(self):
        fd = make_file_diff(action="delete", diff=make_diff(['password = "secret"']))
        assert self.rule.check(fd) == []

    def test_short_value_no_flag(self):
        # Values shorter than 6 chars should not trigger
        diff = make_diff(['password = "hi"'])
        fd = make_file_diff(diff=diff)
        assert self.rule.check(fd) == []


class TestDebugCodeRule:
    rule = _DebugCodeRule()

    def test_pdb_set_trace(self):
        diff = make_diff(["pdb.set_trace()"])
        findings = self.rule.check(make_file_diff(diff=diff))
        assert len(findings) == 1
        assert findings[0].severity == Severity.WARNING

    def test_console_log(self):
        diff = make_diff(["console.log('debug info')"])
        findings = self.rule.check(make_file_diff(diff=diff))
        assert len(findings) == 1

    def test_todo_comment(self):
        diff = make_diff(["# TODO: fix this later"])
        findings = self.rule.check(make_file_diff(diff=diff))
        assert len(findings) == 1

    def test_clean_code(self):
        diff = make_diff(["def add(a, b): return a + b"])
        assert self.rule.check(make_file_diff(diff=diff)) == []


class TestLongLineRule:
    rule = _LongLineRule()

    def test_long_line_flagged(self):
        long_line = "x" * 301
        diff = make_diff([long_line])
        findings = self.rule.check(make_file_diff(diff=diff))
        assert len(findings) == 1
        assert findings[0].severity == Severity.INFO

    def test_normal_line_ok(self):
        diff = make_diff(["normal length line"])
        assert self.rule.check(make_file_diff(diff=diff)) == []

    def test_exactly_max_length_ok(self):
        diff = make_diff(["x" * 300])
        assert self.rule.check(make_file_diff(diff=diff)) == []


class TestLargeFileDiffRule:
    rule = _LargeFileDiffRule()

    def test_large_diff_flagged(self):
        added = [f"line {i}" for i in range(600)]
        removed = [f"old {i}" for i in range(600)]
        diff = make_diff(added, removed)
        findings = self.rule.check(make_file_diff(diff=diff))
        assert len(findings) == 1
        assert findings[0].severity == Severity.WARNING

    def test_small_diff_ok(self):
        diff = make_diff(["a", "b", "c"])
        assert self.rule.check(make_file_diff(diff=diff)) == []


class TestBinaryFileRule:
    rule = _BinaryFileRule()

    def test_binary_add_flagged(self):
        fd = make_file_diff(action="add", is_binary=True)
        findings = self.rule.check(fd)
        assert len(findings) == 1
        assert findings[0].severity == Severity.INFO

    def test_text_file_not_flagged(self):
        fd = make_file_diff(action="add", is_binary=False)
        assert self.rule.check(fd) == []

    def test_binary_delete_not_flagged(self):
        fd = make_file_diff(action="delete", is_binary=True)
        assert self.rule.check(fd) == []


class TestDeletedFileRule:
    rule = _DeletedFileRule()

    def test_delete_flagged(self):
        fd = make_file_diff(action="delete")
        findings = self.rule.check(fd)
        assert len(findings) == 1
        assert findings[0].severity == Severity.INFO

    def test_edit_not_flagged(self):
        assert self.rule.check(make_file_diff(action="edit")) == []


# ---------------------------------------------------------------------------
# Reviewer (integration)
# ---------------------------------------------------------------------------

class TestReviewer:
    def _make_reviewer(self, **kwargs):
        config = ReviewConfig(**kwargs)
        return Reviewer(config)

    def test_empty_diffs(self):
        reviewer = self._make_reviewer()
        result = reviewer.review([])
        assert result.findings == []
        assert result.reviewed_files == []

    def test_excluded_extension_skipped(self):
        reviewer = self._make_reviewer(exclude_extensions=[".png"])
        fd = make_file_diff(depot_path="//depot/img.png", diff=make_diff(["data"]))
        result = reviewer.review([fd])
        assert "//depot/img.png" in result.skipped_files
        assert result.reviewed_files == []

    def test_included_extension_filter(self):
        reviewer = self._make_reviewer(include_extensions=[".py"])
        py_fd = make_file_diff(depot_path="//depot/foo.py", diff=make_diff(["code"]))
        js_fd = make_file_diff(depot_path="//depot/bar.js", diff=make_diff(["code"]))
        result = reviewer.review([py_fd, js_fd])
        assert "//depot/foo.py" in result.reviewed_files
        assert "//depot/bar.js" in result.skipped_files

    def test_excluded_path_pattern(self):
        reviewer = self._make_reviewer(exclude_paths=["//depot/vendor/*"])
        fd = make_file_diff(depot_path="//depot/vendor/lib.py", diff=make_diff(["code"]))
        result = reviewer.review([fd])
        assert "//depot/vendor/lib.py" in result.skipped_files

    def test_diff_too_large_skipped(self):
        reviewer = self._make_reviewer(max_diff_lines=5)
        big_diff = "\n".join([f"+line {i}" for i in range(20)])
        fd = make_file_diff(diff=big_diff)
        result = reviewer.review([fd])
        assert fd.depot_path in result.skipped_files

    def test_has_errors_property(self):
        reviewer = self._make_reviewer()
        diff = make_diff(['password = "verylongsecret123"'])
        fd = make_file_diff(diff=diff)
        result = reviewer.review([fd])
        assert result.has_errors is True

    def test_no_findings_on_clean_code(self):
        reviewer = self._make_reviewer()
        diff = make_diff(["def add(a, b):", "    return a + b"])
        fd = make_file_diff(diff=diff)
        result = reviewer.review([fd])
        assert result.findings == []

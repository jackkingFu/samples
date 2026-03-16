"""Unit tests for the formatter module."""

import io
import json

import pytest

from perforce_review_agent.formatter import format_json, format_markdown, format_text
from perforce_review_agent.reviewer import Finding, ReviewResult, Severity


def _make_result(
    reviewed=("//depot/foo.py",),
    skipped=(),
    findings=(),
):
    r = ReviewResult()
    r.reviewed_files = list(reviewed)
    r.skipped_files = list(skipped)
    r.findings = list(findings)
    return r


class TestFormatText:
    def test_no_findings(self):
        result = _make_result()
        out = io.StringIO()
        format_text(result, out)
        text = out.getvalue()
        assert "No findings" in text
        assert "Files reviewed" in text

    def test_with_findings(self):
        finding = Finding(
            depot_path="//depot/foo.py",
            severity=Severity.ERROR,
            rule="hardcoded-secret",
            message="Possible secret",
            line_number=42,
            line_content='password = "abc123456"',
        )
        result = _make_result(findings=[finding])
        out = io.StringIO()
        format_text(result, out)
        text = out.getvalue()
        assert "hardcoded-secret" in text
        assert "42" in text
        assert "//depot/foo.py" in text


class TestFormatMarkdown:
    def test_no_findings(self):
        result = _make_result()
        out = io.StringIO()
        format_markdown(result, out)
        text = out.getvalue()
        assert "No findings" in text
        assert "# Perforce" in text

    def test_with_findings(self):
        finding = Finding(
            depot_path="//depot/bar.py",
            severity=Severity.WARNING,
            rule="debug-code",
            message="TODO comment",
            line_number=10,
            line_content="# TODO: remove",
        )
        result = _make_result(reviewed=["//depot/bar.py"], findings=[finding])
        out = io.StringIO()
        format_markdown(result, out)
        text = out.getvalue()
        assert "debug-code" in text
        assert "//depot/bar.py" in text
        assert "| 10 |" in text


class TestFormatJson:
    def test_structure(self):
        finding = Finding(
            depot_path="//depot/x.py",
            severity=Severity.INFO,
            rule="binary-file",
            message="Binary changed",
        )
        result = _make_result(reviewed=["//depot/x.py"], findings=[finding])
        out = io.StringIO()
        format_json(result, out)
        data = json.loads(out.getvalue())
        assert "summary" in data
        assert "findings" in data
        assert data["summary"]["reviewed_files"] == 1
        assert data["findings"][0]["rule"] == "binary-file"
        assert data["findings"][0]["severity"] == "info"

    def test_empty_result(self):
        result = _make_result(reviewed=[], skipped=[], findings=[])
        out = io.StringIO()
        format_json(result, out)
        data = json.loads(out.getvalue())
        assert data["findings"] == []
        assert data["summary"]["errors"] == 0

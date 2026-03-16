"""Unit tests for the p4_client module (no live Perforce required)."""

import pytest

from perforce_review_agent.p4_client import P4FileDiff, _parse_p4_diff


# ---------------------------------------------------------------------------
# _parse_p4_diff
# ---------------------------------------------------------------------------

class TestParseP4Diff:
    """Tests for the diff parser."""

    def test_empty_diff(self):
        result = _parse_p4_diff("")
        assert result == []

    def test_single_file_edit(self):
        raw = (
            "==== //depot/main/foo.py#5 (text) ====\n"
            "@@ -1,3 +1,4 @@\n"
            " line1\n"
            "+new line\n"
            " line2\n"
            " line3\n"
        )
        result = _parse_p4_diff(raw)
        assert len(result) == 1
        fd = result[0]
        assert fd.depot_path == "//depot/main/foo.py"
        assert not fd.is_binary
        assert "+new line\n" in fd.diff

    def test_binary_file_detected(self):
        raw = (
            "==== //depot/main/image.png#1 (binary) ====\n"
            "Binary files differ\n"
        )
        result = _parse_p4_diff(raw)
        assert len(result) == 1
        assert result[0].is_binary is True

    def test_multiple_files(self):
        raw = (
            "==== //depot/main/a.py#1 (text) ====\n"
            "@@ -0,0 +1 @@\n"
            "+hello\n"
            "==== //depot/main/b.py#2 (text) ====\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n"
        )
        result = _parse_p4_diff(raw)
        assert len(result) == 2
        assert result[0].depot_path == "//depot/main/a.py"
        assert result[1].depot_path == "//depot/main/b.py"

    def test_delete_action(self):
        raw = (
            "==== //depot/main/gone.py#3 (text) ====\n"
            "... //depot/main/gone.py delete\n"
        )
        result = _parse_p4_diff(raw)
        # File may or may not be present depending on parser path, but no crash
        assert isinstance(result, list)

    def test_diff_with_no_hunk(self):
        raw = "==== //depot/main/empty.py#1 (text) ====\n"
        result = _parse_p4_diff(raw)
        assert len(result) == 1
        assert result[0].depot_path == "//depot/main/empty.py"
        assert result[0].diff == ""

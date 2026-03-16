"""Unit tests for the config module."""

import os
import pytest

from perforce_review_agent.config import AgentConfig, P4Config, ReviewConfig, _parse_list, load_config


class TestParseList:
    def test_empty_string(self):
        assert _parse_list("") == []

    def test_single_value(self):
        assert _parse_list(".py") == [".py"]

    def test_multiple_values(self):
        assert _parse_list(".py,.js,.ts") == [".py", ".js", ".ts"]

    def test_strips_whitespace(self):
        assert _parse_list(" .py , .js ") == [".py", ".js"]

    def test_none_treated_as_empty(self):
        assert _parse_list(None or "") == []


class TestP4Config:
    def test_defaults_from_env(self, monkeypatch):
        monkeypatch.setenv("P4PORT", "myserver:1666")
        monkeypatch.setenv("P4USER", "alice")
        monkeypatch.setenv("P4CLIENT", "alice-ws")
        config = P4Config()
        assert config.port == "myserver:1666"
        assert config.user == "alice"
        assert config.client == "alice-ws"

    def test_fallback_defaults(self, monkeypatch):
        monkeypatch.delenv("P4PORT", raising=False)
        monkeypatch.delenv("P4USER", raising=False)
        monkeypatch.delenv("P4CLIENT", raising=False)
        config = P4Config()
        assert config.port == "perforce:1666"
        assert config.user == ""
        assert config.client == ""


class TestReviewConfig:
    def test_exclude_extensions_default(self):
        config = ReviewConfig()
        assert ".png" in config.exclude_extensions
        assert ".pdf" in config.exclude_extensions

    def test_fail_on_findings_env(self, monkeypatch):
        monkeypatch.setenv("REVIEW_FAIL_ON_FINDINGS", "true")
        config = ReviewConfig()
        assert config.fail_on_findings is True

    def test_fail_on_findings_default_false(self, monkeypatch):
        monkeypatch.delenv("REVIEW_FAIL_ON_FINDINGS", raising=False)
        config = ReviewConfig()
        assert config.fail_on_findings is False

    def test_output_format_env(self, monkeypatch):
        monkeypatch.setenv("REVIEW_OUTPUT_FORMAT", "json")
        config = ReviewConfig()
        assert config.output_format == "json"


class TestLoadConfig:
    def test_returns_agent_config(self):
        config = load_config()
        assert isinstance(config, AgentConfig)
        assert isinstance(config.p4, P4Config)
        assert isinstance(config.review, ReviewConfig)

    def test_changelist_from_env(self, monkeypatch):
        monkeypatch.setenv("P4_CHANGELIST", "99999")
        config = load_config()
        assert config.changelist == "99999"

    def test_changelist_none_when_unset(self, monkeypatch):
        monkeypatch.delenv("P4_CHANGELIST", raising=False)
        config = load_config()
        assert config.changelist is None

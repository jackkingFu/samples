# Perforce Review Agent

An agent that reviews code changes (changelists) against a Perforce (Helix Core) client and reports findings such as potential secrets, debug code, large diffs, and other quality issues.

## Features

| Rule | Severity | Description |
|---|---|---|
| `hardcoded-secret` | 🔴 Error | Detects possible hard-coded passwords, API keys, tokens, etc. |
| `debug-code` | 🟡 Warning | Flags `pdb.set_trace()`, `console.log`, `TODO`, `FIXME`, etc. |
| `large-diff` | 🟡 Warning | Warns when a single file has more than 1000 changed lines |
| `long-line` | 🔵 Info | Notes lines exceeding 300 characters |
| `binary-file` | 🔵 Info | Notes binary files added or modified |
| `file-deletion` | 🔵 Info | Notes files that are being deleted |

## Requirements

- Python 3.10+
- The [Perforce CLI (`p4`)](https://www.perforce.com/downloads/helix-command-line-client-p4) installed and on `$PATH`
- A configured Perforce workspace (client)

## Installation

```bash
pip install -e .
```

## Usage

### Command line

```bash
# Review the default (opened) changelist
perforce-review-agent

# Review a specific submitted or pending changelist
perforce-review-agent --changelist 12345

# Output as JSON
perforce-review-agent --changelist 12345 --format json

# Output as Markdown
perforce-review-agent --changelist 12345 --format markdown

# Fail with exit code 2 if any error-level findings are found
perforce-review-agent --changelist 12345 --fail-on-findings
```

### Environment variables

All settings can be driven from environment variables, which is useful in CI/CD pipelines:

| Variable | Default | Description |
|---|---|---|
| `P4PORT` | `perforce:1666` | Perforce server address |
| `P4USER` | *(empty)* | Perforce username |
| `P4CLIENT` | *(empty)* | Perforce client (workspace) name |
| `P4PASSWD` | *(empty)* | Perforce password / login ticket |
| `P4CHARSET` | `utf8` | Character set for Perforce Unicode servers |
| `P4_CHANGELIST` | *(empty)* | Changelist number to review |
| `REVIEW_MAX_DIFF_LINES` | `5000` | Skip files whose diff exceeds this many lines |
| `REVIEW_INCLUDE_EXTENSIONS` | *(all)* | Comma-separated list of extensions to include |
| `REVIEW_EXCLUDE_EXTENSIONS` | `.png,.jpg,...` | Comma-separated list of extensions to skip |
| `REVIEW_EXCLUDE_PATHS` | *(none)* | Comma-separated glob patterns for paths to skip |
| `REVIEW_FAIL_ON_FINDINGS` | `false` | Exit code 2 on error-level findings |
| `REVIEW_OUTPUT_FORMAT` | `text` | `text`, `json`, or `markdown` |
| `AGENT_VERBOSE` | `false` | Enable debug logging |

### Python API

```python
from perforce_review_agent import run, AgentConfig, P4Config, ReviewConfig

config = AgentConfig(
    p4=P4Config(port="myserver:1666", user="alice", client="alice-ws"),
    review=ReviewConfig(output_format="json", fail_on_findings=True),
    changelist="12345",
)

result = run(config)
print(f"Errors: {sum(1 for f in result.findings if f.severity.value == 'error')}")
```

## GitHub Actions

A ready-to-use workflow is provided in `.github/workflows/perforce-review.yml`. It can be triggered manually from the **Actions** tab in GitHub.

### Required repository secrets

| Secret | Description |
|---|---|
| `P4PORT` | Perforce server address (e.g., `ssl:perforce.example.com:1666`) |
| `P4USER` | Perforce username |
| `P4CLIENT` | Perforce client workspace name |
| `P4PASSWD` | Perforce password or login ticket |

## Running tests

```bash
pip install -r perforce_review_agent/requirements-dev.txt
pytest
```

## Project structure

```
perforce_review_agent/
├── __init__.py          # Public API
├── agent.py             # CLI entry point and main orchestration
├── config.py            # Configuration (env vars + dataclasses)
├── formatter.py         # Output formatters (text, JSON, Markdown)
├── p4_client.py         # Perforce CLI wrapper
├── reviewer.py          # Review rules and result aggregation
├── requirements.txt     # Runtime dependencies (none beyond stdlib)
├── requirements-dev.txt # Development / test dependencies
└── tests/
    ├── test_config.py
    ├── test_formatter.py
    ├── test_p4_client.py
    └── test_reviewer.py
```

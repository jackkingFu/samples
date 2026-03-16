"""Output formatters for review results."""

import json
from typing import TextIO

from .reviewer import Finding, ReviewResult, Severity


_SEVERITY_EMOJI = {
    Severity.ERROR: "🔴",
    Severity.WARNING: "🟡",
    Severity.INFO: "🔵",
}


def format_text(result: ReviewResult, out: TextIO) -> None:
    """Write a human-readable text report."""
    total = len(result.findings)
    errors = sum(1 for f in result.findings if f.severity == Severity.ERROR)
    warnings = sum(1 for f in result.findings if f.severity == Severity.WARNING)
    infos = total - errors - warnings

    out.write("=" * 72 + "\n")
    out.write("Perforce Code Review Report\n")
    out.write("=" * 72 + "\n")
    out.write(f"Files reviewed : {len(result.reviewed_files)}\n")
    out.write(f"Files skipped  : {len(result.skipped_files)}\n")
    out.write(f"Errors         : {errors}\n")
    out.write(f"Warnings       : {warnings}\n")
    out.write(f"Info           : {infos}\n")
    out.write("-" * 72 + "\n\n")

    if not result.findings:
        out.write("No findings. Looks good! ✅\n")
        return

    # Group by file
    by_file: dict = {}
    for finding in result.findings:
        by_file.setdefault(finding.depot_path, []).append(finding)

    for depot_path, findings in by_file.items():
        out.write(f"📄 {depot_path}\n")
        for f in findings:
            emoji = _SEVERITY_EMOJI.get(f.severity, "❔")
            loc = f":{f.line_number}" if f.line_number is not None else ""
            out.write(f"  {emoji} [{f.severity.value.upper()}] {f.rule}{loc} – {f.message}\n")
            if f.line_content:
                out.write(f"     {f.line_content[:120]}\n")
        out.write("\n")


def format_markdown(result: ReviewResult, out: TextIO) -> None:
    """Write a Markdown-formatted report."""
    errors = sum(1 for f in result.findings if f.severity == Severity.ERROR)
    warnings = sum(1 for f in result.findings if f.severity == Severity.WARNING)
    infos = len(result.findings) - errors - warnings

    out.write("# Perforce Code Review Report\n\n")
    out.write("| Metric | Value |\n|---|---|\n")
    out.write(f"| Files reviewed | {len(result.reviewed_files)} |\n")
    out.write(f"| Files skipped | {len(result.skipped_files)} |\n")
    out.write(f"| Errors | {errors} |\n")
    out.write(f"| Warnings | {warnings} |\n")
    out.write(f"| Info | {infos} |\n\n")

    if not result.findings:
        out.write("**No findings. Looks good!** ✅\n")
        return

    out.write("## Findings\n\n")

    by_file: dict = {}
    for finding in result.findings:
        by_file.setdefault(finding.depot_path, []).append(finding)

    for depot_path, findings in by_file.items():
        out.write(f"### `{depot_path}`\n\n")
        out.write("| Line | Severity | Rule | Message |\n|---|---|---|---|\n")
        for f in findings:
            loc = str(f.line_number) if f.line_number is not None else "-"
            out.write(f"| {loc} | {f.severity.value} | `{f.rule}` | {f.message} |\n")
        if any(f.line_content for f in findings):
            out.write("\n**Excerpts:**\n\n")
            for f in findings:
                if f.line_content:
                    loc = f":{f.line_number}" if f.line_number else ""
                    out.write(f"- `{depot_path}{loc}`: `{f.line_content[:120]}`\n")
        out.write("\n")


def format_json(result: ReviewResult, out: TextIO) -> None:
    """Write a JSON-formatted report."""
    data = {
        "summary": {
            "reviewed_files": len(result.reviewed_files),
            "skipped_files": len(result.skipped_files),
            "errors": sum(1 for f in result.findings if f.severity == Severity.ERROR),
            "warnings": sum(1 for f in result.findings if f.severity == Severity.WARNING),
            "info": sum(1 for f in result.findings if f.severity == Severity.INFO),
        },
        "reviewed_files": result.reviewed_files,
        "skipped_files": result.skipped_files,
        "findings": [
            {
                "depot_path": f.depot_path,
                "severity": f.severity.value,
                "rule": f.rule,
                "message": f.message,
                "line_number": f.line_number,
                "line_content": f.line_content,
            }
            for f in result.findings
        ],
    }
    json.dump(data, out, indent=2)
    out.write("\n")

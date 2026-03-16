"""Perforce client wrapper using the p4 command-line tool."""

import json
import logging
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .config import P4Config

logger = logging.getLogger(__name__)


@dataclass
class P4Change:
    """Represents a Perforce changelist."""

    change: str
    description: str
    user: str
    client: str
    status: str
    files: List[str] = field(default_factory=list)


@dataclass
class P4FileDiff:
    """Represents a diff for a single file in a changelist."""

    depot_path: str
    action: str  # add, edit, delete, branch, integrate, etc.
    diff: str = ""
    is_binary: bool = False


class P4ClientError(Exception):
    """Raised when a Perforce command fails."""


class P4Client:
    """Thin wrapper around the Perforce p4 command-line tool.

    Uses ``p4 -G`` (marshalled Python output) wherever possible so that the
    output can be parsed reliably without screen-scraping.
    """

    def __init__(self, config: P4Config) -> None:
        self._config = config
        self._base_cmd = self._build_base_cmd()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_base_cmd(self) -> List[str]:
        cmd = ["p4"]
        if self._config.port:
            cmd += ["-p", self._config.port]
        if self._config.user:
            cmd += ["-u", self._config.user]
        if self._config.client:
            cmd += ["-c", self._config.client]
        if self._config.charset:
            cmd += ["-C", self._config.charset]
        return cmd

    def _run(self, args: List[str], *, marshalled: bool = False) -> subprocess.CompletedProcess:
        """Run a p4 command, returning the completed process."""
        if marshalled:
            cmd = self._base_cmd + ["-G"] + args
        else:
            cmd = self._base_cmd + args

        env_patch: Dict[str, str] = {}
        if self._config.password:
            env_patch["P4PASSWD"] = self._config.password

        logger.debug("Running: %s", " ".join(cmd))
        try:
            import os

            env = {**os.environ, **env_patch}
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=not marshalled,
                env=env,
            )
        except FileNotFoundError as exc:
            raise P4ClientError(
                "The 'p4' command was not found. Please install the Perforce CLI."
            ) from exc

        if result.returncode != 0 and not marshalled:
            stderr = result.stderr.strip() if isinstance(result.stderr, str) else ""
            raise P4ClientError(f"p4 command failed: {stderr or result.stdout}")

        return result

    def _run_marshalled(self, args: List[str]) -> List[dict]:
        """Run a p4 command with -G and return the list of record dicts."""
        import marshal
        import io

        result = self._run(args, marshalled=True)
        records = []
        data = result.stdout if isinstance(result.stdout, bytes) else result.stdout.encode()
        buf = io.BytesIO(data)
        while True:
            try:
                record = marshal.load(buf)  # noqa: S302 — trusted p4 output
                records.append(record)
            except EOFError:
                break
        return records

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_connection(self) -> bool:
        """Return True if we can connect to the Perforce server."""
        try:
            result = self._run(["info"])
            return result.returncode == 0
        except P4ClientError:
            return False

    def login(self) -> None:
        """Login to Perforce using the configured password."""
        if not self._config.password:
            return
        proc = subprocess.run(
            self._base_cmd + ["login"],
            input=self._config.password,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise P4ClientError(f"p4 login failed: {proc.stderr.strip()}")

    def get_change(self, changelist: str) -> P4Change:
        """Fetch metadata for a specific changelist."""
        result = self._run(["describe", "-s", changelist])
        lines = result.stdout.splitlines()

        description_lines = []
        files: List[str] = []
        user = client = status = ""

        for line in lines:
            if line.startswith("Change ") and " by " in line:
                # e.g. "Change 12345 by user@client on 2024/01/01 *pending*"
                parts = line.split()
                try:
                    by_idx = parts.index("by")
                    user_client = parts[by_idx + 1]
                    if "@" in user_client:
                        user, client = user_client.split("@", 1)
                except (ValueError, IndexError):
                    pass
                status = "pending" if "*pending*" in line else "submitted"
            elif line.startswith("\t\t"):
                description_lines.append(line.strip())
            elif line.startswith("... //"):
                # File entry: "... //depot/path#rev action"
                parts = line.strip().lstrip("... ").rsplit("#", 1)
                if parts:
                    files.append(parts[0])

        return P4Change(
            change=changelist,
            description="\n".join(description_lines),
            user=user,
            client=client,
            status=status,
            files=files,
        )

    def get_default_changelist_files(self) -> List[str]:
        """Return the list of files opened in the default changelist."""
        records = self._run_marshalled(["opened", "-c", "default"])
        files = []
        for record in records:
            depot_file = record.get(b"depotFile", b"").decode("utf-8", errors="replace")
            if depot_file:
                files.append(depot_file)
        return files

    def get_opened_files(self, changelist: Optional[str] = None) -> List[str]:
        """Return the list of depot paths opened in a changelist."""
        args = ["opened"]
        if changelist and changelist != "default":
            args += ["-c", changelist]
        records = self._run_marshalled(args)
        files = []
        for record in records:
            depot_file = record.get(b"depotFile", b"").decode("utf-8", errors="replace")
            if depot_file:
                files.append(depot_file)
        return files

    def get_diff(self, changelist: Optional[str] = None) -> str:
        """Return the unified diff for a changelist.

        For *submitted* changelists use ``p4 describe -du``.
        For *pending* changelists use ``p4 diff -du``.
        """
        if changelist and changelist != "default":
            result = self._run(["describe", "-du", changelist])
        else:
            result = self._run(["diff", "-du"])
        return result.stdout

    def get_file_diffs(self, changelist: Optional[str] = None) -> List[P4FileDiff]:
        """Return per-file diffs for the given changelist."""
        raw_diff = self.get_diff(changelist)
        return _parse_p4_diff(raw_diff)


# ---------------------------------------------------------------------------
# Diff parser
# ---------------------------------------------------------------------------

def _parse_p4_diff(raw: str) -> List[P4FileDiff]:
    """Split a p4 diff output into per-file P4FileDiff objects."""
    file_diffs: List[P4FileDiff] = []
    current_depot_path: Optional[str] = None
    current_action = "edit"
    current_lines: List[str] = []
    is_binary = False

    for line in raw.splitlines(keepends=True):
        # p4 describe / p4 diff2 header lines look like:
        #   ==== //depot/path#rev (text) ====
        # or for a single file p4 diff:
        #   ==== //depot/path#rev - //client/path ==== (text)
        if line.startswith("==== "):
            if current_depot_path is not None:
                file_diffs.append(
                    P4FileDiff(
                        depot_path=current_depot_path,
                        action=current_action,
                        diff="".join(current_lines),
                        is_binary=is_binary,
                    )
                )
            current_lines = []
            is_binary = False
            current_action = "edit"
            # Parse depot path and action from the header
            header = line.strip().lstrip("==== ").rstrip(" ====")
            # Strip type hint like "(text)", "(binary)", "(xtext)"
            if " (" in header:
                header, type_hint = header.rsplit(" (", 1)
                type_hint = type_hint.rstrip(")")
                if "binary" in type_hint.lower():
                    is_binary = True
            # The depot path comes before the '#'
            depot_part = header.split(" - ")[0].split("#")[0].strip()
            current_depot_path = depot_part
        elif line.startswith("... //") and " " in line:
            # File action line from p4 describe -s
            parts = line.strip().lstrip("... ").rsplit(" ", 1)
            if len(parts) == 2:
                current_action = parts[1].strip()
                current_depot_path = parts[0].split("#")[0]
        elif line.startswith("Binary files ") or "differ" in line.lower():
            is_binary = True
            current_lines.append(line)
        else:
            current_lines.append(line)

    if current_depot_path is not None:
        file_diffs.append(
            P4FileDiff(
                depot_path=current_depot_path,
                action=current_action,
                diff="".join(current_lines),
                is_binary=is_binary,
            )
        )

    return file_diffs

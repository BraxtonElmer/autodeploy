from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GitResult:
    command: str
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


def _run(args: list[str], cwd: str | Path) -> GitResult:
    start = time.monotonic()
    proc = subprocess.run(
        args,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    duration_ms = int((time.monotonic() - start) * 1000)
    return GitResult(
        command=" ".join(args),
        stdout=proc.stdout.strip(),
        stderr=proc.stderr.strip(),
        exit_code=proc.returncode,
        duration_ms=duration_ms,
    )


def rev_parse_head(repo_path: str | Path) -> GitResult:
    return _run(["git", "rev-parse", "HEAD"], repo_path)


def pull(repo_path: str | Path, branch: str) -> GitResult:
    return _run(["git", "pull", "origin", branch], repo_path)


def reset_hard(repo_path: str | Path, commit_hash: str) -> GitResult:
    return _run(["git", "reset", "--hard", commit_hash], repo_path)


def run_command(command: str, cwd: str | Path) -> GitResult:
    """Run an arbitrary shell command, capturing stdout/stderr."""
    start = time.monotonic()
    proc = subprocess.run(
        command,
        cwd=str(cwd),
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    duration_ms = int((time.monotonic() - start) * 1000)
    return GitResult(
        command=command,
        stdout=proc.stdout.strip(),
        stderr=proc.stderr.strip(),
        exit_code=proc.returncode,
        duration_ms=duration_ms,
    )

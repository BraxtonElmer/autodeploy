from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List

DEFAULT_LOG_PATH = Path.home() / ".autodeploy" / "deploy.log.jsonl"


def _log_path() -> Path:
    raw = os.environ.get("LOG_PATH", "")
    return Path(raw) if raw else DEFAULT_LOG_PATH


def write(entry: dict) -> None:
    path = _log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def read(n: int = 20) -> List[dict]:
    path = _log_path()
    if not path.exists():
        return []
    lines = path.read_text().splitlines()
    entries = []
    for line in lines:
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries[-n:]


def make_entry(
    *,
    trigger: str,
    branch: str,
    commit_before: str,
    commit_after: str,
    steps: list,
    result: str,
    duration_ms: int,
) -> dict:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trigger": trigger,
        "branch": branch,
        "commit_before": commit_before,
        "commit_after": commit_after,
        "steps": steps,
        "result": result,
        "duration_ms": duration_ms,
    }


def make_step(
    *,
    name: str,
    command: str,
    stdout: str,
    stderr: str,
    exit_code: int,
    duration_ms: int,
) -> dict:
    return {
        "name": name,
        "command": command,
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
    }

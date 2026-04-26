from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from autodeploy import git, health, logger
from autodeploy.config import Config


def run(
    config: Config,
    repo_path: str | Path,
    trigger: str = "webhook",
    log_fn: Callable[[str], None] | None = None,
) -> dict:
    """Run the full deploy pipeline. Returns the log entry dict."""

    def emit(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    repo_path = Path(repo_path)
    steps: list[dict] = []
    total_start = time.monotonic()

    # 1. save current commit as rollback point
    r = git.rev_parse_head(repo_path)
    commit_before = r.stdout if r.ok else "unknown"
    steps.append(logger.make_step(
        name="rev-parse HEAD",
        command=r.command,
        stdout=r.stdout,
        stderr=r.stderr,
        exit_code=r.exit_code,
        duration_ms=r.duration_ms,
    ))
    if not r.ok:
        emit(f"[warn] could not read HEAD: {r.stderr}")

    emit(f"deploying branch {config.branch} (was {commit_before[:8]})")

    # 2. git pull
    emit("pulling...")
    r = git.pull(repo_path, config.branch)
    steps.append(logger.make_step(
        name="git pull",
        command=r.command,
        stdout=r.stdout,
        stderr=r.stderr,
        exit_code=r.exit_code,
        duration_ms=r.duration_ms,
    ))
    if not r.ok:
        emit(f"pull failed: {r.stderr}")
        return _fail_or_rollback(config, repo_path, steps, commit_before, trigger, total_start, emit)

    commit_after_r = git.rev_parse_head(repo_path)
    commit_after = commit_after_r.stdout if commit_after_r.ok else "unknown"
    emit(f"pulled to {commit_after[:8]}")

    # 3. build commands
    for cmd in config.build:
        emit(f"running: {cmd}")
        r = git.run_command(cmd, repo_path)
        steps.append(logger.make_step(
            name=f"build: {cmd}",
            command=r.command,
            stdout=r.stdout,
            stderr=r.stderr,
            exit_code=r.exit_code,
            duration_ms=r.duration_ms,
        ))
        if not r.ok:
            emit(f"build failed (exit {r.exit_code}): {cmd}")
            return _fail_or_rollback(config, repo_path, steps, commit_before, trigger, total_start, emit,
                                     commit_after=commit_after)

    # 4. restart
    emit(f"restarting: {config.restart.command}")
    r = git.run_command(config.restart.command, repo_path)
    steps.append(logger.make_step(
        name="restart",
        command=r.command,
        stdout=r.stdout,
        stderr=r.stderr,
        exit_code=r.exit_code,
        duration_ms=r.duration_ms,
    ))
    if not r.ok:
        emit(f"restart failed: {r.stderr}")
        return _fail_or_rollback(config, repo_path, steps, commit_before, trigger, total_start, emit,
                                 commit_after=commit_after)

    # 5. health check
    if config.health_check:
        hc = config.health_check
        emit(f"health check: {hc.url} (retries={hc.retries}, timeout={hc.timeout}s)")
        hc_start = time.monotonic()
        result = health.check(hc.url, timeout=hc.timeout, retries=hc.retries)
        hc_ms = int((time.monotonic() - hc_start) * 1000)
        steps.append(logger.make_step(
            name="health check",
            command=f"GET {hc.url}",
            stdout=f"status={result.status_code} attempts={result.attempts}",
            stderr=result.error or "",
            exit_code=0 if result.success else 1,
            duration_ms=hc_ms,
        ))
        if not result.success:
            emit(f"health check failed after {result.attempts} attempts: {result.error}")
            return _fail_or_rollback(config, repo_path, steps, commit_before, trigger, total_start, emit,
                                     commit_after=commit_after)
        emit(f"healthy after {result.attempts} attempt(s)")

    # success
    duration_ms = int((time.monotonic() - total_start) * 1000)
    entry = logger.make_entry(
        trigger=trigger,
        branch=config.branch,
        commit_before=commit_before,
        commit_after=commit_after,
        steps=steps,
        result="success",
        duration_ms=duration_ms,
    )
    logger.write(entry)
    emit(f"deploy done in {duration_ms}ms")
    return entry


def _fail_or_rollback(
    config: Config,
    repo_path: Path,
    steps: list[dict],
    commit_before: str,
    trigger: str,
    total_start: float,
    emit: Callable[[str], None],
    commit_after: str = "unknown",
) -> dict:
    result = "failed"

    if config.rollback.on_failure and commit_before != "unknown":
        emit(f"rolling back to {commit_before[:8]}...")

        r = git.reset_hard(repo_path, commit_before)
        steps.append(logger.make_step(
            name="rollback reset",
            command=r.command,
            stdout=r.stdout,
            stderr=r.stderr,
            exit_code=r.exit_code,
            duration_ms=r.duration_ms,
        ))

        r2 = git.run_command(config.restart.command, repo_path)
        steps.append(logger.make_step(
            name="rollback restart",
            command=r2.command,
            stdout=r2.stdout,
            stderr=r2.stderr,
            exit_code=r2.exit_code,
            duration_ms=r2.duration_ms,
        ))
        result = "rolled_back"
        emit("rolled back")

    duration_ms = int((time.monotonic() - total_start) * 1000)
    entry = logger.make_entry(
        trigger=trigger,
        branch=config.branch,
        commit_before=commit_before,
        commit_after=commit_after,
        steps=steps,
        result=result,
        duration_ms=duration_ms,
    )
    logger.write(entry)
    return entry

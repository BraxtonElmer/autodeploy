from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml


@dataclass
class HealthCheck:
    url: str
    timeout: int = 30
    retries: int = 3


@dataclass
class Restart:
    command: str


@dataclass
class Rollback:
    on_failure: bool = False


@dataclass
class Config:
    branch: str
    restart: Restart
    build: List[str] = field(default_factory=list)
    health_check: Optional[HealthCheck] = None
    rollback: Rollback = field(default_factory=Rollback)


class ConfigError(Exception):
    pass


def load(repo_path: str | os.PathLike) -> Config:
    path = Path(repo_path) / "deploy.yaml"
    if not path.exists():
        raise ConfigError(f"deploy.yaml not found in {repo_path}")

    try:
        with path.open() as f:
            raw = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"deploy.yaml is invalid YAML: {e}") from e

    if not isinstance(raw, dict):
        raise ConfigError("deploy.yaml must be a YAML mapping")

    branch = raw.get("branch")
    if not branch or not isinstance(branch, str):
        raise ConfigError("deploy.yaml: 'branch' is required and must be a string")

    restart_raw = raw.get("restart")
    if not restart_raw or not isinstance(restart_raw, dict):
        raise ConfigError("deploy.yaml: 'restart' section is required")
    restart_cmd = restart_raw.get("command")
    if not restart_cmd or not isinstance(restart_cmd, str):
        raise ConfigError("deploy.yaml: 'restart.command' is required and must be a string")

    build = raw.get("build") or []
    if not isinstance(build, list):
        raise ConfigError("deploy.yaml: 'build' must be a list of commands")
    for i, cmd in enumerate(build):
        if not isinstance(cmd, str):
            raise ConfigError(f"deploy.yaml: 'build[{i}]' must be a string")

    health_check = None
    hc_raw = raw.get("health_check")
    if hc_raw:
        if not isinstance(hc_raw, dict):
            raise ConfigError("deploy.yaml: 'health_check' must be a mapping")
        url = hc_raw.get("url")
        if not url or not isinstance(url, str):
            raise ConfigError("deploy.yaml: 'health_check.url' is required")
        health_check = HealthCheck(
            url=url,
            timeout=int(hc_raw.get("timeout", 30)),
            retries=int(hc_raw.get("retries", 3)),
        )

    rollback = Rollback()
    rb_raw = raw.get("rollback")
    if rb_raw and isinstance(rb_raw, dict):
        rollback = Rollback(on_failure=bool(rb_raw.get("on_failure", False)))

    return Config(
        branch=branch,
        restart=Restart(command=restart_cmd),
        build=build,
        health_check=health_check,
        rollback=rollback,
    )

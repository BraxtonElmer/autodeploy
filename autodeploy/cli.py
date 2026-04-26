from __future__ import annotations

import os
import secrets
import subprocess
import sys
from pathlib import Path

import click
from dotenv import load_dotenv

from autodeploy import __version__

ENV_FILE = Path(".env")
SYSTEMD_SERVICE = Path("/etc/systemd/system/autodeploy.service")
SYSTEMD_AVAILABLE = sys.platform == "linux" and Path("/etc/systemd/system").exists()


def _load_env() -> None:
    load_dotenv(ENV_FILE)


def _repo_path() -> Path | None:
    p = os.environ.get("REPO_PATH", "")
    return Path(p) if p else None


def _require_repo_path() -> Path:
    p = _repo_path()
    if not p:
        raise click.ClickException("REPO_PATH not set. Run 'autodeploy init' first.")
    if not p.exists():
        raise click.ClickException(f"REPO_PATH does not exist: {p}")
    return p


def _run_systemctl(action: str, service: str = "autodeploy") -> int:
    result = subprocess.run(["systemctl", action, service], capture_output=True, text=True)
    return result.returncode


@click.group()
@click.version_option(__version__, prog_name="autodeploy")
@click.option("--debug", is_flag=True, default=False, hidden=True)
@click.pass_context
def main(ctx: click.Context, debug: bool) -> None:
    """Self-hosted auto-deploy via GitHub webhooks."""
    ctx.ensure_object(dict)
    ctx.obj["debug"] = debug
    if not debug:
        sys.tracebacklimit = 0
    _load_env()


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

@main.command()
def init() -> None:
    """Interactive setup wizard."""
    click.echo("autodeploy setup\n")

    repo_path = click.prompt("Repo path (absolute path to your project)")
    repo_path = str(Path(repo_path).expanduser().resolve())
    if not Path(repo_path).exists():
        raise click.ClickException(f"Path does not exist: {repo_path}")

    branch = click.prompt("Branch to watch", default="main")

    build_cmds = []
    click.echo("Build commands (one per line, empty line to finish):")
    while True:
        cmd = click.prompt("  build step", default="", show_default=False)
        if not cmd:
            break
        build_cmds.append(cmd)

    restart_cmd = click.prompt("Restart command (e.g. pm2 restart myapp)")

    hc_url = click.prompt("Health check URL (optional, press Enter to skip)", default="", show_default=False)

    secret = click.prompt(
        "Webhook secret (press Enter to generate one)",
        default="",
        show_default=False,
    )
    if not secret:
        secret = secrets.token_hex(32)
        click.echo(f"  generated secret: {secret}")

    port = click.prompt("Port for webhook server", default="5000")

    # write deploy.yaml
    yaml_lines = [f"branch: {branch}\n"]
    if build_cmds:
        yaml_lines.append("build:\n")
        for cmd in build_cmds:
            yaml_lines.append(f"  - {cmd}\n")
    yaml_lines.append("\nrestart:\n")
    yaml_lines.append(f"  command: {restart_cmd}\n")
    if hc_url:
        yaml_lines.append("\nhealth_check:\n")
        yaml_lines.append(f"  url: {hc_url}\n")
        yaml_lines.append("  timeout: 30\n")
        yaml_lines.append("  retries: 3\n")
    yaml_lines.append("\nrollback:\n")
    yaml_lines.append("  on_failure: true\n")

    deploy_yaml = Path(repo_path) / "deploy.yaml"
    deploy_yaml.write_text("".join(yaml_lines))
    click.echo(f"\nwrote {deploy_yaml}")

    # write .env
    env_lines = [
        f"WEBHOOK_SECRET={secret}\n",
        f"REPO_PATH={repo_path}\n",
        f"PORT={port}\n",
    ]
    ENV_FILE.write_text("".join(env_lines))
    click.echo(f"wrote {ENV_FILE.resolve()}")

    # systemd service
    python_bin = sys.executable
    work_dir = str(Path.cwd())
    service_content = f"""[Unit]
Description=autodeploy webhook server
After=network.target

[Service]
Type=simple
User={os.environ.get("USER", "root")}
WorkingDirectory={work_dir}
EnvironmentFile={ENV_FILE.resolve()}
ExecStart={python_bin} -m autodeploy.server
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
"""

    if SYSTEMD_AVAILABLE:
        try:
            SYSTEMD_SERVICE.write_text(service_content)
            click.echo(f"wrote {SYSTEMD_SERVICE}")
            subprocess.run(["systemctl", "daemon-reload"], check=True, capture_output=True)
            subprocess.run(["systemctl", "enable", "autodeploy"], check=True, capture_output=True)
            click.echo("systemd service enabled")
        except PermissionError:
            click.echo("\nno permission to write systemd service — save this manually:")
            click.echo(f"\n{service_content}")
            click.echo(f"then run: sudo systemctl enable autodeploy")
        except subprocess.CalledProcessError as e:
            click.echo(f"systemctl error: {e}")
    else:
        service_file = Path("autodeploy.service")
        service_file.write_text(service_content)
        click.echo(f"\nsystemd not available. service file written to {service_file.resolve()}")
        click.echo("to run manually:")
        click.echo(f"  source {ENV_FILE.resolve()} && {python_bin} -m autodeploy.server")

    click.echo("\nsetup complete.")
    click.echo(f"  run 'autodeploy start' to start the service")
    click.echo(f"  webhook URL: http://your-server:{port}/webhook")


# ---------------------------------------------------------------------------
# start / stop
# ---------------------------------------------------------------------------

@main.command()
def start() -> None:
    """Start the autodeploy service."""
    if not SYSTEMD_AVAILABLE:
        raise click.ClickException("systemd not available. Start manually: python -m autodeploy.server")
    rc = _run_systemctl("start")
    if rc == 0:
        click.echo("autodeploy started")
        _run_systemctl("status")
    else:
        raise click.ClickException("failed to start service (check: journalctl -u autodeploy)")


@main.command()
def stop() -> None:
    """Stop the autodeploy service."""
    if not SYSTEMD_AVAILABLE:
        raise click.ClickException("systemd not available.")
    rc = _run_systemctl("stop")
    if rc == 0:
        click.echo("autodeploy stopped")
    else:
        raise click.ClickException("failed to stop service")


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

@main.command()
def status() -> None:
    """Show current deploy status."""
    repo_path = _require_repo_path()

    # current commit
    from autodeploy import git
    r = git.rev_parse_head(repo_path)
    if r.ok:
        short = r.stdout[:12]
        msg_r = git.run_command("git log -1 --pretty=%s", repo_path)
        msg = msg_r.stdout if msg_r.ok else ""
        click.echo(f"commit   {short}  {msg}")
    else:
        click.echo("commit   (unknown)")

    # config
    try:
        from autodeploy.config import load as load_config
        cfg = load_config(repo_path)
        click.echo(f"branch   {cfg.branch}")
    except Exception:
        click.echo("branch   (could not read deploy.yaml)")

    # last deploy
    from autodeploy import logger
    entries = logger.read(n=1)
    if entries:
        e = entries[-1]
        click.echo(f"last deploy   {e['timestamp']}  result={e['result']}  {e['commit_before'][:8]} → {e['commit_after'][:8]}")
    else:
        click.echo("last deploy   (none)")

    # service running?
    if SYSTEMD_AVAILABLE:
        rc = _run_systemctl("is-active")
        state = "running" if rc == 0 else "stopped"
    else:
        state = "unknown (no systemd)"
    click.echo(f"service  {state}")


# ---------------------------------------------------------------------------
# logs
# ---------------------------------------------------------------------------

@main.command()
@click.option("-n", default=20, show_default=True, help="Number of log entries to show.")
def logs(n: int) -> None:
    """Show recent deploy logs."""
    from autodeploy import logger
    entries = logger.read(n=n)
    if not entries:
        click.echo("no deploy logs found")
        return

    for e in entries:
        ts = e.get("timestamp", "?")
        result = e.get("result", "?")
        ms = e.get("duration_ms", 0)
        before = e.get("commit_before", "?")[:8]
        after = e.get("commit_after", "?")[:8]
        trigger = e.get("trigger", "?")
        secs = ms / 1000
        click.echo(f"{ts}  [{result:12s}]  {before} → {after}  {secs:.1f}s  ({trigger})")


# ---------------------------------------------------------------------------
# rollback
# ---------------------------------------------------------------------------

@main.command()
def rollback() -> None:
    """Roll back to the previous commit."""
    repo_path = _require_repo_path()

    from autodeploy import git, logger
    from autodeploy.config import load as load_config

    try:
        cfg = load_config(repo_path)
    except Exception as e:
        raise click.ClickException(f"could not load deploy.yaml: {e}")

    entries = logger.read(n=2)
    if len(entries) < 1:
        raise click.ClickException("no deploy history found — nothing to roll back to")

    current_entry = entries[-1]
    target_hash = current_entry.get("commit_before")
    if not target_hash or target_hash == "unknown":
        raise click.ClickException("could not determine rollback commit from logs")

    current_hash_r = git.rev_parse_head(repo_path)
    current_hash = current_hash_r.stdout if current_hash_r.ok else "unknown"

    click.echo(f"rolling back {current_hash[:8]} → {target_hash[:8]}")

    import time
    steps = []
    total_start = time.monotonic()

    r = git.reset_hard(repo_path, target_hash)
    steps.append(logger.make_step(
        name="rollback reset",
        command=r.command,
        stdout=r.stdout,
        stderr=r.stderr,
        exit_code=r.exit_code,
        duration_ms=r.duration_ms,
    ))
    if not r.ok:
        raise click.ClickException(f"git reset failed: {r.stderr}")

    click.echo(f"restarting: {cfg.restart.command}")
    r2 = git.run_command(cfg.restart.command, repo_path)
    steps.append(logger.make_step(
        name="rollback restart",
        command=r2.command,
        stdout=r2.stdout,
        stderr=r2.stderr,
        exit_code=r2.exit_code,
        duration_ms=r2.duration_ms,
    ))

    duration_ms = int((time.monotonic() - total_start) * 1000)
    entry = logger.make_entry(
        trigger="manual",
        branch=cfg.branch,
        commit_before=current_hash,
        commit_after=target_hash,
        steps=steps,
        result="rolled_back",
        duration_ms=duration_ms,
    )
    logger.write(entry)
    click.echo(f"rolled back in {duration_ms}ms")

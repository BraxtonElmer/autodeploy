import sys
import click

from autodeploy import __version__


@click.group()
@click.version_option(__version__, prog_name="autodeploy")
@click.option("--debug", is_flag=True, default=False, hidden=True,
              help="Show full tracebacks on errors.")
@click.pass_context
def main(ctx: click.Context, debug: bool) -> None:
    """Self-hosted auto-deploy via GitHub webhooks."""
    ctx.ensure_object(dict)
    ctx.obj["debug"] = debug

    if not debug:
        sys.tracebacklimit = 0


@main.command()
def init() -> None:
    """Interactive setup wizard."""
    click.echo("not implemented")


@main.command()
def start() -> None:
    """Start the autodeploy service."""
    click.echo("not implemented")


@main.command()
def stop() -> None:
    """Stop the autodeploy service."""
    click.echo("not implemented")


@main.command()
def status() -> None:
    """Show current deploy status."""
    click.echo("not implemented")


@main.command()
@click.option("-n", default=20, show_default=True, help="Number of log entries to show.")
def logs(n: int) -> None:
    """Show recent deploy logs."""
    click.echo("not implemented")


@main.command()
def rollback() -> None:
    """Roll back to the previous commit."""
    click.echo("not implemented")

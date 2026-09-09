import typer

from eos.cli._common import cli_command, run

ray_app = typer.Typer(help="Manage the EOS Ray cluster", no_args_is_help=True)


@ray_app.command()
@cli_command("Failed to start head node")
def head(
    dashboard: bool = typer.Option(False, "--dashboard", help="Enable the Ray dashboard"),
    additional_params: list[str] = typer.Argument(None, help="Additional parameters to pass to 'ray start'"),
) -> None:
    """Start a Ray head node."""
    cmd = ["ray", "start", "--head", "--resources", '{"eos": 1000}', "--disable-usage-stats"]
    if not dashboard:
        cmd.append("--include-dashboard=false")
    if additional_params:
        cmd.extend(additional_params)
    run(cmd)
    typer.echo("Started the Ray head node.")


@ray_app.command()
@cli_command("Failed to start worker node")
def worker(
    address: str = typer.Option(..., "--address", "-a", help="Address of the head node to connect to"),
    additional_params: list[str] = typer.Argument(None, help="Additional parameters to pass to 'ray start'"),
) -> None:
    """Start a Ray worker node connected to the given head node."""
    cmd = ["ray", "start", "--address", address, "--disable-usage-stats"]
    if additional_params:
        cmd.extend(additional_params)
    run(cmd)
    typer.echo(f"Started a Ray worker node connecting to {address}.")


@ray_app.command()
@cli_command("Failed to stop Ray")
def stop() -> None:
    """Stop Ray on this node."""
    run(["ray", "stop"])


@ray_app.command()
@cli_command("Failed to retrieve status")
def status() -> None:
    """Show the Ray cluster status."""
    run(["ray", "status"])

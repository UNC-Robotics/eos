import typer

ray_app = typer.Typer(help="Manage EOS Ray cluster commands", no_args_is_help=True)


@ray_app.command()
def head(
    additional_params: list[str] = typer.Argument(None, help="Additional parameters to pass to 'ray start'"),
) -> None:
    """
    Create a Ray head node.
    """
    import subprocess

    cmd = ["ray", "start", "--head", "--resources", '{"eos": 1000}', "--disable-usage-stats"]

    # Append any additional parameters provided by the user
    if additional_params:
        cmd.extend(additional_params)

    try:
        subprocess.run(cmd, check=True)
        typer.echo("Started the Ray head node.")
    except subprocess.CalledProcessError as e:
        typer.echo(f"Failed to start head node: {e}", err=True)
        raise typer.Exit(1) from e


@ray_app.command()
def worker(
    address: str = typer.Option(..., "--address", "-a", help="Address of the head node to connect to"),
    additional_params: list[str] = typer.Argument(
        None, help="Additional parameters to pass to 'ray start' for worker node"
    ),
) -> None:
    """
    Create a Ray worker node that connects to a specified head node.

    This command calls the Ray CLI command:
        ray start --address <address> <additional_params>
    """
    import subprocess

    # Base Ray CLI command for worker node
    cmd = ["ray", "start", "--address", address, "--disable-usage-stats"]

    # Append any additional parameters provided by the user
    if additional_params:
        cmd.extend(additional_params)

    try:
        subprocess.run(cmd, check=True)
        typer.echo(f"Started a Ray worker node connecting to {address}.")
    except subprocess.CalledProcessError as e:
        typer.echo(f"Failed to start worker node: {e}", err=True)
        raise typer.Exit(1) from e


@ray_app.command()
def stop() -> None:
    """
    Stop Ray.

    This command calls the Ray CLI command:
        ray stop
    """
    import subprocess

    cmd = ["ray", "stop"]

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        typer.echo(f"Failed to stop Ray: {e}", err=True)
        raise typer.Exit(1) from e


@ray_app.command()
def status() -> None:
    """
    Display the current status of the Ray cluster.

    This command calls the Ray CLI command:
        ray status
    """
    import subprocess

    cmd = ["ray", "status"]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        typer.echo(f"Failed to retrieve status: {e}", err=True)
        raise typer.Exit(1) from e

"""CLI entry point for the EOS scheduling simulator."""

from typing import Annotated

import typer

from eos.scheduling.simulation import run_simulation


def simulate(
    config: Annotated[str, typer.Argument(help="Path to simulation config YAML")],
    user_dir: Annotated[
        str, typer.Option("--user-dir", "-u", help="User directory containing EOS packages")
    ] = "./user",
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Show scheduling decisions")] = False,
    jitter: Annotated[float, typer.Option("--jitter", help="Duration jitter fraction (e.g. 0.1 = +/-10%%)")] = 0.0,
    seed: Annotated[int | None, typer.Option("--seed", help="Random seed for reproducibility")] = None,
    scheduler: Annotated[str, typer.Option("--scheduler", "-s", help="Scheduler type: greedy or cpsat")] = "greedy",
) -> None:
    """Run a discrete-event simulation of the EOS scheduler."""
    run_simulation(
        config_path=config,
        user_dir=user_dir,
        verbose=verbose,
        jitter=jitter,
        seed=seed,
        scheduler_type=scheduler,
    )

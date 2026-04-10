"""CLI entry point for the EOS scheduling simulator."""

import json
import logging
import sys
from typing import Annotated

import typer

from eos.scheduling.simulation import compute_sim_stats, run_simulation


def simulate(
    config: Annotated[str, typer.Argument(help="Path to simulation config YAML")],
    user_dir: Annotated[
        str, typer.Option("--user-dir", "-u", help="User directory containing EOS packages")
    ] = "./user",
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Show scheduling decisions")] = False,
    jitter: Annotated[float, typer.Option("--jitter", help="Duration jitter fraction (e.g. 0.1 = +/-10%%)")] = 0.0,
    seed: Annotated[int | None, typer.Option("--seed", help="Random seed for reproducibility")] = None,
    scheduler: Annotated[str, typer.Option("--scheduler", "-s", help="Scheduler type: greedy or cpsat")] = "greedy",
    output_json: Annotated[
        bool, typer.Option("--json", help="Output results as JSON (suppresses text output)")
    ] = False,
) -> None:
    """Run a discrete-event simulation of the EOS scheduler."""
    if output_json:
        logging.getLogger("rich").setLevel(logging.CRITICAL)

    timeline = run_simulation(
        config_path=config,
        user_dir=user_dir,
        verbose=verbose if not output_json else False,
        jitter=jitter,
        seed=seed,
        scheduler_type=scheduler,
        quiet=output_json,
    )

    if not output_json:
        return

    starts = [e for e in timeline if e.event_type == "START"]
    completions = [e for e in timeline if e.event_type == "DONE"]
    stats = compute_sim_stats(starts, completions, scheduler)
    task_records = [
        {
            "protocol_run": ev.protocol_run_name,
            "task": ev.task_name,
            "start": ev.time,
            "duration": ev.duration,
            "end": ev.time + ev.duration,
            "devices": [{"slot": slot, "lab": d.lab_name, "name": d.name} for slot, d in ev.devices.items()],
            "resources": dict(ev.resources.items()),
        }
        for ev in starts
    ]
    sys.stdout.write(json.dumps({"timeline": task_records, "stats": stats}))

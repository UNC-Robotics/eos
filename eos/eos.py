#!/usr/bin/env python3

import typer

from eos.cli.auth_cli import auth_app
from eos.cli.db_cli import db_app
from eos.cli.pkg_cli import pkg_app
from eos.cli.ray_cli import ray_app
from eos.cli.services_cli import services_app
from eos.cli.setup_cli import run_setup
from eos.cli.sim_cli import simulate
from eos.cli.start_cli import start_app
from eos.cli.update_cli import update
from eos.cli.web_cli import start_web_ui

eos_app = typer.Typer(pretty_exceptions_show_locals=False, no_args_is_help=True)
eos_app.command(name="setup", help="Interactively set up EOS")(run_setup)
eos_app.add_typer(start_app, name="start")
eos_app.add_typer(services_app, name="services")
eos_app.add_typer(auth_app, name="auth")
eos_app.add_typer(db_app, name="db")
eos_app.add_typer(pkg_app, name="pkg")
eos_app.add_typer(ray_app, name="ray")
eos_app.command(name="sim", help="Run a scheduling simulation")(simulate)
eos_app.command(name="ui", help="Start the EOS web UI", hidden=True)(start_web_ui)
eos_app.command(name="update", help="Update EOS")(update)

if __name__ == "__main__":
    eos_app()

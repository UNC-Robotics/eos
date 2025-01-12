#!/usr/bin/env python3

import typer

from eos.cli.db_cli import db_app
from eos.cli.orchestrator_cli import start_orchestrator
from eos.cli.pkg_cli import pkg_app

eos_app = typer.Typer(pretty_exceptions_show_locals=False)
eos_app.command(name="orchestrator", help="Start the EOS orchestrator")(start_orchestrator)
eos_app.add_typer(db_app, name="db", help="Manage the EOS database")
eos_app.add_typer(pkg_app, name="pkg", help="Manage EOS packages")

if __name__ == "__main__":
    eos_app()

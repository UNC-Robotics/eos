import typer

from eos.cli.orchestrator_cli import start_orchestrator
from eos.cli.services_cli import services_up
from eos.cli.web_cli import start_web_ui

start_app = typer.Typer(
    help="Start EOS components",
    invoke_without_command=True,
)

# Bare `eos start` runs the orchestrator; subcommands start the other components.
start_app.callback(invoke_without_command=True)(start_orchestrator)
start_app.command(name="ui", help="Start the EOS web UI")(start_web_ui)
start_app.command(name="services", help="Start infrastructure services (alias for 'eos services up')")(services_up)

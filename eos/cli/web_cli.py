import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer

WEB_UI_DIR = Path(__file__).resolve().parents[2] / "web_ui"


def start_web_ui(
    dev: Annotated[bool, typer.Option("--dev", "-d", help="Run the development server instead of production")] = False,
    build: Annotated[
        bool, typer.Option("--build", "-b", help="Force a rebuild even if a build already exists")
    ] = False,
    host: Annotated[str, typer.Option("--host", "-H", help="Host to bind to (default: 127.0.0.1)")] = "127.0.0.1",
) -> None:
    """Start the EOS web UI."""
    if not WEB_UI_DIR.is_dir():
        typer.echo(f"Error: web UI directory not found at {WEB_UI_DIR}", err=True)
        raise typer.Exit(1)

    if not (WEB_UI_DIR / "node_modules").is_dir():
        typer.echo("Error: node_modules not found. Run 'npm install' in the web_ui/ directory first.", err=True)
        raise typer.Exit(1)

    npm = shutil.which("npm")
    if npm is None:
        typer.echo("Error: npm not found on PATH.", err=True)
        raise typer.Exit(1)

    env = {**os.environ, "HOST": host}

    if dev:
        typer.echo("Starting web UI in development mode...")
        sys.exit(subprocess.call([npm, "run", "dev"], cwd=WEB_UI_DIR, env=env))
    else:
        needs_build = build or not (WEB_UI_DIR / ".next").is_dir()
        if needs_build:
            typer.echo("Building web UI...")
            result = subprocess.call([npm, "run", "build"], cwd=WEB_UI_DIR)
            if result != 0:
                typer.echo("Error: build failed.", err=True)
                raise typer.Exit(result)

        typer.echo("Starting web UI...")
        sys.exit(subprocess.call([npm, "start"], cwd=WEB_UI_DIR, env=env))

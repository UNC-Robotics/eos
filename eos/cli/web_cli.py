import os
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer

from eos.utils.net import is_port_in_use

WEB_UI_DIR = Path(__file__).resolve().parents[2] / "web_ui"
WEB_UI_ENV = WEB_UI_DIR / ".env"
IS_WINDOWS = os.name == "nt"
DEFAULT_UI_PORT = 3000


def _run_npm(*args: str, cwd: Path, env: dict[str, str] | None = None) -> int:
    return subprocess.call(["npm", *args], cwd=cwd, env=env, shell=IS_WINDOWS)  # noqa: S607


def _node_ca_from_env_file() -> str | None:
    """Read NODE_EXTRA_CA_CERTS from web_ui/.env.

    Node configures its TLS trust store at process startup, before Next.js loads .env, so the value must
    be in the process environment from the start. A shell export wins; otherwise we inject the .env value.
    """
    if "NODE_EXTRA_CA_CERTS" in os.environ or not WEB_UI_ENV.exists():
        return None
    for line in WEB_UI_ENV.read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() == "NODE_EXTRA_CA_CERTS":
            return value.strip().strip("\"'") or None
    return None


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

    port = int(os.environ.get("PORT", DEFAULT_UI_PORT))
    if is_port_in_use(host, port):
        typer.echo(
            f"Error: port {host}:{port} is already in use. The web UI may already be running.",
            err=True,
        )
        raise typer.Exit(1)

    env = {**os.environ, "HOST": host}
    node_ca = _node_ca_from_env_file()
    if node_ca:
        env["NODE_EXTRA_CA_CERTS"] = node_ca

    try:
        if dev:
            typer.echo("Starting web UI in development mode...")
            sys.exit(_run_npm("run", "dev", cwd=WEB_UI_DIR, env=env))
        else:
            needs_build = build or not (WEB_UI_DIR / ".next").is_dir()
            if needs_build:
                typer.echo("Building web UI...")
                result = _run_npm("run", "build", cwd=WEB_UI_DIR)
                if result != 0:
                    typer.echo("Error: build failed.", err=True)
                    raise typer.Exit(result)

            typer.echo("Starting web UI...")
            sys.exit(_run_npm("start", cwd=WEB_UI_DIR, env=env))
    except FileNotFoundError:
        typer.echo("Error: npm not found on PATH.", err=True)
        raise typer.Exit(1) from None

import asyncio
import importlib.metadata
import os
import signal
import sys
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, TYPE_CHECKING

import typer

if sys.platform == "win32":
    # Prevent Intel Fortran runtime from intercepting signals and aborting the process
    os.environ.setdefault("FOR_DISABLE_CONSOLE_CTRL_HANDLER", "1")

import eos.configuration.env  # noqa: F401

from eos.cli._common import DEFAULT_CONFIG_PATH, load_config
from eos.configuration.eos_config import EosConfig
from eos.logging.logger import log, LogLevel
from eos.utils.net import is_port_in_use

if TYPE_CHECKING:
    from eos.orchestration.orchestrator import Orchestrator
    import uvicorn


EOS_BANNER = f"""Experiment Orchestration System v{importlib.metadata.version("eos")}

███████╗ ██████╗ ███████╗
██╔════╝██╔═══██╗██╔════╝
█████╗  ██║   ██║███████╗
██╔══╝  ██║   ██║╚════██║
███████╗╚██████╔╝███████║
╚══════╝ ╚═════╝ ╚══════╝
"""


def parse_list_arg(arg: str | None) -> list[str]:
    """Parse a comma-separated string into a list of stripped items."""
    return [item.strip() for item in arg.split(",")] if arg else []


def _block_shutdown_signals() -> None:
    """
    Block SIGINT/SIGTERM so Ray's C-level sigaction handlers can't intercept them.

    A dedicated thread uses sigwait() to catch these signals instead.
    Must be called before asyncio.run() and ray.init() so all spawned threads
    inherit the blocked signal mask.
    """
    if sys.platform != "win32":
        signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})


async def setup_orchestrator(config: EosConfig) -> "Orchestrator":
    """Initialize and set up the orchestrator with labs and protocols."""
    from eos.orchestration.orchestrator import Orchestrator

    orchestrator = Orchestrator(config)
    await orchestrator.initialize()

    async with orchestrator.db_interface.get_async_session() as db:
        await orchestrator.loading.load_labs(db, config.labs)
        await orchestrator.loading.load_protocols(db, config.protocols)

    return orchestrator


@asynccontextmanager
async def handle_shutdown(
    orchestrator: "Orchestrator", web_api_server: "uvicorn.Server"
) -> AsyncIterator[asyncio.Event]:
    """Context manager for graceful shutdown handling."""
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    if sys.platform != "win32":
        # Unix: use sigwait() in a dedicated thread to catch blocked signals.
        shutdown_signals = {signal.SIGINT, signal.SIGTERM}
        shutdown_count = 0

        def _signal_waiter() -> None:
            """Wait for shutdown signals and trigger graceful/forced exit."""
            nonlocal shutdown_count
            while True:
                signal.sigwait(shutdown_signals)
                if not shutdown_event.is_set():
                    log.warning("Shutdown signal.")
                    loop.call_soon_threadsafe(shutdown_event.set)
                elif shutdown_count == 0:
                    shutdown_count = 1
                    log.warning("Shutdown in progress. Press Ctrl+C again to force exit.")
                else:
                    log.warning("Forcing shutdown.")
                    os._exit(1)

        waiter = threading.Thread(target=_signal_waiter, daemon=True, name="signal-waiter")
        waiter.start()
    else:
        # Windows: use signal.signal() since sigwait is not available.
        def _signal_handler(*_) -> None:
            if not shutdown_event.is_set():
                log.warning("Shutdown signal.")
                loop.call_soon_threadsafe(shutdown_event.set)

        win_signals = [signal.SIGINT]
        if hasattr(signal, "SIGBREAK"):
            win_signals.append(signal.SIGBREAK)
        original_handlers = {sig: signal.signal(sig, _signal_handler) for sig in win_signals}

    try:
        yield shutdown_event
    finally:
        if sys.platform == "win32":
            for sig, handler in original_handlers.items():
                signal.signal(sig, handler)

        from eos.logging.log_buffer import log_buffer

        log_buffer.shutdown()

        log.info("Shutting down the web API...")
        web_api_server.should_exit = True
        await web_api_server.shutdown()

        log.info("Shutting down the orchestrator...")
        await orchestrator.terminate()

        log.info("EOS shut down.")


async def run_eos(config: EosConfig) -> None:
    """Run the EOS orchestrator and web API server."""
    from eos.logging.log_buffer import log_buffer

    log_buffer.set_loop(asyncio.get_running_loop())

    from eos.web_api.app import build_web_api

    orchestrator = await setup_orchestrator(config)
    web_api_server = build_web_api(orchestrator, config)

    if not config.auth.enabled:
        log.warning("AUTHENTICATION IS DISABLED. The REST API is unprotected. Do not expose it on untrusted networks.")

    log.info("EOS initialized.")

    async with handle_shutdown(orchestrator, web_api_server) as shutdown_event:
        tasks = [
            asyncio.create_task(
                orchestrator.spin(config.orchestrator_hz.rate, config.orchestrator_hz.maintenance_interval)
            ),
            asyncio.create_task(web_api_server.serve()),
            asyncio.create_task(shutdown_event.wait()),
        ]

        # Run until any task completes (typically the shutdown monitor on Ctrl+C)
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

        # Log any exceptions from completed tasks
        for task in done:
            try:
                exc = task.exception()
                if exc is not None:
                    log.error(f"Task failed with exception: {exc}")
            except asyncio.CancelledError:
                pass

        # Cancel any still-running tasks
        for task in pending:
            task.cancel()

        # Wait for all tasks to finish cancelling
        await asyncio.gather(*pending, return_exceptions=True)


def start_orchestrator(
    ctx: typer.Context,
    config_file: Annotated[
        str, typer.Option("--config", "-c", help="Path to the EOS configuration file")
    ] = DEFAULT_CONFIG_PATH,
    user_dir: (
        Annotated[str, typer.Option("--user-dir", "-u", help="The directory containing EOS user configurations")] | None
    ) = None,
    labs: (
        Annotated[str, typer.Option("--labs", "-l", help="Comma-separated list of lab configurations to load")] | None
    ) = None,
    protocols: (
        Annotated[
            str,
            typer.Option("--protocols", "-e", help="Comma-separated list of protocol configurations to load"),
        ]
        | None
    ) = None,
    log_level: Annotated[LogLevel, typer.Option("--log-level", "-v", help="Logging level")] = None,
    profile: Annotated[bool, typer.Option("--profile", help="Enable function profiling report on exit")] = False,
    profile_mem: Annotated[
        bool, typer.Option("--profile-mem", help="Also profile memory (RSS + tracemalloc). Use with --profile")
    ] = False,
    profile_mem_all: Annotated[
        bool,
        typer.Option("--profile-mem-all", help="Profile all Python memory, not just EOS. Implies --profile-mem"),
    ] = False,
) -> None:
    """Start the EOS orchestrator with the given configuration."""
    if ctx.invoked_subcommand is not None:
        return

    typer.echo(EOS_BANNER)

    file_config = load_config(config_file)

    cli_overrides = {}
    if user_dir:
        cli_overrides["user_dir"] = user_dir
    parsed_labs = parse_list_arg(labs)
    if parsed_labs:
        cli_overrides["labs"] = parsed_labs
    parsed_protocols = parse_list_arg(protocols)
    if parsed_protocols:
        cli_overrides["protocols"] = parsed_protocols
    if log_level is not None:
        cli_overrides["log_level"] = log_level.value

    if cli_overrides:
        config_dict = file_config.model_dump()
        config_dict.update(cli_overrides)
        config = EosConfig.model_validate(config_dict)
    else:
        config = file_config

    log.set_level(config.log_level)

    if is_port_in_use(config.web_api.host, config.web_api.port):
        log.error(
            f"Port {config.web_api.host}:{config.web_api.port} is already in use. "
            "EOS may already be running; refusing to start a second instance."
        )
        raise typer.Exit(1)

    if profile or profile_mem or profile_mem_all:
        from eos.utils.profiler import start as start_profiler

        start_profiler(memory=profile_mem or profile_mem_all, memory_all=profile_mem_all)

    _block_shutdown_signals()
    asyncio.run(run_eos(config))

import asyncio
import importlib.metadata
import os
import signal
import sys
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, TYPE_CHECKING

import typer
import yaml

if sys.platform == "win32":
    # Prevent Intel Fortran runtime from intercepting signals and aborting the process
    os.environ.setdefault("FOR_DISABLE_CONSOLE_CTRL_HANDLER", "1")

# Suppress Ray GPU override warning
os.environ.setdefault("RAY_ACCEL_ENV_VAR_OVERRIDE_ON_ZERO", "0")

from eos.configuration.eos_config import EosConfig, WebApiConfig
from eos.logging.logger import log, LogLevel

if TYPE_CHECKING:
    from eos.orchestration.orchestrator import Orchestrator
    import uvicorn


EOS_BANNER = f"""Experiment Orchestration System v{importlib.metadata.version("eos")}
 ▄▄▄▄▄▄▄▄▄▄▄  ▄▄▄▄▄▄▄▄▄▄▄  ▄▄▄▄▄▄▄▄▄▄▄
▐░░░░░░░░░░░▌▐░░░░░░░░░░░▌▐░░░░░░░░░░░▌
▐░█▀▀▀▀▀▀▀▀▀ ▐░█▀▀▀▀▀▀▀█░▌▐░█▀▀▀▀▀▀▀▀▀
▐░█▄▄▄▄▄▄▄▄▄ ▐░▌       ▐░▌▐░█▄▄▄▄▄▄▄▄▄
▐░░░░░░░░░░░▌▐░▌       ▐░▌▐░░░░░░░░░░░▌
▐░█▀▀▀▀▀▀▀▀▀ ▐░▌       ▐░▌ ▀▀▀▀▀▀▀▀▀█░▌
▐░█▄▄▄▄▄▄▄▄▄ ▐░█▄▄▄▄▄▄▄█░▌ ▄▄▄▄▄▄▄▄▄█░▌
▐░░░░░░░░░░░▌▐░░░░░░░░░░░▌▐░░░░░░░░░░░▌
 ▀▀▀▀▀▀▀▀▀▀▀  ▀▀▀▀▀▀▀▀▀▀▀  ▀▀▀▀▀▀▀▀▀▀▀
"""


def load_config(config_file: str) -> EosConfig:
    """Load EOS configuration from a YAML file."""
    config_file_path = Path(config_file)
    if not config_file_path.exists():
        raise FileNotFoundError(f"Config file '{config_file}' does not exist")

    with Path.open(config_file_path) as f:
        user_config = yaml.safe_load(f) or {}

    return EosConfig(**user_config)


def parse_list_arg(arg: str | None) -> list[str]:
    """Parse a comma-separated string into a list of stripped items."""
    return [item.strip() for item in arg.split(",")] if arg else []


def _get_shutdown_signals() -> list[signal.Signals]:
    """Get the list of signals to handle for graceful shutdown based on platform."""
    signals_to_handle = [signal.SIGINT]
    if sys.platform == "win32" and hasattr(signal, "SIGBREAK"):
        signals_to_handle.append(signal.SIGBREAK)
    elif sys.platform != "win32":
        signals_to_handle.append(signal.SIGTERM)
    return signals_to_handle


def _register_shutdown_handlers(
    loop: asyncio.AbstractEventLoop,
    signal_handler: Callable,
    signals_to_handle: list[signal.Signals],
) -> dict:
    """Register signal handlers for shutdown. Returns original handlers on Windows, empty dict on Unix."""
    if sys.platform == "win32":
        # Windows: asyncio signal handlers not supported, use standard signal.signal()
        return {sig: signal.signal(sig, signal_handler) for sig in signals_to_handle}

    # Unix/Linux: use asyncio's native signal handlers
    for sig in signals_to_handle:
        loop.add_signal_handler(sig, signal_handler)
    return {}


def _cleanup_shutdown_handlers(
    loop: asyncio.AbstractEventLoop,
    signals_to_handle: list[signal.Signals],
    original_handlers: dict,
) -> None:
    """Clean up signal handlers."""
    if sys.platform == "win32":
        for sig, handler in original_handlers.items():
            signal.signal(sig, handler)
    else:
        for sig in signals_to_handle:
            loop.remove_signal_handler(sig)


async def setup_orchestrator(config: EosConfig) -> "Orchestrator":
    """Initialize and set up the orchestrator with labs and experiments."""
    from eos.orchestration.orchestrator import Orchestrator

    orchestrator = Orchestrator(config)
    await orchestrator.initialize()

    async with orchestrator.db_interface.get_async_session() as db:
        await orchestrator.loading.load_labs(db, config.labs)

    await orchestrator.loading.load_experiments(config.experiments)

    return orchestrator


def setup_web_api(orchestrator: "Orchestrator", config: WebApiConfig) -> "uvicorn.Server":
    """Set up the web API server."""
    from litestar import Litestar, Router
    from litestar import Controller
    from litestar.config.cors import CORSConfig
    from litestar.logging import LoggingConfig
    from litestar.openapi import OpenAPIConfig
    from litestar.openapi.plugins import ScalarRenderPlugin
    import uvicorn
    from eos.web_api.controllers.campaign_controller import CampaignController
    from eos.web_api.controllers.experiment_controller import ExperimentController
    from eos.web_api.controllers.file_controller import FileController
    from eos.web_api.controllers.lab_controller import LabController
    from eos.web_api.controllers.rpc_controller import RPCController
    from eos.web_api.controllers.task_controller import TaskController
    from eos.web_api.dependencies import get_common_dependencies
    from eos.web_api.exception_handling import general_exception_handler

    litestar_logging_config = LoggingConfig(
        configure_root_logger=False,
        loggers={"litestar": {"level": "CRITICAL"}},
    )
    os.environ["LITESTAR_WARN_IMPLICIT_SYNC_TO_THREAD"] = "0"

    controllers: list[type[Controller]] = [
        CampaignController,
        ExperimentController,
        FileController,
        LabController,
        RPCController,
        TaskController,
    ]

    api_router = Router(
        path="/api",
        route_handlers=controllers,
        dependencies=get_common_dependencies(orchestrator),
    )

    cors_config = CORSConfig(
        allow_origins=["*"],
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    openapi_config = OpenAPIConfig(
        title="EOS REST API",
        description="EOS REST API documentation",
        version="0.1.0",
        path="/docs",
        render_plugins=[ScalarRenderPlugin()],
    )

    web_api_app = Litestar(
        route_handlers=[api_router],
        logging_config=litestar_logging_config,
        exception_handlers={Exception: general_exception_handler},
        cors_config=cors_config,
        openapi_config=openapi_config,
    )

    uv_config = uvicorn.Config(web_api_app, host=config.host, port=config.port, log_level="critical")

    return uvicorn.Server(uv_config)


@asynccontextmanager
async def handle_shutdown(
    orchestrator: "Orchestrator", web_api_server: "uvicorn.Server"
) -> AsyncIterator[asyncio.Event]:
    """Context manager for graceful shutdown handling via signals."""
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def signal_handler(*_) -> None:
        """Signal handler that safely triggers shutdown via event."""
        if not shutdown_event.is_set():
            log.warning("Shutdown signal.")
            loop.call_soon_threadsafe(shutdown_event.set)

    signals_to_handle = _get_shutdown_signals()
    original_handlers = _register_shutdown_handlers(loop, signal_handler, signals_to_handle)

    try:
        yield shutdown_event
    finally:
        _cleanup_shutdown_handlers(loop, signals_to_handle, original_handlers)

        log.info("Shutting down the web API...")
        web_api_server.should_exit = True
        await web_api_server.shutdown()

        log.info("Shutting down the orchestrator...")
        await orchestrator.terminate()

        log.info("EOS shut down.")


async def run_eos(config: EosConfig) -> None:
    """Run the EOS orchestrator and web API server."""
    orchestrator = await setup_orchestrator(config)
    web_api_server = setup_web_api(orchestrator, config.web_api)

    log.info("EOS initialized.")

    async with handle_shutdown(orchestrator, web_api_server) as shutdown_event:

        async def wait_for_shutdown() -> None:
            """Task that completes when shutdown is requested."""
            await shutdown_event.wait()

        # Create all main tasks
        tasks = [
            asyncio.create_task(orchestrator.spin(config.orchestrator_hz.min, config.orchestrator_hz.max)),
            asyncio.create_task(web_api_server.serve()),
            asyncio.create_task(wait_for_shutdown()),
        ]

        # Run until any task completes (typically the shutdown monitor on Ctrl+C)
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

        # Cancel any still-running tasks
        for task in pending:
            task.cancel()

        # Wait for all tasks to finish cancelling
        await asyncio.gather(*pending, return_exceptions=True)


def start_orchestrator(
    config_file: Annotated[
        str, typer.Option("--config", "-c", help="Path to the EOS configuration file")
    ] = "./config.yml",
    user_dir: (
        Annotated[str, typer.Option("--user-dir", "-u", help="The directory containing EOS user configurations")] | None
    ) = None,
    labs: (
        Annotated[str, typer.Option("--labs", "-l", help="Comma-separated list of lab configurations to load")] | None
    ) = None,
    experiments: (
        Annotated[
            str,
            typer.Option("--experiments", "-e", help="Comma-separated list of experiment configurations to load"),
        ]
        | None
    ) = None,
    log_level: Annotated[LogLevel, typer.Option("--log-level", "-v", help="Logging level")] = None,
) -> None:
    """Start the EOS orchestrator with the given configuration."""
    typer.echo(EOS_BANNER)

    file_config = load_config(config_file)

    cli_overrides = {}
    if user_dir:
        cli_overrides["user_dir"] = user_dir
    parsed_labs = parse_list_arg(labs)
    if parsed_labs:
        cli_overrides["labs"] = parsed_labs
    parsed_experiments = parse_list_arg(experiments)
    if parsed_experiments:
        cli_overrides["experiments"] = parsed_experiments
    if log_level is not None:
        cli_overrides["log_level"] = log_level.value

    if cli_overrides:
        config_dict = file_config.model_dump()
        config_dict.update(cli_overrides)
        config = EosConfig.model_validate(config_dict)
    else:
        config = file_config

    log.set_level(config.log_level)

    asyncio.run(run_eos(config))

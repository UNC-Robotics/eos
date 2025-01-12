import asyncio
import contextlib
import functools
import os
import signal
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Annotated
import importlib.metadata

import typer
import uvicorn
import yaml
from litestar import Litestar, Router
from litestar.di import Provide
from litestar.logging import LoggingConfig

from eos.configuration.entities.eos_config import EosConfig, WebApiConfig
from eos.logging.logger import log, LogLevel
from eos.orchestration.orchestrator import Orchestrator
from eos.web_api.controllers.campaign_controller import CampaignController
from eos.web_api.controllers.experiment_controller import ExperimentController
from eos.web_api.controllers.file_controller import FileController
from eos.web_api.controllers.lab_controller import LabController
from eos.web_api.controllers.task_controller import TaskController
from eos.web_api.exception_handling import global_exception_handler


def load_config(config_file: str) -> EosConfig:
    config_file_path = Path(config_file)
    if not config_file_path.exists():
        raise FileNotFoundError(f"Config file '{config_file}' does not exist")

    with Path.open(config_file_path) as f:
        user_config = yaml.safe_load(f) or {}

    return EosConfig(**user_config)


def parse_list_arg(arg: str | None) -> list[str]:
    return [item.strip() for item in arg.split(",")] if arg else []


@contextlib.asynccontextmanager
async def handle_shutdown(
    orchestrator: Orchestrator, web_api_server: uvicorn.Server
) -> AbstractAsyncContextManager[None]:
    class GracefulExit(SystemExit):
        pass

    loop = asyncio.get_running_loop()
    shutdown_initiated = False

    def signal_handler(*_) -> None:
        nonlocal shutdown_initiated
        if not shutdown_initiated:
            log.warning("Shut down signal.")
            shutdown_initiated = True
            raise GracefulExit()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, functools.partial(signal_handler))

    try:
        yield
    except GracefulExit:
        pass
    finally:
        log.info("Shutting down the web API...")
        web_api_server.should_exit = True
        await web_api_server.shutdown()

        log.info("Shutting down the orchestrator...")
        await orchestrator.terminate()

        log.info("EOS shut down.")


async def setup_orchestrator(config: EosConfig) -> Orchestrator:
    orchestrator = Orchestrator(str(config.user_dir), config.db, config.file_db)
    await orchestrator.initialize()

    async with orchestrator.db_interface.get_async_session() as db:
        await orchestrator.loading.load_labs(db, config.labs)

    orchestrator.loading.load_experiments(config.experiments)

    return orchestrator


def setup_web_api(orchestrator: Orchestrator, config: WebApiConfig) -> uvicorn.Server:
    litestar_logging_config = LoggingConfig(
        configure_root_logger=False,
        loggers={"litestar": {"level": "CRITICAL"}},
    )
    os.environ["LITESTAR_WARN_IMPLICIT_SYNC_TO_THREAD"] = "0"

    api_router = Router(
        path="/api",
        route_handlers=[TaskController, ExperimentController, CampaignController, LabController, FileController],
        dependencies={
            "orchestrator": Provide(lambda: orchestrator),
        },
    )

    web_api_app = Litestar(
        route_handlers=[api_router],
        logging_config=litestar_logging_config,
        exception_handlers={Exception: global_exception_handler},
    )

    uv_config = uvicorn.Config(web_api_app, host=config.host, port=config.port, log_level="critical")

    return uvicorn.Server(uv_config)


async def run_eos(config: EosConfig) -> None:
    orchestrator = await setup_orchestrator(config)
    web_api_server = setup_web_api(orchestrator, config.web_api)

    log.info("EOS initialized.")

    async with handle_shutdown(orchestrator, web_api_server):
        await asyncio.gather(
            orchestrator.spin(config.orchestrator_min_hz, config.orchestrator_max_hz), web_api_server.serve()
        )


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
        config = EosConfig(**config_dict)
    else:
        config = file_config

    log.set_level(config.log_level)

    asyncio.run(run_eos(config))


EOS_BANNER = f"""The Experiment Orchestration System, {importlib.metadata.version("eos")}
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

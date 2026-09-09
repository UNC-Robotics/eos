"""Builds the EOS web API (Litestar app served by uvicorn)."""

import os
from typing import TYPE_CHECKING

import uvicorn
from litestar import Controller, Litestar, Router
from litestar.config.cors import CORSConfig
from litestar.datastructures import State
from litestar.logging import LoggingConfig
from litestar.middleware import DefineMiddleware
from litestar.openapi import OpenAPIConfig
from litestar.openapi.plugins import ScalarRenderPlugin

from eos.auth.middleware import EosAuthenticationMiddleware
from eos.auth.token_validator import TokenValidator
from eos.configuration.eos_config import EosConfig
from eos.web_api.controllers.admin_controller import AdminController
from eos.web_api.controllers.api_token_controller import ApiTokenController
from eos.web_api.controllers.campaign_controller import CampaignController
from eos.web_api.controllers.definition_controller import DefinitionController
from eos.web_api.controllers.file_controller import FileController
from eos.web_api.controllers.health_controller import HealthController
from eos.web_api.controllers.lab_controller import LabController
from eos.web_api.controllers.log_controller import LogController
from eos.web_api.controllers.optimizer_controller import OptimizerController
from eos.web_api.controllers.package_controller import PackageController
from eos.web_api.controllers.protocol_controller import ProtocolController
from eos.web_api.controllers.refresh_controller import RefreshController
from eos.web_api.controllers.resource_controller import ResourceController
from eos.web_api.controllers.rpc_controller import RPCController
from eos.web_api.controllers.simulator_controller import SimulatorController
from eos.web_api.controllers.task_controller import TaskController
from eos.web_api.dependencies import get_common_dependencies
from eos.web_api.exception_handling import general_exception_handler

if TYPE_CHECKING:
    from eos.orchestration.orchestrator import Orchestrator

CONTROLLERS: list[type[Controller]] = [
    AdminController,
    ApiTokenController,
    CampaignController,
    DefinitionController,
    ProtocolController,
    FileController,
    HealthController,
    LabController,
    LogController,
    OptimizerController,
    PackageController,
    RefreshController,
    ResourceController,
    RPCController,
    SimulatorController,
    TaskController,
]


def build_web_api(orchestrator: "Orchestrator", config: EosConfig) -> uvicorn.Server:
    """Build the uvicorn server hosting the EOS REST API."""
    litestar_logging_config = LoggingConfig(
        configure_root_logger=False,
        loggers={"litestar": {"level": "CRITICAL"}},
    )
    os.environ["LITESTAR_WARN_IMPLICIT_SYNC_TO_THREAD"] = "0"

    api_router = Router(
        path="/api",
        route_handlers=CONTROLLERS,
        dependencies=get_common_dependencies(orchestrator),
    )

    cors_config = CORSConfig(
        allow_origins=config.web_api.cors_origins,
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

    state = State({"db_interface": orchestrator.db_interface})
    middleware = []
    if config.auth.enabled:
        state["token_validator"] = TokenValidator(config.auth, orchestrator.db_interface)
        middleware.append(DefineMiddleware(EosAuthenticationMiddleware, exclude=["^/api/health", "^/docs", "^/schema"]))

    web_api_app = Litestar(
        route_handlers=[api_router],
        logging_config=litestar_logging_config,
        exception_handlers={Exception: general_exception_handler},
        cors_config=cors_config,
        openapi_config=openapi_config,
        middleware=middleware,
        state=state,
    )

    uv_config = uvicorn.Config(web_api_app, host=config.web_api.host, port=config.web_api.port, log_level="critical")
    return uvicorn.Server(uv_config)

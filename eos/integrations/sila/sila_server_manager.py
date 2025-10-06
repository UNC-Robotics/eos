"""SiLA 2 server lifecycle management for EOS devices."""

import asyncio
import socket
from typing import Any

try:
    from ray.util import get_node_ip_address
except ImportError:

    def get_node_ip_address() -> str:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()


class SilaServerInstance:
    """Single SiLA server instance with lifecycle management."""

    def __init__(
        self,
        name: str,
        server_class: type,
        bind_ip: str = "0.0.0.0",  # noqa: S104
        port: int = 0,
        insecure: bool = True,
        advertise_ip: str | None = None,
    ):
        """
        Initialize SiLA server instance.

        :param name: Unique identifier for this server
        :param server_class: The generated SiLA Server class
        :param bind_ip: IP to bind on
        :param port: Port to bind (0 = auto-assign a free port)
        :param insecure: Use insecure connections
        :param advertise_ip: IP clients should connect to (None = auto-detect)
        """
        self.name = name
        self._server_class = server_class
        self._server: Any | None = None
        self._bind_ip = bind_ip
        self._advertise_ip = advertise_ip or get_node_ip_address()
        self._port = port
        self._insecure = insecure
        self._started = False

    async def start(self) -> None:
        """Start the SiLA server."""
        if self._port == 0:
            self._port = self._find_free_port()

        self._server = self._server_class()

        if self._insecure:
            await asyncio.to_thread(self._server.start_insecure, self._bind_ip, self._port)
        else:
            await asyncio.to_thread(self._server.start, self._bind_ip, self._port)

        self._started = True

    async def stop(self) -> None:
        """Stop the SiLA server."""
        if self._server and self._started:
            await asyncio.to_thread(self._server.stop)
            self._started = False

    def get_endpoint(self) -> dict[str, Any]:
        """Get connection endpoint information."""
        if not self._started:
            raise RuntimeError(f"SiLA server '{self.name}' not started")

        return {
            "address": self._advertise_ip,
            "port": self._port,
            "insecure": self._insecure,
        }

    def get_status(self) -> dict[str, Any]:
        """Get current server status."""
        return {
            "name": self.name,
            "address": self._advertise_ip,
            "port": self._port,
            "started": self._started,
        }

    @staticmethod
    def _find_free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            return s.getsockname()[1]


class SilaServerManager:
    """Manages multiple SiLA server instances within an EOS device."""

    def __init__(self):
        self._servers: dict[str, SilaServerInstance] = {}
        self._default_bind_ip = "0.0.0.0"  # noqa: S104
        self._default_advertise_ip: str | None = None
        self._default_insecure = True

    def add_server(
        self,
        name: str,
        server_class: type,
        port: int = 0,
        bind_ip: str | None = None,
        advertise_ip: str | None = None,
        insecure: bool | None = None,
    ) -> None:
        """
        Register a SiLA server.

        :param name: Unique identifier for this server
        :param server_class: The generated SiLA Server class
        :param port: Port to bind (0 = auto-assign a free port)
        :param bind_ip: IP to bind on (None = use default from init_parameters)
        :param advertise_ip: IP clients should connect to (None = auto-detect)
        :param insecure: Use insecure connections (None = use default from init_parameters)
        """
        if name in self._servers:
            raise ValueError(f"SiLA server '{name}' already registered")

        instance = SilaServerInstance(
            name=name,
            server_class=server_class,
            bind_ip=bind_ip or self._default_bind_ip,
            port=port,
            insecure=insecure if insecure is not None else self._default_insecure,
            advertise_ip=advertise_ip or self._default_advertise_ip,
        )
        self._servers[name] = instance

    async def start_all(self, init_parameters: dict[str, Any] | None = None) -> None:
        """
        Start all registered SiLA servers concurrently.

        :param init_parameters: Device init params (can contain sila_bind_ip, sila_insecure, etc.)
        """
        if init_parameters:
            self._apply_init_parameters(init_parameters)

        await asyncio.gather(*[server.start() for server in self._servers.values()])

    async def start_server(self, name: str, init_parameters: dict[str, Any] | None = None) -> None:
        """
        Start a specific SiLA server by name.

        :param name: Name of the server to start
        :param init_parameters: Device init params (can contain sila_bind_ip, sila_insecure, etc.)
        """
        if name not in self._servers:
            raise ValueError(f"SiLA server '{name}' not registered")

        if init_parameters:
            self._apply_init_parameters(init_parameters)

        await self._servers[name].start()

    async def stop_all(self) -> None:
        """Stop all SiLA servers concurrently."""
        await asyncio.gather(*[server.stop() for server in self._servers.values()])

    async def stop_server(self, name: str) -> None:
        """
        Stop a specific SiLA server by name.

        :param name: Name of the server to stop
        """
        if name not in self._servers:
            raise ValueError(f"SiLA server '{name}' not registered")

        await self._servers[name].stop()

    def get_endpoint(self, name: str) -> dict[str, Any]:
        """
        Get connection endpoint for a specific server.

        :param name: Name of the server
        :return: Dictionary with 'address', 'port', 'insecure' keys
        """
        if name not in self._servers:
            raise ValueError(f"SiLA server '{name}' not registered")

        return self._servers[name].get_endpoint()

    def get_all_endpoints(self) -> dict[str, dict[str, Any]]:
        """Get connection endpoints for all registered servers."""
        return {name: server.get_endpoint() for name, server in self._servers.items()}

    def get_status(self) -> dict[str, Any]:
        """Get status of all servers."""
        return {
            "servers": {name: server.get_status() for name, server in self._servers.items()},
            "count": len(self._servers),
        }

    def list_servers(self) -> list[str]:
        """Get names of all registered servers."""
        return list(self._servers.keys())

    def _apply_init_parameters(self, init_parameters: dict[str, Any]) -> None:
        self._default_bind_ip = str(init_parameters.get("sila_bind_ip", self._default_bind_ip))
        self._default_insecure = bool(init_parameters.get("sila_insecure", self._default_insecure))
        if "sila_advertise_ip" in init_parameters:
            self._default_advertise_ip = init_parameters["sila_advertise_ip"]

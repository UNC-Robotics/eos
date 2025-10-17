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
            "connection_type": "manual",
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


class SilaServerConnection:
    """Represents a connection to an external SiLA server."""

    def __init__(
        self,
        name: str,
        # Manual connection parameters
        address: str | None = None,
        port: int | None = None,
        # Discovery parameters
        server_name: str | None = None,
        server_uuid: str | None = None,
        timeout: float = 0,
        # Common parameters
        insecure: bool = True,
        root_certs: str | None = None,
        private_key: str | None = None,
        cert_chain: str | None = None,
    ):
        """
        Initialize external SiLA server connection.

        Use either manual connection (address + port) OR discovery (server_name and/or server_uuid).

        Manual connection:
            :param address: Server address to connect to
            :param port: Server port to connect to

        Discovery:
            :param server_name: Server name for discovery
            :param server_uuid: Server UUID for discovery (optional)
            :param timeout: Discovery timeout in seconds (default: 0 = no timeout)

        Common:
            :param name: Unique identifier for this connection
            :param insecure: Use insecure connections
            :param root_certs: Path to root certificates for TLS
            :param private_key: Path to private key for TLS
            :param cert_chain: Path to certificate chain for TLS

        :raises ValueError: If neither manual nor discovery parameters provided, or if both provided
        """
        self.name = name

        # Validate connection type
        has_manual = address is not None and port is not None
        has_discovery = server_name is not None or server_uuid is not None

        if not has_manual and not has_discovery:
            raise ValueError(
                "Must provide either manual connection (address + port) or discovery (server_name and/or server_uuid)"
            )
        if has_manual and has_discovery:
            raise ValueError(
                "Cannot specify both manual connection (address + port) and discovery (server_name/server_uuid)"
            )

        # Store connection type and parameters
        self._connection_type = "manual" if has_manual else "discovery"

        # Manual connection fields
        self._address = address
        self._port = port

        # Discovery fields
        self._server_name = server_name
        self._server_uuid = server_uuid
        self._timeout = timeout

        # Common fields
        self._insecure = insecure
        self._root_certs = root_certs
        self._private_key = private_key
        self._cert_chain = cert_chain

    def get_endpoint(self) -> dict[str, Any]:
        """Get connection endpoint information."""
        endpoint: dict[str, Any] = {
            "connection_type": self._connection_type,
            "insecure": self._insecure,
        }

        if self._connection_type == "manual":
            endpoint["address"] = self._address
            endpoint["port"] = self._port
        else:  # discovery
            if self._server_name:
                endpoint["server_name"] = self._server_name
            if self._server_uuid:
                endpoint["server_uuid"] = self._server_uuid
            endpoint["timeout"] = self._timeout

        if self._root_certs:
            endpoint["root_certs"] = self._root_certs
        if self._private_key:
            endpoint["private_key"] = self._private_key
        if self._cert_chain:
            endpoint["cert_chain"] = self._cert_chain

        return endpoint

    def get_status(self) -> dict[str, Any]:
        """Get current connection status."""
        status: dict[str, Any] = {
            "name": self.name,
            "type": "external",
            "connection_type": self._connection_type,
        }

        if self._connection_type == "manual":
            status["address"] = self._address
            status["port"] = self._port
        else:  # discovery
            if self._server_name:
                status["server_name"] = self._server_name
            if self._server_uuid:
                status["server_uuid"] = self._server_uuid

        return status


class SilaServerManager:
    """Manages multiple SiLA server instances and external connections within an EOS device."""

    def __init__(self):
        self._servers: dict[str, SilaServerInstance] = {}
        self._connections: dict[str, SilaServerConnection] = {}

    def add_server(
        self,
        name: str,
        server_class: type,
        port: int = 0,
        bind_ip: str = "0.0.0.0",  # noqa: S104
        advertise_ip: str | None = None,
        insecure: bool = True,
    ) -> None:
        """
        Register a SiLA server.

        :param name: Unique identifier for this server
        :param server_class: The generated SiLA Server class
        :param port: Port to bind (0 = auto-assign a free port)
        :param bind_ip: IP to bind on (default: "0.0.0.0" for all interfaces)
        :param advertise_ip: IP clients should connect to (None = auto-detect)
        :param insecure: Use insecure connections (default: True for development)
        """
        if name in self._servers:
            raise ValueError(f"SiLA server '{name}' already registered")

        instance = SilaServerInstance(
            name=name,
            server_class=server_class,
            bind_ip=bind_ip,
            port=port,
            insecure=insecure,
            advertise_ip=advertise_ip,
        )
        self._servers[name] = instance

    def add_connection(
        self,
        name: str,
        # Manual connection parameters
        address: str | None = None,
        port: int | None = None,
        # Discovery parameters
        server_name: str | None = None,
        server_uuid: str | None = None,
        timeout: float = 0,
        # Common parameters
        insecure: bool = True,
        root_certs: str | None = None,
        private_key: str | None = None,
        cert_chain: str | None = None,
    ) -> None:
        """
        Register an external SiLA server connection.

        Use either manual connection (address + port) OR discovery (server_name and/or server_uuid).

        Manual connection:
            :param address: Server address to connect to
            :param port: Server port to connect to

        Discovery:
            :param server_name: Server name for discovery
            :param server_uuid: Server UUID for discovery (optional)
            :param timeout: Discovery timeout in seconds (default: 0 = no timeout)

        Common:
            :param name: Unique identifier for this connection
            :param insecure: Use insecure connections
            :param root_certs: Path to root certificates for TLS
            :param private_key: Path to private key for TLS
            :param cert_chain: Path to certificate chain for TLS
        """
        if name in self._connections or name in self._servers:
            raise ValueError(f"SiLA server or connection '{name}' already registered")

        connection = SilaServerConnection(
            name=name,
            address=address,
            port=port,
            server_name=server_name,
            server_uuid=server_uuid,
            timeout=timeout,
            insecure=insecure,
            root_certs=root_certs,
            private_key=private_key,
            cert_chain=cert_chain,
        )
        self._connections[name] = connection

    async def start_all(self) -> None:
        """Start all registered SiLA servers concurrently."""
        await asyncio.gather(*[server.start() for server in self._servers.values()])

    async def start_server(self, name: str) -> None:
        """
        Start a specific SiLA server by name.

        :param name: Name of the server to start
        """
        if name not in self._servers:
            raise ValueError(f"SiLA server '{name}' not registered")

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
        Get connection endpoint for a specific server or connection.

        :param name: Name of the server or connection
        :return: Dictionary with 'address', 'port', 'insecure' keys
        """
        if name in self._servers:
            return self._servers[name].get_endpoint()
        if name in self._connections:
            return self._connections[name].get_endpoint()
        raise ValueError(f"SiLA server or connection '{name}' not registered")

    def get_all_endpoints(self) -> dict[str, dict[str, Any]]:
        """Get connection endpoints for all registered servers and connections."""
        endpoints = {}
        endpoints.update({name: server.get_endpoint() for name, server in self._servers.items()})
        endpoints.update({name: conn.get_endpoint() for name, conn in self._connections.items()})
        return endpoints

    def get_status(self) -> dict[str, Any]:
        """Get status of all servers and connections."""
        hosted = {name: server.get_status() for name, server in self._servers.items()}
        external = {name: conn.get_status() for name, conn in self._connections.items()}
        return {
            "hosted_servers": hosted,
            "external_connections": external,
            "count": len(self._servers) + len(self._connections),
        }

    def list_servers(self) -> list[str]:
        """Get names of all registered servers and connections."""
        return list(self._servers.keys()) + list(self._connections.keys())

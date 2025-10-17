"""Mixin for adding SiLA servers to EOS devices."""

from typing import Any

from eos.integrations.sila.sila_server_manager import SilaServerManager


class SilaDeviceMixin:
    """Mixin that adds SiLA server management capabilities to EOS devices."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sila_manager: SilaServerManager | None = None

    def sila_add_server(
        self,
        name: str,
        server_class: type,
        port: int = 0,
        bind_ip: str = "0.0.0.0",  # noqa: S104
        advertise_ip: str | None = None,
        insecure: bool = True,
    ) -> None:
        """
        Register a SiLA server to run on this device.

        :param name: Unique identifier for this server
        :param server_class: The generated SiLA Server class
        :param port: Port to bind (0 = auto-assign a free port)
        :param bind_ip: IP to bind on (default: "0.0.0.0" for all interfaces)
        :param advertise_ip: IP clients should connect to (None = auto-detect)
        :param insecure: Use insecure connections (default: True for development)
        """
        if not hasattr(self, "_sila_manager") or self._sila_manager is None:
            self._sila_manager = SilaServerManager()

        self._sila_manager.add_server(
            name=name,
            server_class=server_class,
            port=port,
            bind_ip=bind_ip,
            advertise_ip=advertise_ip,
            insecure=insecure,
        )

    def sila_add_server_connection(
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
        if not hasattr(self, "_sila_manager") or self._sila_manager is None:
            self._sila_manager = SilaServerManager()

        self._sila_manager.add_connection(
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

    async def sila_start_all(self) -> None:
        """Start all registered SiLA servers concurrently."""
        manager = getattr(self, "_sila_manager", None)
        if manager:
            await manager.start_all()

    async def sila_start_server(self, name: str) -> None:
        """
        Start a specific SiLA server by name.

        :param name: Name of the server to start
        """
        manager = getattr(self, "_sila_manager", None)
        if manager:
            await manager.start_server(name)

    async def sila_stop_all(self) -> None:
        """Stop all SiLA servers."""
        manager = getattr(self, "_sila_manager", None)
        if manager:
            await manager.stop_all()

    async def sila_stop_server(self, name: str) -> None:
        """
        Stop a specific SiLA server by name.

        :param name: Name of the server to stop
        """
        manager = getattr(self, "_sila_manager", None)
        if manager:
            await manager.stop_server(name)

    def get_sila_endpoint(self, server_name: str | None = None) -> dict[str, Any]:
        """
        Get SiLA server/connection endpoint for connecting clients.

        :param server_name: Name of the server or connection (optional for single-server devices)
        :return: Dictionary with 'address', 'port', 'insecure' keys
        :raises RuntimeError: If no SiLA servers/connections are configured
        :raises ValueError: If server_name is required but not provided, or server/connection doesn't exist
        """
        manager = getattr(self, "_sila_manager", None)
        if not manager:
            raise RuntimeError("No SiLA servers configured for this device")

        if server_name is not None:
            return manager.get_endpoint(server_name)

        servers = manager.list_servers()
        if len(servers) == 1:
            return manager.get_endpoint(servers[0])
        if len(servers) == 0:
            raise RuntimeError("No SiLA servers registered")
        raise ValueError(f"Device has {len(servers)} SiLA servers. Specify server_name from: {servers}")

    def get_all_sila_endpoints(self) -> dict[str, dict[str, Any]]:
        """
        Get connection endpoints for all SiLA servers and connections on this device.

        :return: Dictionary mapping server/connection names to their endpoint info
        """
        manager = getattr(self, "_sila_manager", None)
        if not manager:
            return {}
        return manager.get_all_endpoints()

    def list_sila_servers(self) -> list[str]:
        """
        List names of all SiLA servers and connections registered on this device.

        :return: List of server and connection names
        """
        manager = getattr(self, "_sila_manager", None)
        if not manager:
            return []
        return manager.list_servers()

    def sila_get_status(self) -> dict[str, Any]:
        """
        Get SiLA status for device reporting.

        :return: Dictionary with 'sila_servers' key containing status of hosted servers and external connections
        """
        manager = getattr(self, "_sila_manager", None)
        if not manager:
            return {"sila_servers": None}
        return {"sila_servers": manager.get_status()}

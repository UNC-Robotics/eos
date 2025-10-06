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
        bind_ip: str | None = None,
        advertise_ip: str | None = None,
        insecure: bool | None = None,
    ) -> None:
        """
        Register a SiLA server to run on this device.

        :param name: Unique identifier for this server
        :param server_class: The generated SiLA Server class
        :param port: Port to bind (0 = auto-assign a free port)
        :param bind_ip: IP to bind on (None = use default from init_parameters)
        :param advertise_ip: IP clients should connect to (None = auto-detect)
        :param insecure: Use insecure connections (None = use default from init_parameters)
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

    async def sila_start_all(self, init_parameters: dict[str, Any] | None = None) -> None:
        """
        Start all registered SiLA servers.

        :param init_parameters: Device init params (can contain sila_bind_ip, sila_insecure, etc.)
        """
        manager = getattr(self, "_sila_manager", None)
        if manager:
            await manager.start_all(init_parameters)

    async def sila_start_server(self, name: str, init_parameters: dict[str, Any] | None = None) -> None:
        """
        Start a specific SiLA server by name.

        :param name: Name of the server to start
        :param init_parameters: Optional device init params
        """
        manager = getattr(self, "_sila_manager", None)
        if manager:
            await manager.start_server(name, init_parameters)

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
        Get SiLA server endpoint for connecting clients.

        :param server_name: Name of the server (optional for single-server devices)
        :return: Dictionary with 'address', 'port', 'insecure' keys
        :raises RuntimeError: If no SiLA servers are configured
        :raises ValueError: If server_name is required but not provided, or server doesn't exist
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
        Get connection endpoints for all SiLA servers on this device.

        :return: Dictionary mapping server names to their endpoint info
        """
        manager = getattr(self, "_sila_manager", None)
        if not manager:
            return {}
        return manager.get_all_endpoints()

    def list_sila_servers(self) -> list[str]:
        """
        List names of all SiLA servers registered on this device.

        :return: List of server names
        """
        manager = getattr(self, "_sila_manager", None)
        if not manager:
            return []
        return manager.list_servers()

    def sila_get_status(self) -> dict[str, Any]:
        """
        Get SiLA status for device reporting.

        :return: Dictionary with 'sila_servers' key containing server status info
        """
        manager = getattr(self, "_sila_manager", None)
        if not manager:
            return {"sila_servers": None}
        return {"sila_servers": manager.get_status()}

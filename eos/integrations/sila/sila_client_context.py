"""Context manager for connecting to SiLA servers from EOS tasks."""

import asyncio
from typing import TypeVar
from contextlib import asynccontextmanager

T = TypeVar("T")


class SilaClientContext:
    """Helper for connecting to SiLA servers hosted in EOS device actors."""

    @staticmethod
    async def _create_client_from_endpoint(endpoint: dict, client_class: type[T]) -> T:
        """
        Create a SiLA client from an endpoint dictionary.

        :param endpoint: Endpoint configuration dict with connection details
        :param client_class: Generated SiLA client class to instantiate
        :return: Connected SiLA client instance
        """
        # Build common kwargs for TLS
        kwargs = {}
        if "root_certs" in endpoint:
            kwargs["root_certs"] = endpoint["root_certs"]
        if "private_key" in endpoint:
            kwargs["private_key"] = endpoint["private_key"]
        if "cert_chain" in endpoint:
            kwargs["cert_chain"] = endpoint["cert_chain"]

        # Add insecure flag
        kwargs["insecure"] = endpoint.get("insecure", False)

        # Determine connection type and create client
        connection_type = endpoint.get("connection_type", "manual")

        if connection_type == "discovery":
            # Use discovery to connect
            if "server_name" in endpoint:
                kwargs["server_name"] = endpoint["server_name"]
            if "server_uuid" in endpoint:
                kwargs["server_uuid"] = endpoint["server_uuid"]
            if "timeout" in endpoint:
                kwargs["timeout"] = endpoint["timeout"]

            # Run discovery in thread to avoid blocking async event loop (discovery can take several seconds)
            return await asyncio.to_thread(client_class.discover, **kwargs)

        # Use manual connection
        return client_class(endpoint["address"], endpoint["port"], **kwargs)

    @staticmethod
    @asynccontextmanager
    async def connect(device, client_class: type[T], server_name: str | None = None) -> T:
        """
        Connect to SiLA server and yield client.

        Works with both RayActorWrapper (from tasks) and SilaDeviceMixin instances (from device._initialize).

        :param device: EOS device wrapper or SilaDeviceMixin instance
        :param client_class: Generated SiLA client class to instantiate
        :param server_name: Name of specific server (optional for single-server devices)
        :return: Connected SiLA client instance
        """
        if hasattr(device, "_sila_manager") or server_name:
            endpoint = device.get_sila_endpoint(server_name)
        else:
            try:
                endpoint = device.get_sila_endpoint()
            except TypeError:
                raise ValueError("Device hosts multiple SiLA servers. Specify server_name parameter.") from None

        client = await SilaClientContext._create_client_from_endpoint(endpoint, client_class)

        try:
            yield client
        finally:
            client.close()

    @staticmethod
    async def create_client(device, client_class: type[T], server_name: str | None = None) -> T:
        """
        Create a SiLA client without context manager for long-running connections.

        Unlike `connect()`, this does NOT automatically close the client.
        Works with both RayActorWrapper (from tasks) and SilaDeviceMixin instances (from device._initialize).

        :param device: EOS device wrapper or SilaDeviceMixin instance
        :param client_class: Generated SiLA client class to instantiate
        :param server_name: Name of specific server (optional for single-server devices)
        :return: Connected SiLA client instance
        """
        if hasattr(device, "_sila_manager") or server_name:
            endpoint = device.get_sila_endpoint(server_name)
        else:
            try:
                endpoint = device.get_sila_endpoint()
            except TypeError:
                raise ValueError("Device hosts multiple SiLA servers. Specify server_name parameter.") from None

        return await SilaClientContext._create_client_from_endpoint(endpoint, client_class)

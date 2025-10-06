"""Context manager for connecting to SiLA servers from EOS tasks."""

from typing import TypeVar
from contextlib import asynccontextmanager

from eos.utils.ray_utils import RayActorWrapper

T = TypeVar("T")


class SilaClientContext:
    """Helper for connecting to SiLA servers hosted in EOS device actors."""

    @staticmethod
    @asynccontextmanager
    async def connect(device: RayActorWrapper, client_class: type[T], server_name: str | None = None) -> T:
        """
        Connect to SiLA server and yield client.

        :param device: EOS device wrapper (from task's devices dict)
        :param client_class: Generated SiLA client class to instantiate
        :param server_name: Name of specific server (optional for single-server devices)
        :return: Connected SiLA client instance
        :raises ValueError: If server_name is required but not provided, or server doesn't exist
        :raises RuntimeError: If device has no SiLA servers configured
        """
        if server_name:
            endpoint = device.get_sila_endpoint(server_name)
        else:
            try:
                endpoint = device.get_sila_endpoint()
            except TypeError:
                raise ValueError("Device hosts multiple SiLA servers. Specify server_name parameter.") from None

        if endpoint.get("insecure", False):
            client = client_class(endpoint["address"], endpoint["port"], insecure=True)
        else:
            kwargs = {}
            if "root_certs" in endpoint:
                kwargs["root_certs"] = endpoint["root_certs"]
            if "private_key" in endpoint:
                kwargs["private_key"] = endpoint["private_key"]
            if "cert_chain" in endpoint:
                kwargs["cert_chain"] = endpoint["cert_chain"]
            client = client_class(endpoint["address"], endpoint["port"], **kwargs)

        try:
            yield client
        finally:
            client.close()

"""Context manager for connecting to SiLA servers from EOS tasks."""

import asyncio
import time
import uuid
from typing import Any, TypeVar
from contextlib import asynccontextmanager

T = TypeVar("T")


class _SilaFeatureWrapper:
    """Wraps SiLA feature to inject lock metadata into commands and properties."""

    def __init__(self, feature, lock_metadata: list):
        """
        Initialize feature wrapper.

        :param feature: The SiLA feature to wrap
        :param lock_metadata: Lock metadata to inject into calls
        """
        self._feature = feature
        self._lock_metadata = lock_metadata

    def __getattr__(self, name):
        """Wrap command/property calls to inject lock metadata."""
        attr = getattr(self._feature, name)

        # If it's callable, wrap it to inject metadata
        if callable(attr):

            def wrapped_call(*args, **kwargs) -> Any:
                # Skip metadata injection for metadata calls (identified by get_affected_calls attribute)
                if hasattr(attr, "get_affected_calls"):
                    return attr(*args, **kwargs)

                if "metadata" in kwargs:
                    # Append to existing metadata
                    kwargs["metadata"] = list(kwargs["metadata"]) + self._lock_metadata
                else:
                    # Add lock metadata
                    kwargs["metadata"] = self._lock_metadata
                return attr(*args, **kwargs)

            return wrapped_call

        # For non-callable attributes (like property objects), wrap them recursively
        # so their methods (like .get()) also get metadata injected
        return _SilaFeatureWrapper(attr, self._lock_metadata)


class _SilaLockedClient:
    """Wraps SiLA client with lock management capabilities."""

    def __init__(self, client):
        """
        Initialize locked client wrapper.

        :param client: The SiLA client to wrap
        """
        self._client = client
        self._lock_identifier: str | None = None

    def lock(self, timeout: int = 60, retry_delay: float = 0.5, max_retries: int = 120) -> None:
        """
        Lock the server with an auto-generated UUID.

        If the server is already locked, retries until it becomes available.

        :param timeout: Lock timeout in seconds (default: 60)
        :param retry_delay: Delay between retry attempts in seconds (default: 0.5)
        :param max_retries: Maximum number of retry attempts (default: 120, ~60s total)
        """
        if self._client.LockController.IsLocked.get():
            return  # Already locked

        self._lock_identifier = str(uuid.uuid4())

        # Try to acquire lock with retries
        for attempt in range(max_retries):
            try:
                self._client.LockController.LockServer(LockIdentifier=self._lock_identifier, Timeout=timeout)
                return
            except Exception as e:
                # Check if it's a ServerAlreadyLocked error and retry if attempts remain
                if "ServerAlreadyLocked" in str(type(e).__name__) and attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                # Re-raise if not ServerAlreadyLocked or max retries reached
                raise

    def unlock(self) -> None:
        """Unlock the server if currently locked."""
        if not self._client.LockController.IsLocked.get():
            return  # Not locked

        try:
            self._client.LockController.UnlockServer(LockIdentifier=self._lock_identifier)
        finally:
            self._lock_identifier = None

    def close(self) -> None:
        """Unlock if locked and close the client."""
        self.unlock()
        self._client.close()

    def __getattr__(self, name):
        """Intercept feature access to inject lock metadata when locked."""
        # Allow direct access to LockController
        if name == "LockController":
            return self._client.LockController

        attr = getattr(self._client, name)

        # If it's a callable method, return as-is
        if callable(attr):
            return attr

        # Wrap features to inject lock metadata if locked
        if self._client.LockController.IsLocked.get():
            lock_metadata = [self._client.LockController.LockIdentifier(self._lock_identifier)]
            return _SilaFeatureWrapper(attr, lock_metadata)

        return attr  # Not locked, no metadata injection


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
            client = await asyncio.to_thread(client_class.discover, **kwargs)
        else:
            # Use manual connection
            client = client_class(endpoint["address"], endpoint["port"], **kwargs)

        # Wrap client if LockController is available
        if hasattr(client, "LockController"):
            client = _SilaLockedClient(client)

        return client

    @staticmethod
    @asynccontextmanager
    async def connect(
        device,
        client_class: type[T],
        server_name: str | None = None,
        lock_timeout: int = 60,
        lock_retry_delay: float = 0.5,
        lock_max_retries: int = 120,
    ) -> T:
        """
        Connect to SiLA server and yield client.

        If the server supports LockController, the client will be automatically locked
        for the duration of the context.

        Works with both RayActorWrapper (from tasks) and SilaDeviceMixin instances (from device._initialize).

        :param device: EOS device wrapper or SilaDeviceMixin instance
        :param client_class: Generated SiLA client class to instantiate
        :param server_name: Name of specific server (optional for single-server devices)
        :param lock_timeout: Lock timeout in seconds for LockController (default: 60),
            only applies if LockController is used
        :param lock_retry_delay: Delay between lock retry attempts in seconds (default: 0.5)
        :param lock_max_retries: Maximum lock retry attempts (default: 120, ~60s total)
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

        # Auto-lock if lock_timeout is specified
        if lock_timeout is not None and hasattr(client, "lock"):
            client.lock(lock_timeout, lock_retry_delay, lock_max_retries)

        try:
            yield client
        finally:
            client.close()  # Will unlock if locked

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

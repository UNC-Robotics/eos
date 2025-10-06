"""
SiLA 2 integration for EOS.

This package provides utilities for running SiLA 2 servers inside EOS device actors
and connecting to them from EOS tasks.
"""

from eos.integrations.sila.sila_client_context import SilaClientContext
from eos.integrations.sila.sila_device_mixin import SilaDeviceMixin
from eos.integrations.sila.sila_server_manager import SilaServerInstance, SilaServerManager

__all__ = [
    "SilaClientContext",
    "SilaDeviceMixin",
    "SilaServerInstance",
    "SilaServerManager",
]

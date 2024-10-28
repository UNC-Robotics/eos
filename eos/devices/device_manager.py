import asyncio
import itertools
from typing import Any

import ray
from ray.actor import ActorHandle

from eos.configuration.configuration_manager import ConfigurationManager
from eos.configuration.constants import EOS_COMPUTER_NAME
from eos.devices.entities.device import Device, DeviceStatus
from eos.devices.exceptions import EosDeviceStateError, EosDeviceInitializationError
from eos.devices.repositories.device_repository import DeviceRepository
from eos.logging.batch_error_logger import batch_error, raise_batched_errors
from eos.logging.logger import log
from eos.persistence.async_mongodb_interface import AsyncMongoDbInterface


class DeviceManager:
    """
    Provides methods for interacting with the devices in a lab.
    """

    def __init__(self, configuration_manager: ConfigurationManager, db_interface: AsyncMongoDbInterface):
        self._configuration_manager = configuration_manager
        self._session_factory = db_interface.session_factory
        self._devices = None

        self._device_plugin_registry = configuration_manager.devices
        self._device_actor_handles: dict[str, ActorHandle] = {}
        self._device_actor_computer_ips: dict[str, str] = {}

    async def initialize(self, db_interface: AsyncMongoDbInterface) -> None:
        self._devices = DeviceRepository(db_interface)
        await self._devices.initialize()

        log.debug("Device manager initialized.")

    async def get_device(self, lab_id: str, device_id: str) -> Device | None:
        """
        Get a device by its lab and device ID.

        :param lab_id: The ID of the lab the device is in.
        :param device_id: The ID of the device in the lab.
        """
        device = await self._devices.get_one(lab_id=lab_id, id=device_id)
        if not device:
            return None
        return Device(**device)

    async def get_devices(self, **query: dict[str, Any]) -> list[Device]:
        """
        Query devices with arbitrary parameters and return a list of matching devices.

        :param query: Dictionary of query parameters.
        """
        devices = await self._devices.get_all(**query)
        return [Device(**device) for device in devices]

    async def set_device_status(self, lab_id: str, device_id: str, status: DeviceStatus) -> None:
        """
        Set the status of a device.
        """
        if not await self._devices.exists(lab_id=lab_id, id=device_id):
            raise EosDeviceStateError(f"Device '{device_id}' in lab '{lab_id}' does not exist.")

        await self._devices.update_one({"status": status.value}, lab_id=lab_id, id=device_id)

    def get_device_actor(self, lab_id: str, device_id: str) -> ActorHandle:
        """
        Get the actor handle of a device.
        """
        actor_id = f"{lab_id}.{device_id}"
        if actor_id not in self._device_actor_handles:
            raise EosDeviceInitializationError(f"Device actor '{actor_id}' does not exist.")

        return self._device_actor_handles.get(actor_id)

    async def update_devices(self, loaded_labs: set[str] | None = None, unloaded_labs: set[str] | None = None) -> None:
        if unloaded_labs:
            await self.cleanup_device_actors(lab_ids=list(unloaded_labs))

        if loaded_labs:
            creation_tasks = [self._create_devices_for_lab(lab_id) for lab_id in loaded_labs]
            await asyncio.gather(*creation_tasks)

        self._check_device_actors_healthy()
        log.debug("Devices have been updated.")

    async def cleanup_device_actors(self, lab_ids: list[str] | None = None) -> None:
        """
        Terminate device actors, optionally for specific labs.

        :param lab_ids: If provided, cleanup devices for these labs.
                        If None, cleanup all devices.
        """
        if lab_ids:
            devices_by_lab = await self._devices.get_devices_by_lab_ids(lab_ids)
            devices_to_remove = list(itertools.chain(*devices_by_lab.values()))
            actor_ids = [Device(**device).get_actor_id() for device in devices_to_remove]
        else:
            actor_ids = list(self._device_actor_handles.keys())

        async def cleanup_device(actor_id: str) -> None:
            if actor_id in self._device_actor_handles:
                await self._device_actor_handles[actor_id].cleanup.remote()
                ray.kill(self._device_actor_handles[actor_id])
                del self._device_actor_handles[actor_id]
                del self._device_actor_computer_ips[actor_id]

        await asyncio.gather(*[cleanup_device(actor_id) for actor_id in actor_ids])

        if lab_ids:
            await self._devices.delete_devices_by_lab_ids(lab_ids)
            log.debug(f"Cleaned up devices for lab(s): {', '.join(lab_ids)}")
        else:
            await self._devices.delete_all()

    async def _create_devices_for_lab(self, lab_id: str) -> None:
        lab_config = self._configuration_manager.labs[lab_id]

        existing_devices = {device["id"]: Device(**device) for device in await self._devices.get_all(lab_id=lab_id)}

        devices_to_upsert: list[Device] = []

        for device_id, device_config in lab_config.devices.items():
            device = existing_devices.get(device_id)

            if device and device.get_actor_id() in self._device_actor_handles:
                continue

            if device and device.actor_handle:
                self._restore_device_actor(device)
            else:
                new_device = Device(
                    lab_id=lab_id,
                    id=device_id,
                    type=device_config.type,
                    location=device_config.location,
                    computer=device_config.computer,
                )
                devices_to_upsert.append(new_device)
                await self._create_device_actor(new_device)

        if devices_to_upsert:
            await self._devices.bulk_upsert([device.model_dump() for device in devices_to_upsert])

        log.debug(f"Updated devices for lab '{lab_id}'")

    def _restore_device_actor(self, device: Device) -> None:
        """
        Restore a device actor registered in the database by looking up its actor in the Ray cluster.
        """
        device_actor_id = device.get_actor_id()
        device_config = self._configuration_manager.labs[device.lab_id].devices[device.id]
        self._device_actor_handles[device_actor_id] = ray.get_actor(device_actor_id)
        self._device_actor_computer_ips[device_actor_id] = (
            self._configuration_manager.labs[device.lab_id].computers[device_config.computer].ip
        )
        log.debug(f"Restored device actor {device_actor_id}")

    async def _create_device_actor(self, device: Device) -> None:
        lab_config = self._configuration_manager.labs[device.lab_id]
        device_config = lab_config.devices[device.id]
        computer_name = device_config.computer.lower()

        computer_ip = "127.0.0.1" if computer_name == EOS_COMPUTER_NAME else lab_config.computers[computer_name].ip

        device_actor_id = device.get_actor_id()
        self._device_actor_computer_ips[device_actor_id] = computer_ip

        spec_initialization_parameters = (
            self._configuration_manager.device_specs.get_spec_by_type(device.type).init_parameters or {}
        )

        device_config_initialization_parameters = device_config.init_parameters or {}

        initialization_parameters: dict[str, Any] = {
            **spec_initialization_parameters,
            **device_config_initialization_parameters,
        }

        resources = (
            {"eos-core": 0.0001} if computer_ip in ["localhost", "127.0.0.1"] else {f"node:{computer_ip}": 0.0001}
        )

        device_class = ray.remote(self._device_plugin_registry.get_plugin_class_type(device.type))
        self._device_actor_handles[device_actor_id] = device_class.options(
            name=device_actor_id,
            num_cpus=0,
            resources=resources,
        ).remote(device.id, device.lab_id, device.type)
        await self._device_actor_handles[device_actor_id].initialize.remote(initialization_parameters)

    def _check_device_actors_healthy(self) -> None:
        status_reports = [actor_handle.get_status.remote() for actor_handle in self._device_actor_handles.values()]
        status_report_to_device_actor_id = {
            status_report: device_actor_id
            for device_actor_id, status_report in zip(self._device_actor_handles.keys(), status_reports, strict=False)
        }

        ready_status_reports, not_ready_status_reports = ray.wait(
            status_reports,
            num_returns=len(self._device_actor_handles),
            timeout=5,
        )

        for not_ready_ref in not_ready_status_reports:
            device_actor_id = status_report_to_device_actor_id[not_ready_ref]
            actor_handle = self._device_actor_handles[device_actor_id]
            computer_ip = self._device_actor_computer_ips[device_actor_id]

            ray.kill(actor_handle)

            batch_error(
                f"Device actor '{device_actor_id}' could not be reached on the computer {computer_ip}",
                EosDeviceInitializationError,
            )
        raise_batched_errors(EosDeviceInitializationError)

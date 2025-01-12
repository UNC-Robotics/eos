from typing import Any

import ray
from ray.actor import ActorHandle
from sqlalchemy import select, update, delete

from eos.configuration.configuration_manager import ConfigurationManager
from eos.configuration.constants import EOS_COMPUTER_NAME
from eos.devices.entities.device import Device, DeviceStatus, DeviceModel
from eos.devices.exceptions import EosDeviceStateError, EosDeviceInitializationError
from eos.logging.batch_error_logger import batch_error, raise_batched_errors
from eos.logging.logger import log

from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.utils.di.di_container import inject_all


class DeviceManager:
    """
    Provides methods for interacting with the devices in a lab.
    """

    @inject_all
    def __init__(self, configuration_manager: ConfigurationManager):
        self._configuration_manager = configuration_manager

        self._device_plugin_registry = configuration_manager.devices
        self._device_actor_handles: dict[str, ActorHandle] = {}
        self._device_actor_computer_ips: dict[str, str] = {}

        log.debug("Device manager initialized.")

    async def get_device(self, db: AsyncDbSession, lab_id: str, device_id: str) -> Device | None:
        """Get a device by its lab and device ID."""
        result = await db.execute(select(DeviceModel).where(DeviceModel.lab_id == lab_id, DeviceModel.id == device_id))
        if device_model := result.scalar_one_or_none():
            return Device.model_validate(device_model)
        return None

    async def get_devices(self, db: AsyncDbSession, **filters: Any) -> list[Device]:
        """Query devices with arbitrary parameters and return matching devices."""
        stmt = select(DeviceModel)
        for key, value in filters.items():
            stmt = stmt.where(getattr(DeviceModel, key) == value)

        result = await db.execute(stmt)
        return [Device.model_validate(model) for model in result.scalars()]

    async def set_device_status(self, db: AsyncDbSession, lab_id: str, device_id: str, status: DeviceStatus) -> None:
        """Set the status of a device."""
        result = await db.execute(
            select(DeviceModel.id).where(DeviceModel.lab_id == lab_id, DeviceModel.id == device_id)
        )
        if not result.scalar_one_or_none():
            raise EosDeviceStateError(f"Device '{device_id}' in lab '{lab_id}' does not exist.")

        await db.execute(
            update(DeviceModel).where(DeviceModel.lab_id == lab_id, DeviceModel.id == device_id).values(status=status)
        )

    def get_device_actor(self, lab_id: str, device_id: str) -> ActorHandle:
        """Get the actor handle of a device."""
        actor_id = f"{lab_id}.{device_id}"
        if actor_handle := self._device_actor_handles.get(actor_id):
            return actor_handle
        raise EosDeviceInitializationError(f"Device actor '{actor_id}' does not exist.")

    async def update_devices(
        self,
        db: AsyncDbSession,
        loaded_labs: set[str] | None = None,
        unloaded_labs: set[str] | None = None,
    ) -> None:
        """Update devices based on the loaded and unloaded labs."""
        if unloaded_labs:
            await self.cleanup_device_actors(db, lab_ids=list(unloaded_labs))

        if loaded_labs:
            for lab_id in loaded_labs:
                await self._create_devices_for_lab(db, lab_id)

        await db.commit()

        self._check_device_actors_healthy()
        log.debug("Devices have been updated.")

    async def cleanup_device_actors(self, db: AsyncDbSession, lab_ids: list[str] | None = None) -> None:
        """Terminate device actors, optionally for specific labs."""
        actor_ids = await self._get_actor_ids_to_cleanup(db, lab_ids)

        for actor_id in actor_ids:
            await self._cleanup_single_device(actor_id)

        await self.cleanup_devices(db, lab_ids)

    async def _get_actor_ids_to_cleanup(self, db: AsyncDbSession, lab_ids: list[str] | None) -> list[str]:
        if not lab_ids:
            return list(self._device_actor_handles.keys())

        result = await db.execute(select(DeviceModel).where(DeviceModel.lab_id.in_(lab_ids)))
        devices = [Device.model_validate(device) for device in result.scalars()]
        return [device.get_actor_id() for device in devices]

    async def _cleanup_single_device(self, actor_id: str) -> None:
        if actor_id not in self._device_actor_handles:
            return

        await self._device_actor_handles[actor_id].cleanup.remote()
        ray.kill(self._device_actor_handles[actor_id])
        del self._device_actor_handles[actor_id]
        del self._device_actor_computer_ips[actor_id]

    async def cleanup_devices(self, db: AsyncDbSession, lab_ids: list[str] | None = None) -> None:
        if lab_ids:
            await db.execute(delete(DeviceModel).where(DeviceModel.lab_id.in_(lab_ids)))
            log.debug(f"Cleaned up devices for lab(s): {', '.join(lab_ids)}")
        else:
            await db.execute(delete(DeviceModel))

    async def _create_devices_for_lab(self, db: AsyncDbSession, lab_id: str) -> None:
        """
        Create or update devices for a specific lab.

        :param db: The database session
        :param lab_id: The lab ID
        """
        lab_config = self._configuration_manager.labs[lab_id]

        # Get existing devices
        stmt = select(DeviceModel).where(DeviceModel.lab_id == lab_id)
        result = await db.execute(stmt)
        existing_devices = {device.id: Device.model_validate(device) for device in result.scalars().all()}

        devices_to_upsert: list[Device] = []

        for device_id, device_config in lab_config.devices.items():
            device = existing_devices.get(device_id)

            if device and device.get_actor_id() in self._device_actor_handles:
                continue

            if device and device.actor_handle:
                self._restore_device_actor(device)
            else:
                new_device = Device(
                    id=device_id,
                    lab_id=lab_id,
                    type=device_config.type,
                    computer=device_config.computer,
                    location=device_config.location,
                )
                devices_to_upsert.append(DeviceModel(**new_device.model_dump()))
                await self._create_device_actor(new_device)

        if devices_to_upsert:
            db.add_all(devices_to_upsert)

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

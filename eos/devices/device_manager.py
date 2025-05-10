import asyncio
import contextlib
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

from eos.database.abstract_sql_db_interface import AsyncDbSession, AbstractSqlDbInterface
from eos.utils.di.di_container import inject


class DeviceManager:
    """
    Provides methods for interacting with devices in a lab.
    """

    @inject
    def __init__(self, configuration_manager: ConfigurationManager, db_interface: AbstractSqlDbInterface) -> None:
        self._configuration_manager = configuration_manager
        self._device_plugin_registry = configuration_manager.devices
        self._db_interface = db_interface
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

        await db.commit()

        if loaded_labs:
            await self._create_devices_for_labs(loaded_labs)

        self._check_device_actors_healthy()
        log.debug("Devices have been updated.")

    async def reload_devices(self, db: AsyncDbSession, lab_id: str, device_ids: list[str]) -> None:
        """Reload specific devices within a lab with updated plugin code.

        This method reloads the device plugin code and then recreates the device actors.

        :param db: The database session
        :param lab_id: The lab ID
        :param device_ids: List of device IDs to reload
        :raises EosDeviceStateError: If any device doesn't exist or the lab isn't loaded
        """
        # Verify lab exists
        if lab_id not in self._configuration_manager.labs:
            raise EosDeviceStateError(f"Lab '{lab_id}' is not loaded.")

        # Verify all devices exist
        for device_id in device_ids:
            if device_id not in self._configuration_manager.labs[lab_id].devices:
                raise EosDeviceStateError(f"Device '{lab_id}.{device_id}' does not exist.")

        # Reload device plugin types first
        device_types_to_reload = set()
        for device_id in device_ids:
            device_type = self._configuration_manager.labs[lab_id].devices[device_id].type
            device_types_to_reload.add(device_type)

        for device_type in device_types_to_reload:
            try:
                self._device_plugin_registry.reload_plugin(device_type)
                log.info(f"Reloaded device plugin code for type '{device_type}'")
            except Exception as e:
                log.error(f"Failed to reload device plugin code for type '{device_type}': {e}")
                raise

        # Cleanup the specific device actors
        reload_tasks = []

        for device_id in device_ids:
            actor_id = f"{lab_id}.{device_id}"
            if actor_id in self._device_actor_handles:
                reload_tasks.append(self._cleanup_single_device(actor_id))

        if reload_tasks:
            await asyncio.gather(*reload_tasks)

        # Remove device records from database
        await db.execute(delete(DeviceModel).where(DeviceModel.lab_id == lab_id, DeviceModel.id.in_(device_ids)))

        # Create new device records and actors
        lab_config = self._configuration_manager.labs[lab_id]
        devices_to_upsert = []
        device_creation_tasks = []

        for device_id in device_ids:
            device_config = lab_config.devices[device_id]
            new_device = Device(
                id=device_id,
                lab_id=lab_id,
                type=device_config.type,
                computer=device_config.computer,
                location=device_config.location,
                meta=device_config.meta,
            )
            devices_to_upsert.append(DeviceModel(**new_device.model_dump()))
            device_creation_tasks.append(self._create_device_actor(new_device))

        if device_creation_tasks:
            await asyncio.gather(*device_creation_tasks)

        if devices_to_upsert:
            db.add_all(devices_to_upsert)

        await db.commit()
        log.info(f"Reloaded devices {device_ids} in lab '{lab_id}'")

    async def _create_devices_for_labs(self, lab_ids: set[str]) -> None:
        """Create devices for multiple labs concurrently."""

        async def process_lab(lab_id: str) -> None:
            async with self._db_interface.get_async_session() as lab_session:
                await self._create_devices_for_lab(lab_session, lab_id)

        tasks = [process_lab(lab_id) for lab_id in lab_ids]
        await asyncio.gather(*tasks)

    async def cleanup_device_actors(self, db: AsyncDbSession, lab_ids: list[str] | None = None) -> None:
        """Terminate device actors concurrently, optionally for specific labs."""
        actor_ids = await self._get_actor_ids_to_cleanup(db, lab_ids)

        if not actor_ids:
            return

        cleanup_tasks = [
            self._cleanup_single_device(actor_id) for actor_id in actor_ids if actor_id in self._device_actor_handles
        ]

        if cleanup_tasks:
            await asyncio.gather(*cleanup_tasks)

        await self.cleanup_devices(db, lab_ids)

    async def _get_actor_ids_to_cleanup(self, db: AsyncDbSession, lab_ids: list[str] | None) -> list[str]:
        """Get actor IDs that need to be cleaned up."""
        if not lab_ids:
            return list(self._device_actor_handles.keys())

        result = await db.execute(select(DeviceModel).where(DeviceModel.lab_id.in_(lab_ids)))
        devices = [Device.model_validate(device) for device in result.scalars()]
        return [device.get_actor_id() for device in devices]

    async def _cleanup_single_device(self, actor_id: str, timeout: float = 30.0) -> None:
        """Clean up a single device actor with timeout.

        Attempts to gracefully clean up a device actor. If the cleanup
        doesn't complete within the timeout, forcefully kills the actor.

        :param actor_id: The ID of the actor to clean up
        :param timeout: Maximum time in seconds to wait for cleanup before force killing
        """
        if actor_id not in self._device_actor_handles:
            return

        actor_handle = self._device_actor_handles[actor_id]
        success = False

        try:
            log.info(f"Cleaning up device actor '{actor_id}'...")
            cleanup_ref = actor_handle.cleanup.remote()

            # Wait for cleanup to complete with timeout
            ready_refs, _ = ray.wait([cleanup_ref], timeout=timeout)

            if cleanup_ref in ready_refs:
                log.info(f"Cleaned up device actor '{actor_id}'")
                success = True
            else:
                log.warning(
                    f"Timed out cleaning up device actor '{actor_id}' after {timeout} seconds, will forcefully kill..."
                )
        except Exception as e:
            log.error(f"Failed cleaning up device actor '{actor_id}': {e}")
        finally:
            # Kill if cleanup wasn't successful
            if not success and actor_id in self._device_actor_handles:
                try:
                    log.warning(f"Forcefully killing device actor '{actor_id}'")
                    ray.kill(self._device_actor_handles[actor_id])
                except Exception as e:
                    log.error(f"Error killing device actor '{actor_id}': {e}")

            # Clean up references regardless of success
            self._remove_device_references(actor_id)

    def _remove_device_references(self, actor_id: str) -> None:
        """Remove device references from internal tracking dictionaries."""
        self._device_actor_handles.pop(actor_id, None)
        self._device_actor_computer_ips.pop(actor_id, None)

    async def cleanup_devices(self, db: AsyncDbSession, lab_ids: list[str] | None = None) -> None:
        """Remove device records from the database."""
        if lab_ids:
            await db.execute(delete(DeviceModel).where(DeviceModel.lab_id.in_(lab_ids)))
            log.debug(f"Cleaned up devices for lab(s): {', '.join(lab_ids)}")
        else:
            await db.execute(delete(DeviceModel))
            log.debug("Cleaned up all devices")

    async def _create_devices_for_lab(self, db: AsyncDbSession, lab_id: str) -> None:
        """Create or update devices for a specific lab.

        :param db: The database session
        :param lab_id: The lab ID
        """
        lab_config = self._configuration_manager.labs[lab_id]

        # Get existing devices
        stmt = select(DeviceModel).where(DeviceModel.lab_id == lab_id)
        result = await db.execute(stmt)
        existing_devices = {device.id: Device.model_validate(device) for device in result.scalars().all()}

        devices_to_upsert: list[DeviceModel] = []
        device_creation_tasks = []

        for device_id, device_config in lab_config.devices.items():
            device = existing_devices.get(device_id)
            actor_id = f"{lab_id}.{device_id}"

            # Skip if device is already active
            if device and actor_id in self._device_actor_handles:
                continue

            # Restore existing actor or create new one
            if device and device.actor_handle:
                self._restore_device_actor(device)
            else:
                # Create new device
                new_device = Device(
                    id=device_id,
                    lab_id=lab_id,
                    type=device_config.type,
                    computer=device_config.computer,
                    location=device_config.location,
                    meta=device_config.meta,
                )
                devices_to_upsert.append(DeviceModel(**new_device.model_dump()))
                device_creation_tasks.append(self._create_device_actor(new_device))

        if device_creation_tasks:
            await asyncio.gather(*device_creation_tasks)

        if devices_to_upsert:
            db.add_all(devices_to_upsert)

        log.debug(f"Updated devices for lab '{lab_id}'")

    def _restore_device_actor(self, device: Device) -> None:
        """Restore a device actor registered in the database by looking up its actor in the Ray cluster."""
        device_actor_id = device.get_actor_id()
        device_config = self._configuration_manager.labs[device.lab_id].devices[device.id]

        try:
            self._device_actor_handles[device_actor_id] = ray.get_actor(device_actor_id)
            self._device_actor_computer_ips[device_actor_id] = (
                self._configuration_manager.labs[device.lab_id].computers[device_config.computer].ip
            )
            log.debug(f"Restored device actor '{device_actor_id}'")
        except Exception as e:
            log.error(f"Failed to restore device actor '{device_actor_id}': {e}")

    async def _create_device_actor(self, device: Device) -> None:
        """Create a Ray actor for a device."""
        device_actor_id = device.get_actor_id()

        try:
            log.info(f"Creating device actor '{device_actor_id}'...")

            lab_config = self._configuration_manager.labs[device.lab_id]
            device_config = lab_config.devices[device.id]
            computer_name = device_config.computer.lower()

            # Determine computer IP
            computer_ip = "127.0.0.1" if computer_name == EOS_COMPUTER_NAME else lab_config.computers[computer_name].ip
            self._device_actor_computer_ips[device_actor_id] = computer_ip

            initialization_parameters = self._get_initialization_parameters(device)

            resources = self._get_actor_resources(computer_ip)
            device_class = ray.remote(self._device_plugin_registry.get_plugin_class_type(device.type))
            self._device_actor_handles[device_actor_id] = device_class.options(
                name=device_actor_id,
                num_cpus=0,
                resources=resources,
            ).remote(device.id, device.lab_id, device.type)

            await self._device_actor_handles[device_actor_id].initialize.remote(initialization_parameters)
            log.info(f"Created device actor '{device_actor_id}'.")
        except Exception as e:
            log.error(f"Failed to create device actor '{device_actor_id}': {e}")

            self._cleanup_failed_actor(device_actor_id)

            batch_error(
                f"Failed to create device actor '{device_actor_id}': {e}",
                EosDeviceInitializationError,
            )

    def _get_initialization_parameters(self, device: Device) -> dict[str, Any]:
        """Get merged initialization parameters for a device.

        :param device: Device object
        :returns: Dictionary of initialization parameters
        """
        device_config = self._configuration_manager.labs[device.lab_id].devices[device.id]

        spec_params = self._configuration_manager.device_specs.get_spec_by_type(device.type).init_parameters or {}
        config_params = device_config.init_parameters or {}

        return {**spec_params, **config_params}

    def _get_actor_resources(self, computer_ip: str) -> dict[str, float]:
        """Get Ray resource requirements for an actor.

        :param computer_ip: IP address of the computer to run on
        :returns: Dictionary of resource requirements
        """
        if computer_ip in ["localhost", "127.0.0.1"]:
            return {"eos": 0.0001}

        return {f"node:{computer_ip}": 0.0001}

    def _cleanup_failed_actor(self, device_actor_id: str) -> None:
        """Clean up a failed actor and its references.

        :param device_actor_id: Actor ID to clean up
        """
        if device_actor_id in self._device_actor_handles:
            with contextlib.suppress(Exception):
                ray.kill(self._device_actor_handles[device_actor_id])

        self._remove_device_references(device_actor_id)

    def _check_device_actors_healthy(self) -> None:
        """Check health of all device actors and kill unresponsive ones.

        :raises EosDeviceInitializationError: If any device actors are unhealthy
        """
        if not self._device_actor_handles:
            return

        # Request status from all device actors
        status_reports = [actor_handle.get_status.remote() for actor_handle in self._device_actor_handles.values()]
        status_report_to_device_actor_id = {
            status_report: device_actor_id
            for device_actor_id, status_report in zip(self._device_actor_handles.keys(), status_reports, strict=True)
        }

        # Wait for status reports with timeout
        ready_status_reports, not_ready_status_reports = ray.wait(
            status_reports,
            num_returns=len(self._device_actor_handles),
            timeout=5,
        )

        # Kill unresponsive actors
        for not_ready_ref in not_ready_status_reports:
            device_actor_id = status_report_to_device_actor_id[not_ready_ref]
            actor_handle = self._device_actor_handles[device_actor_id]
            computer_ip = self._device_actor_computer_ips[device_actor_id]

            with contextlib.suppress(Exception):
                ray.kill(actor_handle)

            self._remove_device_references(device_actor_id)

            batch_error(
                f"Device actor '{device_actor_id}' could not be reached on the computer {computer_ip}",
                EosDeviceInitializationError,
            )

        raise_batched_errors(EosDeviceInitializationError)

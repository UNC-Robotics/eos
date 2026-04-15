import asyncio
import contextlib
from typing import Any

import ray
from ray.actor import ActorHandle
from sqlalchemy import select, update, delete

from eos.configuration.configuration_manager import ConfigurationManager
from eos.configuration.constants import EOS_COMPUTER_NAME
from eos.allocation.entities.device_allocation import DeviceAllocationModel
from eos.devices.entities.device import Device, DeviceStatus, DeviceModel
from eos.devices.exceptions import EosDeviceStateError, EosDeviceInitializationError
from eos.logging.batch_error_logger import BatchErrorLogger
from eos.logging.logger import log

from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.utils.di.di_container import inject


class DeviceManager:
    """
    Provides methods for interacting with devices in a lab.
    """

    @inject
    def __init__(self, configuration_manager: ConfigurationManager) -> None:
        self._configuration_manager = configuration_manager
        self._device_plugin_registry = configuration_manager.devices
        self._device_actor_handles: dict[str, ActorHandle] = {}
        self._device_actor_computer_ips: dict[str, str] = {}
        self._error_collector = BatchErrorLogger()

        log.debug("Device manager initialized.")

    async def get_device(self, db: AsyncDbSession, lab_name: str, device_name: str) -> Device | None:
        """Get a device by its lab and device name."""
        result = await db.execute(
            select(DeviceModel).where(DeviceModel.lab_name == lab_name, DeviceModel.name == device_name)
        )
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

    async def set_device_status(
        self, db: AsyncDbSession, lab_name: str, device_name: str, status: DeviceStatus
    ) -> None:
        """Set the status of a device."""
        result = await db.execute(
            select(DeviceModel.name).where(DeviceModel.lab_name == lab_name, DeviceModel.name == device_name)
        )
        if not result.scalar_one_or_none():
            raise EosDeviceStateError(f"Device '{device_name}' in lab '{lab_name}' does not exist.")

        await db.execute(
            update(DeviceModel)
            .where(DeviceModel.lab_name == lab_name, DeviceModel.name == device_name)
            .values(status=status)
        )

    def get_device_actor(self, lab_name: str, device_name: str) -> ActorHandle:
        """Get the actor handle of a device."""
        actor_name = f"{lab_name}.{device_name}"
        if actor_handle := self._device_actor_handles.get(actor_name):
            return actor_handle
        raise EosDeviceInitializationError(f"Device actor '{actor_name}' does not exist.")

    async def create_devices_for_labs(self, db: AsyncDbSession, lab_names: set[str]) -> None:
        """Create device actors for the given labs, persist to DB, and verify health.

        :raises EosDeviceInitializationError: If any device actors failed to create or are unhealthy
        """
        self._error_collector = BatchErrorLogger()

        for lab_name in lab_names:
            await self._create_devices_for_lab(db, lab_name)

        self._raise_on_errors()

    async def reload_devices(self, db: AsyncDbSession, lab_name: str, device_names: list[str]) -> None:
        """Reload specific devices within a lab with updated plugin code.

        :param db: The database session
        :param lab_name: The lab name
        :param device_names: List of device names to reload
        :raises EosDeviceStateError: If any device doesn't exist or the lab isn't loaded
        """
        if lab_name not in self._configuration_manager.labs:
            raise EosDeviceStateError(f"Lab '{lab_name}' is not loaded.")

        for device_name in device_names:
            if device_name not in self._configuration_manager.labs[lab_name].devices:
                raise EosDeviceStateError(f"Device '{lab_name}.{device_name}' does not exist.")

        # Reload device plugin types
        device_types_to_reload = {
            self._configuration_manager.labs[lab_name].devices[name].type for name in device_names
        }
        for device_type in device_types_to_reload:
            try:
                self._device_plugin_registry.reload_plugin(device_type)
                log.info(f"Reloaded device plugin code for type '{device_type}'")
            except Exception as e:
                log.error(f"Failed to reload device plugin code for type '{device_type}': {e}")
                raise

        # Cleanup existing actors
        actors_to_cleanup = [
            f"{lab_name}.{name}" for name in device_names if f"{lab_name}.{name}" in self._device_actor_handles
        ]
        if actors_to_cleanup:
            await self._cleanup_device_actors_with_timeout(actors_to_cleanup)

        # Remove old device records
        await db.execute(
            delete(DeviceModel).where(DeviceModel.lab_name == lab_name, DeviceModel.name.in_(device_names))
        )

        # Create new actors and persist
        self._error_collector = BatchErrorLogger()
        await self._create_and_persist_devices(db, lab_name, device_names)
        await db.commit()

        self._raise_on_errors()
        log.info(f"Reloaded devices {device_names} in lab '{lab_name}'")

    # --- Cleanup ---

    async def cleanup_device_actors(self, db: AsyncDbSession, lab_names: list[str] | None = None) -> None:
        """Terminate device actors and remove DB records, optionally for specific labs."""
        actor_names = await self._get_actor_names_to_cleanup(db, lab_names)

        if not actor_names:
            return

        actors_to_cleanup = [name for name in actor_names if name in self._device_actor_handles]
        if actors_to_cleanup:
            await self._cleanup_device_actors_with_timeout(actors_to_cleanup)

        await self.cleanup_device_db_records(db, lab_names)

    async def cleanup_device_db_records(self, db: AsyncDbSession, lab_names: list[str] | None = None) -> None:
        """Remove device and allocation records from the database."""
        if lab_names:
            await db.execute(delete(DeviceAllocationModel).where(DeviceAllocationModel.lab_name.in_(lab_names)))
            await db.execute(delete(DeviceModel).where(DeviceModel.lab_name.in_(lab_names)))
            log.debug(f"Cleaned up devices for lab(s): {', '.join(lab_names)}")
        else:
            await db.execute(delete(DeviceAllocationModel))
            await db.execute(delete(DeviceModel))
            log.debug("Cleaned up all devices")

    async def _cleanup_device_actors_with_timeout(self, actor_names: list[str], cleanup_timeout: float = 30.0) -> None:
        """Clean up multiple device actors concurrently with a timeout."""
        cleanup_refs: dict[ray.ObjectRef, str] = {}
        for actor_name in actor_names:
            actor_handle = self._device_actor_handles.get(actor_name)
            if actor_handle is None:
                continue

            try:
                log.info(f"Cleaning up device '{actor_name}'...")
                cleanup_ref = actor_handle.cleanup.remote()
                cleanup_refs[cleanup_ref] = actor_name
            except Exception as e:
                log.error(f"Failed to start cleanup for device '{actor_name}': {e}")
                self._kill_actor(actor_name)

        if not cleanup_refs:
            return

        pending_refs = set(cleanup_refs.keys())
        start_time = asyncio.get_event_loop().time()

        while pending_refs:
            elapsed = asyncio.get_event_loop().time() - start_time
            remaining_timeout = max(0, cleanup_timeout - elapsed)

            if remaining_timeout <= 0:
                break

            ready_refs, _ = ray.wait(
                list(pending_refs),
                num_returns=1,
                timeout=remaining_timeout,
            )

            if not ready_refs:
                break

            for ref in ready_refs:
                pending_refs.discard(ref)
                actor_name = cleanup_refs[ref]
                try:
                    ray.get(ref)
                    log.info(f"Cleaned up device '{actor_name}'")
                    self._kill_actor(actor_name)
                except Exception as e:
                    log.error(f"Cleanup failed for device '{actor_name}': {e}")
                finally:
                    self._remove_device_references(actor_name)

        # Forcefully kill actors that timed out
        if pending_refs:
            timed_out_actors = [cleanup_refs[ref] for ref in pending_refs]
            log.warning(
                f"Timed out cleaning up {len(timed_out_actors)} device(s) after {cleanup_timeout} seconds: "
                f"{', '.join(timed_out_actors)}"
            )
            for ref in pending_refs:
                actor_name = cleanup_refs[ref]
                log.warning(f"Forcefully killing device '{actor_name}'")
                self._kill_actor(actor_name)
                self._remove_device_references(actor_name)

    def _kill_actor(self, actor_name: str) -> None:
        """Kill a device actor to release its Ray name."""
        if actor_name not in self._device_actor_handles:
            return

        try:
            ray.kill(self._device_actor_handles[actor_name])
        except Exception as e:
            log.error(f"Error killing device '{actor_name}': {e}")

    async def _get_actor_names_to_cleanup(self, db: AsyncDbSession, lab_names: list[str] | None) -> list[str]:
        """Get actor names that need to be cleaned up, from both DB records and in-memory handles."""
        if not lab_names:
            return list(self._device_actor_handles.keys())

        actor_names: set[str] = set()

        # From DB records
        result = await db.execute(select(DeviceModel).where(DeviceModel.lab_name.in_(lab_names)))
        for device in result.scalars():
            actor_names.add(Device.model_validate(device).get_actor_name())

        # From in-memory handles (catches orphaned actors not in DB)
        lab_set = set(lab_names)
        for name in self._device_actor_handles:
            if name.partition(".")[0] in lab_set:
                actor_names.add(name)

        return list(actor_names)

    def _remove_device_references(self, actor_name: str) -> None:
        """Remove device references from internal tracking dictionaries."""
        self._device_actor_handles.pop(actor_name, None)
        self._device_actor_computer_ips.pop(actor_name, None)

    # --- Device creation ---

    async def _create_devices_for_lab(self, db: AsyncDbSession, lab_name: str) -> None:
        """Create devices for a specific lab, skipping any that are already active."""
        lab = self._configuration_manager.labs[lab_name]

        # Get existing devices from DB
        result = await db.execute(select(DeviceModel).where(DeviceModel.lab_name == lab_name))
        existing_device_names = {device.name for device in result.scalars().all()}

        # Determine which devices need to be created
        device_names_to_create = [
            name
            for name in lab.devices
            if name not in existing_device_names or f"{lab_name}.{name}" not in self._device_actor_handles
        ]

        if device_names_to_create:
            await self._create_and_persist_devices(db, lab_name, device_names_to_create)

        log.debug(f"Updated devices for lab '{lab_name}'")

    async def _create_and_persist_devices(self, db: AsyncDbSession, lab_name: str, device_names: list[str]) -> None:
        """Create device actors concurrently and persist successful ones to DB."""
        lab = self._configuration_manager.labs[lab_name]
        devices_to_upsert: list[DeviceModel] = []
        creation_tasks = []

        for device_name in device_names:
            lab_device = lab.devices[device_name]
            new_device = Device(
                name=device_name,
                lab_name=lab_name,
                type=lab_device.type,
                computer=lab_device.computer,
                meta=lab_device.meta,
            )
            devices_to_upsert.append(DeviceModel(**new_device.model_dump()))
            creation_tasks.append(self._create_device_actor(new_device))

        if creation_tasks:
            await asyncio.gather(*creation_tasks)

        # Only persist devices whose actors were successfully created
        successful = [
            model for model in devices_to_upsert if f"{model.lab_name}.{model.name}" in self._device_actor_handles
        ]
        if successful:
            db.add_all(successful)

    async def _create_device_actor(self, device: Device) -> None:
        """Create a Ray actor for a device, recovering an existing one if present in the cluster."""
        device_actor_name = device.get_actor_name()

        try:
            lab = self._configuration_manager.labs[device.lab_name]
            lab_device = lab.devices[device.name]
            computer_name = lab_device.computer.lower()
            computer_ip = "127.0.0.1" if computer_name == EOS_COMPUTER_NAME else lab.computers[computer_name].ip

            # Try to recover an existing actor (e.g., after orchestrator restart)
            if self._try_recover_actor(device_actor_name, computer_ip):
                return

            log.info(f"Creating device actor '{device_actor_name}'...")
            self._device_actor_computer_ips[device_actor_name] = computer_ip

            initialization_parameters = self._get_initialization_parameters(device)

            resources = self._get_actor_resources(computer_ip)
            device_class = ray.remote(self._device_plugin_registry.get_plugin_class_type(device.type))
            self._device_actor_handles[device_actor_name] = device_class.options(
                name=device_actor_name,
                num_cpus=0,
                resources=resources,
            ).remote(device.name, device.lab_name, device.type)

            await self._device_actor_handles[device_actor_name].initialize.remote(initialization_parameters)
            log.info(f"Created device actor '{device_actor_name}'.")
        except Exception as e:
            self._cleanup_failed_actor(device_actor_name)

            self._error_collector.batch_error(
                f"Failed to create device actor '{device_actor_name}': {e}",
                EosDeviceInitializationError,
            )

    def _try_recover_actor(self, actor_name: str, computer_ip: str) -> bool:
        """Try to recover an existing actor from the Ray cluster.

        Returns True if the actor was recovered, False if it needs to be created fresh.
        """
        try:
            existing_handle = ray.get_actor(actor_name)
        except ValueError:
            return False

        # Actor exists — check if it's healthy
        try:
            ready, _ = ray.wait([existing_handle.get_status.remote()], timeout=5)
            if ready:
                self._device_actor_handles[actor_name] = existing_handle
                self._device_actor_computer_ips[actor_name] = computer_ip
                log.info(f"Recovered existing device actor '{actor_name}'")
                return True
        except Exception as e:
            log.warning(f"Health check failed for existing device actor '{actor_name}': {e}")

        # Actor exists but is unresponsive — kill it so we can create a fresh one
        log.warning(f"Existing device actor '{actor_name}' is unresponsive, killing it")
        with contextlib.suppress(Exception):
            ray.kill(existing_handle)
        return False

    def _get_initialization_parameters(self, device: Device) -> dict[str, Any]:
        """Get merged initialization parameters for a device."""
        lab_device = self._configuration_manager.labs[device.lab_name].devices[device.name]

        spec_params = self._configuration_manager.device_specs.get_spec_by_type(device.type).init_parameters or {}
        config_params = lab_device.init_parameters or {}

        return {**spec_params, **config_params}

    def _get_actor_resources(self, computer_ip: str) -> dict[str, float]:
        """Get Ray resource requirements for an actor."""
        if computer_ip in ["localhost", "127.0.0.1"]:
            return {"eos": 0.0001}

        return {f"node:{computer_ip}": 0.0001}

    def _cleanup_failed_actor(self, device_actor_name: str) -> None:
        """Clean up a failed actor and its references."""
        if device_actor_name in self._device_actor_handles:
            with contextlib.suppress(Exception):
                ray.kill(self._device_actor_handles[device_actor_name])

        self._remove_device_references(device_actor_name)

    # --- Health checking ---

    def _raise_on_errors(self) -> None:
        """Check health of all device actors and raise any accumulated errors.

        :raises EosDeviceInitializationError: If any device actors failed to create or are unhealthy
        """
        if self._device_actor_handles:
            status_reports = [actor_handle.get_status.remote() for actor_handle in self._device_actor_handles.values()]
            status_report_to_device_actor_name = {
                status_report: device_actor_name
                for device_actor_name, status_report in zip(
                    self._device_actor_handles.keys(), status_reports, strict=True
                )
            }

            _ready_status_reports, not_ready_status_reports = ray.wait(
                status_reports,
                num_returns=len(self._device_actor_handles),
                timeout=5,
            )

            for not_ready_ref in not_ready_status_reports:
                device_actor_name = status_report_to_device_actor_name[not_ready_ref]
                actor_handle = self._device_actor_handles[device_actor_name]
                computer_ip = self._device_actor_computer_ips[device_actor_name]

                with contextlib.suppress(Exception):
                    ray.kill(actor_handle)

                self._remove_device_references(device_actor_name)

                self._error_collector.batch_error(
                    f"Device actor '{device_actor_name}' could not be reached on the computer {computer_ip}",
                    EosDeviceInitializationError,
                )

        # Always raise accumulated errors (from both creation failures and health check failures)
        self._error_collector.raise_batched_errors(EosDeviceInitializationError)

from operator import or_
from typing import Any

from sqlalchemy import delete, select, tuple_

from eos.configuration.configuration_manager import ConfigurationManager
from eos.logging.logger import log

from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.resource_allocation.entities.device_allocation import (
    DeviceAllocation,
    DeviceAllocationModel,
)
from eos.resource_allocation.exceptions import (
    EosDeviceAllocatedError,
    EosDeviceNotFoundError,
)


class DeviceAllocationManager:
    """
    Responsible for allocating devices to "owners".
    An owner may be an experiment task, a human, etc. A device can only be held by one owner at a time.
    """

    def __init__(
        self,
        configuration_manager: ConfigurationManager,
    ):
        self._configuration_manager = configuration_manager
        log.debug("Device allocation manager initialized.")

    async def allocate(
        self, db: AsyncDbSession, lab_id: str, device_id: str, owner: str, experiment_id: str | None = None
    ) -> None:
        """Allocate a device to an owner."""
        if await self.is_allocated(db, lab_id, device_id):
            raise EosDeviceAllocatedError(f"Device '{device_id}' in lab '{lab_id}' is already allocated.")

        device_config = self._get_device_config(lab_id, device_id)
        allocation_model = DeviceAllocationModel(
            id=device_id,
            lab_id=lab_id,
            owner=owner,
            device_type=device_config["type"],
            experiment_id=experiment_id,
        )

        db.add(allocation_model)

    async def bulk_allocate(
        self, db: AsyncDbSession, devices: list[tuple[str, str]], owner: str, experiment_id: str | None = None
    ) -> None:
        """Bulk allocate devices in a single operation."""
        if not devices:
            return

        # Validate all devices exist
        device_configs = []
        for lab_id, device_id in devices:
            device_configs.append(
                {
                    "id": device_id,
                    "lab_id": lab_id,
                    "device_type": self._get_device_config(lab_id, device_id)["type"],
                }
            )

        db.add_all(
            [
                DeviceAllocationModel(
                    id=config["id"],
                    lab_id=config["lab_id"],
                    owner=owner,
                    device_type=config["device_type"],
                    experiment_id=experiment_id,
                )
                for config in device_configs
            ]
        )

    async def deallocate(self, db: AsyncDbSession, lab_id: str, device_id: str) -> bool:
        """Deallocate a device."""
        result = await db.execute(
            delete(DeviceAllocationModel).where(
                DeviceAllocationModel.lab_id == lab_id,
                DeviceAllocationModel.id == device_id,
            )
        )

        if result.rowcount == 0:
            log.warning(f"Device '{device_id}' in lab '{lab_id}' is not allocated. No action taken.")
            return False

        log.debug(f"Deallocated device '{device_id}' in lab '{lab_id}'.")
        return True

    async def is_allocated(self, db: AsyncDbSession, lab_id: str, device_id: str) -> bool:
        """Check if a device is allocated."""
        self._get_device_config(lab_id, device_id)  # Validate device exists
        result = await db.execute(
            select(DeviceAllocationModel.id).where(
                DeviceAllocationModel.lab_id == lab_id,
                DeviceAllocationModel.id == device_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def bulk_check_allocated(self, db: AsyncDbSession, devices: list[tuple[str, str]]) -> set[tuple[str, str]]:
        """
        Check which devices are already allocated.

        :param devices: List of (lab_id, device_id) tuples
        :returns: Set of (lab_id, device_id) tuples that are already allocated
        """
        if not devices:
            return set()

        result = await db.execute(
            select(DeviceAllocationModel.lab_id, DeviceAllocationModel.id).where(
                tuple_(DeviceAllocationModel.lab_id, DeviceAllocationModel.id).in_(devices)
            )
        )

        return set(result.fetchall())

    async def get_allocation(self, db: AsyncDbSession, lab_id: str, device_id: str) -> DeviceAllocation | None:
        """Get the allocation details of a device."""
        self._get_device_config(lab_id, device_id)  # Validate device exists
        result = await db.execute(
            select(DeviceAllocationModel).where(
                DeviceAllocationModel.lab_id == lab_id,
                DeviceAllocationModel.id == device_id,
            )
        )
        if model := result.scalar_one_or_none():
            return DeviceAllocation.model_validate(model)
        return None

    async def get_allocations(self, db: AsyncDbSession, **filters: Any) -> list[DeviceAllocation]:
        """Query allocations with arbitrary parameters."""
        stmt = select(DeviceAllocationModel)
        for key, value in filters.items():
            stmt = stmt.where(getattr(DeviceAllocationModel, key) == value)

        result = await db.execute(stmt)
        return [DeviceAllocation.model_validate(model) for model in result.scalars()]

    async def get_all_unallocated(self, db: AsyncDbSession) -> list[str]:
        """Get all unallocated devices."""
        result = await db.execute(select(DeviceAllocationModel.id))
        allocated_devices = {str(id_) for id_ in result.scalars().all()}

        all_devices = {
            device_id for lab_config in self._configuration_manager.labs.values() for device_id in lab_config.devices
        }

        return list(all_devices - allocated_devices)

    async def bulk_deallocate(self, db: AsyncDbSession, devices: list[tuple[str, str]]) -> None:
        """
        Bulk deallocate devices with a single query.

        :param devices: List of (lab_id, device_id) tuples
        """
        if not devices:
            return

        if len(devices) == 1:
            lab_id, device_id = devices[0]
            await db.execute(
                delete(DeviceAllocationModel).where(
                    DeviceAllocationModel.lab_id == lab_id, DeviceAllocationModel.id == device_id
                )
            )
        else:
            # Multiple devices: use OR conditions
            conditions = [
                (DeviceAllocationModel.lab_id == lab_id) & (DeviceAllocationModel.id == device_id)
                for lab_id, device_id in devices
            ]
            await db.execute(delete(DeviceAllocationModel).where(or_(*conditions)))

    async def deallocate_all(self, db: AsyncDbSession) -> None:
        """Deallocate all devices."""
        result = await db.execute(delete(DeviceAllocationModel))
        log.debug(f"Deallocated all {result.rowcount} devices.")

    async def deallocate_all_by_owner(self, db: AsyncDbSession, owner: str) -> None:
        """Deallocate all devices allocated to an owner."""
        result = await db.execute(delete(DeviceAllocationModel).where(DeviceAllocationModel.owner == owner))

        if result.rowcount == 0:
            log.warning(f"Owner '{owner}' has no devices allocated. No action taken.")
        else:
            log.debug(f"Deallocated {result.rowcount} devices for owner '{owner}'.")

    def _get_device_config(self, lab_id: str, device_id: str) -> dict[str, Any]:
        """Get device configuration from the configuration manager."""
        lab = self._configuration_manager.labs.get(lab_id)
        if not lab:
            raise EosDeviceNotFoundError(f"Lab '{lab_id}' not found in the configuration.")

        if device_config := lab.devices.get(device_id):
            return {
                "lab_id": lab.type,
                "type": device_config.type,
            }

        raise EosDeviceNotFoundError(f"Device '{device_id}' in lab '{lab_id}' not found in the configuration.")

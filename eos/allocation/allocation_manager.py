from typing import Any

from sqlalchemy import select, delete, update, desc, or_

from eos.configuration.configuration_manager import ConfigurationManager
from eos.logging.logger import log
from eos.database.abstract_sql_db_interface import AsyncDbSession, AbstractSqlDbInterface
from eos.allocation.entities.device_allocation import DeviceAllocation, DeviceAllocationModel
from eos.allocation.entities.resource_allocation import ResourceAllocation, ResourceAllocationModel
from eos.allocation.entities.reservation import Reservation, ReservationModel, ReservationStatus
from eos.allocation.exceptions import (
    EosDeviceNotFoundError,
    EosResourceNotFoundError,
)
from eos.utils.di.di_container import inject


class AllocationManager:
    """Write-through cache for device/resource allocations and manual reservations."""

    @inject
    def __init__(
        self,
        configuration_manager: ConfigurationManager,
        db_interface: AbstractSqlDbInterface,
    ):
        self._configuration_manager = configuration_manager
        self._db_interface = db_interface
        self._device_allocations: dict[tuple[str, str], DeviceAllocation] = {}
        self._resource_allocations: dict[str, ResourceAllocation] = {}

    async def initialize(self, db: AsyncDbSession) -> None:
        await db.execute(delete(DeviceAllocationModel))
        await db.execute(delete(ResourceAllocationModel))
        self._device_allocations.clear()
        self._resource_allocations.clear()
        log.debug("Allocation manager initialized.")

    def is_device_allocated(self, lab_name: str, device_name: str) -> bool:
        return (lab_name, device_name) in self._device_allocations

    def get_device_allocation(self, lab_name: str, device_name: str) -> DeviceAllocation | None:
        return self._device_allocations.get((lab_name, device_name))

    def is_resource_allocated(self, resource_name: str) -> bool:
        return resource_name in self._resource_allocations

    def get_resource_allocation(self, resource_name: str) -> ResourceAllocation | None:
        return self._resource_allocations.get(resource_name)

    def get_all_unallocated_devices(self) -> list[tuple[str, str]]:
        all_devices = {
            (lab_name, device_name)
            for lab_name, lab in self._configuration_manager.labs.items()
            for device_name in lab.devices
        }
        return list(all_devices - set(self._device_allocations.keys()))

    def get_all_unallocated_resources(self) -> list[str]:
        all_resources = {
            resource_name for lab in self._configuration_manager.labs.values() for resource_name in lab.resources
        }
        return list(all_resources - set(self._resource_allocations.keys()))

    async def allocate_devices(
        self, db: AsyncDbSession, devices: list[tuple[str, str]], owner: str, protocol_run_name: str | None = None
    ) -> None:
        if not devices:
            return

        allocations = []
        for lab_name, device_name in devices:
            self._validate_device_exists(lab_name, device_name)
            allocations.append(
                DeviceAllocation(name=device_name, lab_name=lab_name, owner=owner, protocol_run_name=protocol_run_name)
            )

        if len(devices) == 1:
            lab_name, device_name = devices[0]
            await db.execute(
                delete(DeviceAllocationModel).where(
                    DeviceAllocationModel.lab_name == lab_name, DeviceAllocationModel.name == device_name
                )
            )
        else:
            conditions = [
                (DeviceAllocationModel.lab_name == lab) & (DeviceAllocationModel.name == dev) for lab, dev in devices
            ]
            await db.execute(delete(DeviceAllocationModel).where(or_(*conditions)))
        await db.flush()

        db.add_all([DeviceAllocationModel(**a.model_dump(exclude={"created_at"})) for a in allocations])
        await db.flush()
        for alloc in allocations:
            self._device_allocations[(alloc.lab_name, alloc.name)] = alloc

    async def allocate_resources(
        self, db: AsyncDbSession, resource_names: list[str], owner: str, protocol_run_name: str | None = None
    ) -> None:
        if not resource_names:
            return

        allocations = []
        for name in resource_names:
            self._validate_resource_exists(name)
            allocations.append(ResourceAllocation(name=name, owner=owner, protocol_run_name=protocol_run_name))

        await db.execute(delete(ResourceAllocationModel).where(ResourceAllocationModel.name.in_(resource_names)))
        db.add_all([ResourceAllocationModel(**a.model_dump(exclude={"created_at"})) for a in allocations])
        await db.flush()
        for alloc in allocations:
            self._resource_allocations[alloc.name] = alloc

    async def deallocate_devices(self, db: AsyncDbSession, devices: list[tuple[str, str]]) -> None:
        if not devices:
            return

        if len(devices) == 1:
            lab_name, device_name = devices[0]
            await db.execute(
                delete(DeviceAllocationModel).where(
                    DeviceAllocationModel.lab_name == lab_name, DeviceAllocationModel.name == device_name
                )
            )
        else:
            conditions = [
                (DeviceAllocationModel.lab_name == lab) & (DeviceAllocationModel.name == dev) for lab, dev in devices
            ]
            await db.execute(delete(DeviceAllocationModel).where(or_(*conditions)))

        for lab_name, device_name in devices:
            self._device_allocations.pop((lab_name, device_name), None)

    async def deallocate_resources(self, db: AsyncDbSession, resource_names: list[str]) -> None:
        if not resource_names:
            return
        await db.execute(delete(ResourceAllocationModel).where(ResourceAllocationModel.name.in_(resource_names)))
        for name in resource_names:
            self._resource_allocations.pop(name, None)

    async def mark_devices_held(self, db: AsyncDbSession, devices: list[tuple[str, str]], held: bool = True) -> None:
        if not devices:
            return

        if len(devices) == 1:
            lab_name, device_name = devices[0]
            await db.execute(
                update(DeviceAllocationModel)
                .where(DeviceAllocationModel.lab_name == lab_name, DeviceAllocationModel.name == device_name)
                .values(held=held)
            )
        else:
            conditions = [
                (DeviceAllocationModel.lab_name == lab) & (DeviceAllocationModel.name == dev) for lab, dev in devices
            ]
            await db.execute(update(DeviceAllocationModel).where(or_(*conditions)).values(held=held))

        for lab_name, device_name in devices:
            alloc = self._device_allocations.get((lab_name, device_name))
            if alloc:
                alloc.held = held

    async def mark_resources_held(self, db: AsyncDbSession, resource_names: list[str], held: bool = True) -> None:
        if not resource_names:
            return

        await db.execute(
            update(ResourceAllocationModel).where(ResourceAllocationModel.name.in_(resource_names)).values(held=held)
        )
        for name in resource_names:
            alloc = self._resource_allocations.get(name)
            if alloc:
                alloc.held = held

    async def deallocate_all_by_owner(self, db: AsyncDbSession, owner: str) -> None:
        await db.execute(delete(DeviceAllocationModel).where(DeviceAllocationModel.owner == owner))
        await db.execute(delete(ResourceAllocationModel).where(ResourceAllocationModel.owner == owner))
        self._device_allocations = {k: v for k, v in self._device_allocations.items() if v.owner != owner}
        self._resource_allocations = {k: v for k, v in self._resource_allocations.items() if v.owner != owner}

    async def get_device_allocations(self, db: AsyncDbSession, **filters: Any) -> list[DeviceAllocation]:
        stmt = select(DeviceAllocationModel)
        for key, value in filters.items():
            stmt = stmt.where(getattr(DeviceAllocationModel, key) == value)
        result = await db.execute(stmt)
        return [DeviceAllocation.model_validate(m) for m in result.scalars()]

    async def get_resource_allocations(self, db: AsyncDbSession, **filters: Any) -> list[ResourceAllocation]:
        stmt = select(ResourceAllocationModel)
        for key, value in filters.items():
            stmt = stmt.where(getattr(ResourceAllocationModel, key) == value)
        result = await db.execute(stmt)
        return [ResourceAllocation.model_validate(m) for m in result.scalars()]

    async def request_reservation(
        self,
        db: AsyncDbSession,
        devices: list[tuple[str, str]],
        resources: list[str],
        owner: str,
        priority: int = 100,
    ) -> Reservation:
        """Request a manual reservation. Grants immediately if all items are free."""
        for lab_name, device_name in devices:
            self._validate_device_exists(lab_name, device_name)
        for resource_name in resources:
            self._validate_resource_exists(resource_name)

        all_free = all(not self.is_device_allocated(lab, dev) for lab, dev in devices) and all(
            not self.is_resource_allocated(r) for r in resources
        )

        if all_free:
            await self.allocate_devices(db, devices, owner)
            await self.allocate_resources(db, resources, owner)
            model = ReservationModel(
                owner=owner,
                priority=priority,
                status=ReservationStatus.GRANTED,
                devices=[[lab, dev] for lab, dev in devices],
                resources=resources,
            )
            db.add(model)
            await db.flush()
            await db.refresh(model)
            return Reservation(
                id=model.id,
                owner=owner,
                priority=priority,
                status=ReservationStatus.GRANTED,
                devices=devices,
                resources=resources,
            )

        model = ReservationModel(
            owner=owner,
            priority=priority,
            status=ReservationStatus.PENDING,
            devices=[[lab, dev] for lab, dev in devices],
            resources=resources,
        )
        db.add(model)
        await db.flush()
        await db.refresh(model)
        return Reservation(
            id=model.id,
            owner=owner,
            priority=priority,
            status=ReservationStatus.PENDING,
            devices=devices,
            resources=resources,
        )

    async def cancel_reservation(self, db: AsyncDbSession, reservation_id: int) -> None:
        """Cancel a reservation and release any granted allocations."""
        result = await db.execute(select(ReservationModel).where(ReservationModel.id == reservation_id))
        model = result.scalar_one_or_none()
        if not model:
            return

        if model.status == ReservationStatus.GRANTED:
            devices = [(d[0], d[1]) for d in model.devices]
            await self.deallocate_devices(db, devices)
            await self.deallocate_resources(db, model.resources)

        await db.execute(
            update(ReservationModel)
            .where(ReservationModel.id == reservation_id)
            .values(status=ReservationStatus.CANCELLED)
        )

    async def process_reservations(self, db: AsyncDbSession) -> None:
        """Try to grant pending reservations in priority order."""
        result = await db.execute(
            select(ReservationModel)
            .where(ReservationModel.status == ReservationStatus.PENDING)
            .order_by(desc(ReservationModel.priority), ReservationModel.created_at)
        )

        for model in result.scalars():
            devices = [(d[0], d[1]) for d in model.devices]
            resources = model.resources

            all_free = all(not self.is_device_allocated(lab, dev) for lab, dev in devices) and all(
                not self.is_resource_allocated(r) for r in resources
            )

            if all_free:
                await self.allocate_devices(db, devices, model.owner)
                await self.allocate_resources(db, resources, model.owner)
                await db.execute(
                    update(ReservationModel)
                    .where(ReservationModel.id == model.id)
                    .values(status=ReservationStatus.GRANTED)
                )
                log.info(f"Granted reservation {model.id} for '{model.owner}'.")

    async def get_pending_reservations(self, db: AsyncDbSession) -> list[Reservation]:
        result = await db.execute(select(ReservationModel).where(ReservationModel.status == ReservationStatus.PENDING))
        return [
            Reservation(
                id=m.id,
                owner=m.owner,
                priority=m.priority,
                status=m.status,
                devices=[(d[0], d[1]) for d in m.devices],
                resources=m.resources,
                created_at=m.created_at,
            )
            for m in result.scalars()
        ]

    def _validate_device_exists(self, lab_name: str, device_name: str) -> None:
        if not (lab := self._configuration_manager.labs.get(lab_name)):
            raise EosDeviceNotFoundError(f"Lab '{lab_name}' not found.")
        if device_name not in lab.devices:
            raise EosDeviceNotFoundError(f"Device '{device_name}' in lab '{lab_name}' not found.")

    def _validate_resource_exists(self, resource_name: str) -> None:
        for lab in self._configuration_manager.labs.values():
            if resource_name in lab.resources:
                return
        raise EosResourceNotFoundError(f"Resource '{resource_name}' not found.")

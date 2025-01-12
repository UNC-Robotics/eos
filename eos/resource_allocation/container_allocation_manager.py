from typing import Any

from sqlalchemy import delete, select

from eos.configuration.configuration_manager import ConfigurationManager
from eos.logging.logger import log
from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.resource_allocation.entities.container_allocation import (
    ContainerAllocation,
    ContainerAllocationModel,
)
from eos.resource_allocation.exceptions import (
    EosContainerAllocatedError,
    EosContainerNotFoundError,
)


class ContainerAllocationManager:
    """
    Responsible for allocating containers to "owners".
    An owner may be an experiment task, a human, etc. A container can only be held by one owner at a time.
    """

    def __init__(
        self,
        configuration_manager: ConfigurationManager,
    ):
        self._configuration_manager = configuration_manager
        log.debug("Container allocation manager initialized.")

    async def allocate(
        self, db: AsyncDbSession, container_id: str, owner: str, experiment_id: str | None = None
    ) -> None:
        """Allocate a container to an owner."""
        if await self.is_allocated(db, container_id):
            raise EosContainerAllocatedError(f"Container '{container_id}' is already allocated.")

        container_config = self._get_container_config(container_id)
        allocation_model = ContainerAllocationModel(
            id=container_id,
            owner=owner,
            container_type=container_config["type"],
            experiment_id=experiment_id,
        )

        db.add(allocation_model)
        log.debug(f"Allocated container '{container_id}' to owner '{owner}'.")

    async def bulk_allocate(
        self, db: AsyncDbSession, container_ids: list[str], owner: str, experiment_id: str | None = None
    ) -> None:
        """Bulk allocate containers in a single operation."""
        if not container_ids:
            return

        # Validate all containers exist
        container_configs = []
        for container_id in container_ids:
            container_configs.append({"id": container_id, "type": self._get_container_config(container_id)["type"]})

        # Bulk insert all allocations
        db.add_all(
            [
                ContainerAllocationModel(
                    id=config["id"], owner=owner, container_type=config["type"], experiment_id=experiment_id
                )
                for config in container_configs
            ]
        )

    async def deallocate(self, db: AsyncDbSession, container_id: str) -> bool:
        """
        Deallocate a container.
        Returns True if container was deallocated, False if it wasn't allocated.
        """
        result = await db.execute(delete(ContainerAllocationModel).where(ContainerAllocationModel.id == container_id))

        if result.rowcount == 0:
            log.warning(f"Container '{container_id}' is not allocated. No action taken.")
            return False

        log.debug(f"Deallocated container '{container_id}'.")
        return True

    async def is_allocated(self, db: AsyncDbSession, container_id: str) -> bool:
        """Check if a container is allocated."""
        self._get_container_config(container_id)  # Validate container exists
        result = await db.execute(
            select(ContainerAllocationModel.id).where(ContainerAllocationModel.id == container_id)
        )
        return result.scalar_one_or_none() is not None

    async def bulk_check_allocated(self, db: AsyncDbSession, container_ids: list[str]) -> set[str]:
        """
        Check which containers are already allocated.

        :param container_ids: List of container IDs to check
        :returns: Set of container IDs that are already allocated
        """
        if not container_ids:
            return set()

        result = await db.execute(
            select(ContainerAllocationModel.id).where(ContainerAllocationModel.id.in_(container_ids))
        )
        return {str(id_) for id_ in result.scalars()}

    async def get_allocation(self, db: AsyncDbSession, container_id: str) -> ContainerAllocation | None:
        """Get the allocation details of a container."""
        self._get_container_config(container_id)  # Validate container exists
        result = await db.execute(select(ContainerAllocationModel).where(ContainerAllocationModel.id == container_id))
        if model := result.scalar_one_or_none():
            return ContainerAllocation.model_validate(model)
        return None

    async def get_allocations(self, db: AsyncDbSession, **filters: Any) -> list[ContainerAllocation]:
        """Query allocations with arbitrary parameters."""
        stmt = select(ContainerAllocationModel)
        for key, value in filters.items():
            stmt = stmt.where(getattr(ContainerAllocationModel, key) == value)

        result = await db.execute(stmt)
        return [ContainerAllocation.model_validate(model) for model in result.scalars()]

    async def get_all_unallocated(self, db: AsyncDbSession) -> list[str]:
        """Get all unallocated containers."""
        result = await db.execute(select(ContainerAllocationModel.id))
        allocated_containers = {str(id_) for id_ in result.scalars().all()}

        all_containers = {
            container_id
            for lab_config in self._configuration_manager.labs.values()
            for container_config in lab_config.containers
            for container_id in container_config.ids
        }

        return list(all_containers - allocated_containers)

    async def bulk_deallocate(self, db: AsyncDbSession, container_ids: list[str]) -> None:
        """
        Bulk deallocate containers with a single query.

        :param container_ids: List of container IDs to deallocate
        """
        if not container_ids:
            return

        await db.execute(delete(ContainerAllocationModel).where(ContainerAllocationModel.id.in_(container_ids)))

    async def deallocate_all(self, db: AsyncDbSession) -> None:
        """Deallocate all containers."""
        result = await db.execute(delete(ContainerAllocationModel))
        log.debug(f"Deallocated all {result.rowcount} containers.")

    async def deallocate_all_by_owner(self, db: AsyncDbSession, owner: str) -> None:
        """Deallocate all containers allocated to an owner."""
        result = await db.execute(delete(ContainerAllocationModel).where(ContainerAllocationModel.owner == owner))

        if result.rowcount == 0:
            log.warning(f"Owner '{owner}' has no containers allocated. No action taken.")
        else:
            log.debug(f"Deallocated {result.rowcount} containers for owner '{owner}'.")

    def _get_container_config(self, container_id: str) -> dict:
        for lab_config in self._configuration_manager.labs.values():
            for container_config in lab_config.containers:
                if container_id in container_config.ids:
                    return {
                        "type": container_config.type,
                        "lab": lab_config.type,
                    }

        raise EosContainerNotFoundError(f"Container '{container_id}' not found in the configuration.")

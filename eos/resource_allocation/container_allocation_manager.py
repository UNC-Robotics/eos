from typing import Any

from eos.configuration.configuration_manager import ConfigurationManager
from eos.logging.logger import log
from eos.persistence.db_manager import DbManager
from eos.persistence.mongo_repository import MongoRepository
from eos.resource_allocation.entities.container_allocation import (
    ContainerAllocation,
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
        db_manager: DbManager,
    ):
        self._configuration_manager = configuration_manager
        self._allocations = MongoRepository("container_allocations", db_manager)
        self._allocations.create_indices([("id", 1)], unique=True)

        log.debug("Container allocator initialized.")

    def allocate(self, container_id: str, owner: str, experiment_id: str | None = None) -> None:
        """
        Allocate a container to an owner.
        """
        if self.is_allocated(container_id):
            raise EosContainerAllocatedError(f"Container '{container_id}' is already allocated.")

        container_config = self._get_container_config(container_id)
        allocation = ContainerAllocation(
            id=container_id,
            owner=owner,
            container_type=container_config["type"],
            lab=container_config["lab"],
            experiment_id=experiment_id,
        )
        self._allocations.create(allocation.model_dump())

    def deallocate(self, container_id: str) -> None:
        """
        Deallocate a container.
        """
        result = self._allocations.delete(id=container_id)
        if result.deleted_count == 0:
            log.warning(f"Container '{container_id}' is not allocated. No action taken.")
        else:
            log.debug(f"Deallocated container '{container_id}'.")

    def is_allocated(self, container_id: str) -> bool:
        """
        Check if a container is allocated.
        """
        self._get_container_config(container_id)
        return self._allocations.get_one(id=container_id) is not None

    def get_allocation(self, container_id: str) -> ContainerAllocation | None:
        """
        Get the allocation details of a container.
        """
        self._get_container_config(container_id)
        allocation = self._allocations.get_one(id=container_id)
        return ContainerAllocation(**allocation) if allocation else None

    def get_allocations(self, **query: dict[str, Any]) -> list[ContainerAllocation]:
        """
        Query allocations with arbitrary parameters.
        """
        allocations = self._allocations.get_all(**query)
        return [ContainerAllocation(**allocation) for allocation in allocations]

    def get_all_unallocated(self) -> list[str]:
        """
        Get all unallocated containers.
        """
        allocated_containers = [allocation.id for allocation in self.get_allocations()]
        all_containers = [
            container_id
            for lab_config in self._configuration_manager.labs.values()
            for container_config in lab_config.containers
            for container_id in container_config.ids
        ]
        return list(set(all_containers) - set(allocated_containers))

    def deallocate_all(self) -> None:
        """
        Deallocate all containers.
        """
        result = self._allocations.delete()
        log.debug(f"Deallocated all {result.deleted_count} containers.")

    def deallocate_all_by_owner(self, owner: str) -> None:
        """
        Deallocate all containers allocated to an owner.
        """
        result = self._allocations.delete(owner=owner)
        if result.deleted_count == 0:
            log.warning(f"Owner '{owner}' has no containers allocated. No action taken.")
        else:
            log.debug(f"Deallocated {result.deleted_count} containers for owner '{owner}'.")

    def _get_container_config(self, container_id: str) -> dict:
        for lab_config in self._configuration_manager.labs.values():
            for container_config in lab_config.containers:
                if container_id in container_config.ids:
                    return {
                        "type": container_config.type,
                        "lab": lab_config.type,
                    }

        raise EosContainerNotFoundError(f"Container '{container_id}' not found in the configuration.")
import asyncio
from collections import defaultdict
from typing import Any

from sqlalchemy import select, delete, exists, update

from eos.configuration.configuration_manager import ConfigurationManager
from eos.containers.entities.container import Container, ContainerModel
from eos.containers.exceptions import EosContainerStateError
from eos.logging.logger import log

from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.utils.async_rlock import AsyncRLock
from eos.utils.di.di_container import inject_all


class ContainerManager:
    """
    The container manager provides methods for interacting with containers in a lab.
    """

    @inject_all
    def __init__(self, configuration_manager: ConfigurationManager):
        self._configuration_manager = configuration_manager
        self._locks = defaultdict(AsyncRLock)

    async def initialize(self, db: AsyncDbSession) -> None:
        """Initialize the container manager and create initial containers."""
        await self._create_containers(db)
        log.debug("Container manager initialized.")

    async def _check_container_exists(self, db: AsyncDbSession, container_id: str) -> bool:
        """Check if a container exists."""
        result = await db.execute(select(exists().where(ContainerModel.id == container_id)))
        return result.scalar()

    async def get_container(self, db: AsyncDbSession, container_id: str) -> Container:
        """
        Get a container with the specified ID.

        :param db: The database session
        :param container_id: The ID of the container to retrieve
        :return: The container
        :raises EosContainerStateError: If the container doesn't exist
        """
        result = await db.execute(select(ContainerModel).where(ContainerModel.id == container_id))
        if container_model := result.scalar_one_or_none():
            return Container.model_validate(container_model)

        raise EosContainerStateError(f"Container '{container_id}' does not exist.")

    async def get_containers(self, db: AsyncDbSession, **filters: Any) -> list[Container]:
        """
        Query containers with arbitrary parameters.

        :param db: The database session
        :param filters: Dictionary of query parameters
        :return: List of matching containers
        """
        stmt = select(ContainerModel)
        for key, value in filters.items():
            stmt = stmt.where(getattr(ContainerModel, key) == value)

        result = await db.execute(stmt)
        return [Container.model_validate(model) for model in result.scalars()]

    async def set_location(self, db: AsyncDbSession, container_id: str, location: str) -> None:
        """
        Set the location of a container.

        :param db: The database session
        :param container_id: The ID of the container
        :param location: The new location
        :raises EosContainerStateError: If the container doesn't exist
        """
        async with self._get_lock(container_id):
            if not await self._check_container_exists(db, container_id):
                raise EosContainerStateError(f"Container '{container_id}' does not exist.")

            await db.execute(update(ContainerModel).where(ContainerModel.id == container_id).values(location=location))

    async def set_lab(self, db: AsyncDbSession, container_id: str, lab: str) -> None:
        """
        Set the lab of a container.

        :param db: The database session
        :param container_id: The ID of the container
        :param lab: The new lab
        :raises EosContainerStateError: If the container doesn't exist
        """
        async with self._get_lock(container_id):
            if not await self._check_container_exists(db, container_id):
                raise EosContainerStateError(f"Container '{container_id}' does not exist.")

            await db.execute(update(ContainerModel).where(ContainerModel.id == container_id).values(lab=lab))

    async def set_meta(self, db: AsyncDbSession, container_id: str, meta: dict[str, Any]) -> None:
        """
        Set metadata for a container.

        :param db: The database session
        :param container_id: The ID of the container
        :param meta: The new metadata dictionary
        :raises EosContainerStateError: If the container doesn't exist
        """
        async with self._get_lock(container_id):
            if not await self._check_container_exists(db, container_id):
                raise EosContainerStateError(f"Container '{container_id}' does not exist.")

            await db.execute(update(ContainerModel).where(ContainerModel.id == container_id).values(meta=meta))

    async def add_meta(self, db: AsyncDbSession, container_id: str, meta: dict[str, Any]) -> None:
        """
        Add metadata to a container.

        :param db: The database session
        :param container_id: The ID of the container
        :param meta: The metadata to add
        :raises EosContainerStateError: If the container doesn't exist
        """
        async with self._get_lock(container_id):
            container = await self.get_container(db, container_id)
            container.meta.update(meta)

            await db.execute(
                update(ContainerModel).where(ContainerModel.id == container_id).values(meta=container.meta)
            )

    async def remove_meta(self, db: AsyncDbSession, container_id: str, meta_keys: list[str]) -> None:
        """
        Remove metadata from a container.

        :param db: The database session
        :param container_id: The ID of the container
        :param meta_keys: List of metadata keys to remove
        :raises EosContainerStateError: If the container doesn't exist
        """
        async with self._get_lock(container_id):
            container = await self.get_container(db, container_id)
            for key in meta_keys:
                container.meta.pop(key, None)

            await db.execute(
                update(ContainerModel).where(ContainerModel.id == container_id).values(meta=container.meta)
            )

    async def update_container(self, db: AsyncDbSession, container: Container) -> None:
        """
        Update a container in the database.

        :param db: The database session
        :param container: The container to update
        :raises EosContainerStateError: If the container doesn't exist
        """
        if not await self._check_container_exists(db, container.id):
            raise EosContainerStateError(f"Container '{container.id}' does not exist.")

        container_data = container.model_dump()
        await db.execute(update(ContainerModel).where(ContainerModel.id == container.id).values(**container_data))

    async def update_containers(
        self, db: AsyncDbSession, loaded_labs: set[str] | None = None, unloaded_labs: set[str] | None = None
    ) -> None:
        """
        Update containers based on loaded and unloaded labs.

        :param db: The database session
        :param loaded_labs: Set of lab IDs that were loaded
        :param unloaded_labs: Set of lab IDs that were unloaded
        """
        if unloaded_labs:
            await self._remove_containers_for_labs(db, unloaded_labs)

        if loaded_labs:
            await asyncio.gather(*[self._create_containers_for_lab(db, lab_id) for lab_id in loaded_labs])

        log.debug("Containers have been updated.")

    async def _remove_containers_for_labs(self, db: AsyncDbSession, lab_ids: set[str]) -> None:
        """Remove containers associated with unloaded labs."""
        await db.execute(delete(ContainerModel).where(ContainerModel.lab.in_(lab_ids)))
        log.debug(f"Removed containers for labs: {', '.join(lab_ids)}")

    async def _create_containers_for_lab(self, db: AsyncDbSession, lab_id: str) -> None:
        """Create containers for a loaded lab."""
        lab_config = self._configuration_manager.labs[lab_id]
        containers_to_add = []

        for container_config in lab_config.containers:
            for container_id in container_config.ids:
                if not await self._check_container_exists(db, container_id):
                    container = Container(
                        id=container_id,
                        type=container_config.type,
                        lab=lab_id,
                        location=container_config.location,
                        meta=container_config.meta,
                    )
                    containers_to_add.append(ContainerModel(**container.model_dump()))

        if containers_to_add:
            db.add_all(containers_to_add)

        log.debug(f"Created containers for lab '{lab_id}'")

    async def _create_containers(self, db: AsyncDbSession) -> None:
        """Create containers from the lab configuration."""
        containers_to_add = []

        for lab_name, lab_config in self._configuration_manager.labs.items():
            for container_config in lab_config.containers:
                for container_id in container_config.ids:
                    container = Container(
                        id=container_id,
                        type=container_config.type,
                        lab=lab_name,
                        location=container_config.location,
                        meta=container_config.meta,
                    )
                    containers_to_add.append(ContainerModel(**container.model_dump()))

        if containers_to_add:
            db.add_all(containers_to_add)

        log.debug("Created containers")

    def _get_lock(self, container_id: str) -> AsyncRLock:
        """
        Get the lock for a specific container.
        """
        return self._locks[container_id]

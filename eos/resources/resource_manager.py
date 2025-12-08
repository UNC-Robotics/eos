import asyncio
from collections import defaultdict
from typing import Any
from collections.abc import Callable

from sqlalchemy import select, delete, exists, update

from eos.configuration.configuration_manager import ConfigurationManager
from eos.resources.entities.resource import Resource, ResourceModel
from eos.resources.exceptions import EosResourceStateError
from eos.logging.logger import log

from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.utils.async_rlock import AsyncRLock
from eos.utils.di.di_container import inject


class ResourceManager:
    """
    The resource manager provides methods for interacting with resources in a lab.
    """

    @inject
    def __init__(self, configuration_manager: ConfigurationManager):
        self._configuration_manager = configuration_manager
        self._locks = defaultdict(AsyncRLock)

    async def initialize(self, db: AsyncDbSession) -> None:
        """Initialize the resource manager and create initial resources."""
        await self._create_resources(db)
        log.debug("Resource manager initialized.")

    async def _check_resource_exists(self, db: AsyncDbSession, resource_name: str) -> bool:
        """Check if a resource exists."""
        result = await db.execute(select(exists().where(ResourceModel.name == resource_name)))
        return result.scalar()

    async def get_resource(self, db: AsyncDbSession, resource_name: str) -> Resource:
        """
        Get a resource with the specified name.

        :param db: The database session
        :param resource_name: The name of the resource to retrieve
        :return: The resource
        :raises EosResourceStateError: If the resource doesn't exist
        """
        result = await db.execute(select(ResourceModel).where(ResourceModel.name == resource_name))
        if resource_model := result.scalar_one_or_none():
            return Resource.model_validate(resource_model)

        raise EosResourceStateError(f"Resource '{resource_name}' does not exist.")

    async def get_resources(self, db: AsyncDbSession, **filters: Any) -> list[Resource]:
        """
        Query resources with arbitrary parameters.

        :param db: The database session
        :param filters: Dictionary of query parameters
        :return: List of matching resources
        """
        stmt = select(ResourceModel)
        for key, value in filters.items():
            stmt = stmt.where(getattr(ResourceModel, key) == value)

        result = await db.execute(stmt)
        return [Resource.model_validate(model) for model in result.scalars()]

    async def set_lab(self, db: AsyncDbSession, resource_name: str, lab: str) -> None:
        """
        Set the lab of a resource.

        :param db: The database session
        :param resource_name: The name of the resource
        :param lab: The new lab
        :raises EosResourceStateError: If the resource doesn't exist
        """
        async with self._get_lock(resource_name):
            if not await self._check_resource_exists(db, resource_name):
                raise EosResourceStateError(f"Resource '{resource_name}' does not exist.")

            await db.execute(update(ResourceModel).where(ResourceModel.name == resource_name).values(lab=lab))

    async def _update_resource_metadata(
        self, db: AsyncDbSession, resource_name: str, updater: Callable[[dict[str, Any]], dict[str, Any]]
    ) -> None:
        """
        Update resource metadata using an updater function.

        :param db: The database session
        :param resource_name: The name of the resource
        :param updater: Function that takes current metadata and returns updated metadata
        :raises EosResourceStateError: If the resource doesn't exist
        """
        async with self._get_lock(resource_name):
            resource = await self.get_resource(db, resource_name)
            updated_meta = updater(resource.meta)
            await db.execute(update(ResourceModel).where(ResourceModel.name == resource_name).values(meta=updated_meta))

    async def set_meta(self, db: AsyncDbSession, resource_name: str, meta: dict[str, Any]) -> None:
        """
        Set metadata for a resource (replaces all existing metadata).

        :param db: The database session
        :param resource_name: The name of the resource
        :param meta: The new metadata dictionary
        :raises EosResourceStateError: If the resource doesn't exist
        """
        await self._update_resource_metadata(db, resource_name, lambda _: meta)

    async def add_meta(self, db: AsyncDbSession, resource_name: str, meta: dict[str, Any]) -> None:
        """
        Add metadata to a resource (merges with existing metadata).

        :param db: The database session
        :param resource_name: The name of the resource
        :param meta: The metadata to add
        :raises EosResourceStateError: If the resource doesn't exist
        """

        def updater(current_meta: dict[str, Any]) -> dict[str, Any]:
            current_meta.update(meta)
            return current_meta

        await self._update_resource_metadata(db, resource_name, updater)

    async def remove_meta(self, db: AsyncDbSession, resource_name: str, meta_keys: list[str]) -> None:
        """
        Remove metadata keys from a resource.

        :param db: The database session
        :param resource_name: The name of the resource
        :param meta_keys: List of metadata keys to remove
        :raises EosResourceStateError: If the resource doesn't exist
        """

        def updater(current_meta: dict[str, Any]) -> dict[str, Any]:
            for key in meta_keys:
                current_meta.pop(key, None)
            return current_meta

        await self._update_resource_metadata(db, resource_name, updater)

    async def update_resource(self, db: AsyncDbSession, resource: Resource) -> None:
        """
        Update a resource in the database.

        :param db: The database session
        :param resource: The resource to update
        :raises EosResourceStateError: If the resource doesn't exist
        """
        if not await self._check_resource_exists(db, resource.name):
            raise EosResourceStateError(f"Resource '{resource.name}' does not exist.")

        resource_data = resource.model_dump()
        await db.execute(update(ResourceModel).where(ResourceModel.name == resource.name).values(**resource_data))

    async def update_resources(
        self, db: AsyncDbSession, loaded_labs: set[str] | None = None, unloaded_labs: set[str] | None = None
    ) -> None:
        """
        Update resources based on loaded and unloaded labs.

        :param db: The database session
        :param loaded_labs: Set of labs that were loaded
        :param unloaded_labs: Set of labs that were unloaded
        """
        if unloaded_labs:
            await self._remove_resources_for_labs(db, unloaded_labs)

        if loaded_labs:
            await asyncio.gather(*[self._create_resources_for_lab(db, lab_name) for lab_name in loaded_labs])

        log.debug("Resources have been updated.")

    async def _remove_resources_for_labs(self, db: AsyncDbSession, lab_names: set[str]) -> None:
        """Remove resources associated with unloaded labs."""
        # Get resource names before deletion to clean up locks
        result = await db.execute(select(ResourceModel.name).where(ResourceModel.lab.in_(lab_names)))
        resource_names = [row[0] for row in result.fetchall()]

        await db.execute(delete(ResourceModel).where(ResourceModel.lab.in_(lab_names)))

        # Clean up locks for removed resources
        for resource_name in resource_names:
            self._locks.pop(resource_name, None)

        log.debug(f"Removed resources for labs: {', '.join(lab_names)}")

    @staticmethod
    def _build_resource_from_config(resource_name: str, resource_config, lab_config) -> Resource:
        """
        Build a Resource object from configuration, merging type defaults with resource-specific metadata.

        :param resource_name: Name of the resource
        :param resource_config: Resource configuration
        :param lab_config: Lab configuration containing resource type defaults
        :return: Configured Resource object
        """
        # Merge resource type default metadata with resource-specific metadata
        resource_type_meta = {}
        if resource_config.type in lab_config.resource_types:
            resource_type_meta = lab_config.resource_types[resource_config.type].meta.copy()

        # Resource-specific metadata overrides type defaults
        merged_meta = {**resource_type_meta, **resource_config.meta}

        return Resource(
            name=resource_name,
            type=resource_config.type,
            lab=lab_config.name,
            meta=merged_meta,
        )

    async def _create_resources_for_lab(self, db: AsyncDbSession, lab_name: str) -> None:
        """Create resources for a loaded lab."""
        lab_config = self._configuration_manager.labs[lab_name]
        resources_to_add = []

        for resource_name, resource_config in lab_config.resources.items():
            if not await self._check_resource_exists(db, resource_name):
                resource = self._build_resource_from_config(resource_name, resource_config, lab_config)
                resources_to_add.append(ResourceModel(**resource.model_dump()))

        if resources_to_add:
            db.add_all(resources_to_add)

        log.debug(f"Created resources for lab '{lab_name}'")

    async def _create_resources(self, db: AsyncDbSession) -> None:
        """Create resources from the lab configuration."""
        resources_to_add = []

        for _lab_name, lab_config in self._configuration_manager.labs.items():
            for resource_name, resource_config in lab_config.resources.items():
                resource = self._build_resource_from_config(resource_name, resource_config, lab_config)
                resources_to_add.append(ResourceModel(**resource.model_dump()))

        if resources_to_add:
            db.add_all(resources_to_add)

        log.debug("Created resources")

    def _get_lock(self, resource_name: str) -> AsyncRLock:
        """
        Get the lock for a specific resource.
        """
        return self._locks[resource_name]

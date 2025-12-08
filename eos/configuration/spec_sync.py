import traceback
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from sqlalchemy import select, delete, update
from sqlalchemy.dialects.postgresql import insert

from eos.configuration.entities.specification import SpecificationModel
from eos.configuration.packages.entities import EntityType
from eos.configuration.packages.package_manager import PackageManager
from eos.configuration.spec_registries.device_spec_registry import DeviceSpecRegistry
from eos.configuration.spec_registries.task_spec_registry import TaskSpecRegistry
from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.logging.logger import log


class SpecSync:
    """
    Responsible for synchronizing specification data from the file system to the database.
    Specs are persisted in the database and only deleted when source files are removed.
    """

    def __init__(
        self,
        package_manager: PackageManager,
        task_spec_registry: TaskSpecRegistry,
        device_spec_registry: DeviceSpecRegistry,
    ):
        self._package_manager = package_manager
        self._task_spec_registry = task_spec_registry
        self._device_spec_registry = device_spec_registry

    async def sync_all_specs(self, db: AsyncDbSession) -> None:
        """
        Discover and sync all specifications from the user directory to the database.
        This includes tasks, devices, labs, and experiments.
        """
        log.info("Syncing specs to database...")
        try:
            await self.sync_task_specs(db)
            await self.sync_device_specs(db)
            await self.sync_lab_specs(db)
            await self.sync_experiment_specs(db)
            log.info("Successfully synced all specs to database")
        except Exception:
            log.error(f"Error syncing specs to database: {traceback.format_exc()}")
            raise

    async def sync_task_specs(self, db: AsyncDbSession) -> None:
        """Sync all task specifications to the database using batch UPSERT."""
        task_specs = self._task_spec_registry.get_all_specs()

        specs_to_upsert = []
        for task_type, task_spec in task_specs.items():
            # Get the directory path and package for this task
            dir_path = self._task_spec_registry.get_dir_by_type(task_type)
            if not dir_path:
                log.warning(f"Could not find directory path for task type '{task_type}', skipping sync")
                continue

            package_name = str(dir_path).split("/")[0] if "/" in str(dir_path) else "unknown"
            source_path = str(dir_path)

            # Use directory name as spec_name (guaranteed unique across packages)
            dir_name = dir_path.name

            specs_to_upsert.append(
                {
                    "spec_type": "task",
                    "spec_name": dir_name,
                    "spec_data": task_spec.model_dump(),
                    "is_loaded": True,
                    "package_name": package_name,
                    "source_path": source_path,
                }
            )

        if specs_to_upsert:
            await self._batch_upsert_specs(db, specs_to_upsert)
            log.debug(f"Synced {len(specs_to_upsert)} task specs to database")

    async def sync_device_specs(self, db: AsyncDbSession) -> None:
        """Sync all device specifications to the database using batch UPSERT."""
        device_specs = self._device_spec_registry.get_all_specs()

        specs_to_upsert = []
        for device_type, device_spec in device_specs.items():
            # Get the directory path and package for this device
            dir_path = self._device_spec_registry.get_dir_by_type(device_type)
            if not dir_path:
                log.warning(f"Could not find directory path for device type '{device_type}', skipping sync")
                continue

            package_name = str(dir_path).split("/")[0] if "/" in str(dir_path) else "unknown"
            source_path = str(dir_path)

            # Use directory name as spec_name (guaranteed unique across packages)
            dir_name = dir_path.name

            specs_to_upsert.append(
                {
                    "spec_type": "device",
                    "spec_name": dir_name,
                    "spec_data": device_spec.model_dump(),
                    "is_loaded": True,  # Devices are always available once discovered
                    "package_name": package_name,
                    "source_path": source_path,
                }
            )

        if specs_to_upsert:
            await self._batch_upsert_specs(db, specs_to_upsert)
            log.debug(f"Synced {len(specs_to_upsert)} device specs to database")

    async def sync_lab_specs(self, db: AsyncDbSession) -> None:
        """Sync all discovered lab specifications to the database using batch UPSERT."""
        # Get all lab types from all packages
        all_lab_types = set()
        for package in self._package_manager.get_all_packages():
            package_labs = self._package_manager.get_entities_in_package(package.name, EntityType.LAB)
            all_lab_types.update(package_labs)

        specs_to_upsert = []
        for lab_type in all_lab_types:
            try:
                lab_config = self._package_manager.read_lab_config(lab_type)
                package = self._package_manager.find_package_for_entity(lab_type, EntityType.LAB)
                package_name = package.name if package else "unknown"

                # Get source path
                entity_dir = self._package_manager.get_entity_dir(lab_type, EntityType.LAB)
                source_path = str(entity_dir.relative_to(Path(self._package_manager._user_dir)))

                specs_to_upsert.append(
                    {
                        "spec_type": "lab",
                        "spec_name": lab_type,
                        "spec_data": lab_config.model_dump(),
                        "is_loaded": False,  # Will be set to True when lab is loaded
                        "package_name": package_name,
                        "source_path": source_path,
                    }
                )
            except Exception as e:
                log.error(f"Error syncing lab spec '{lab_type}': {e}")
                continue

        if specs_to_upsert:
            await self._batch_upsert_specs(db, specs_to_upsert)
            log.debug(f"Synced {len(specs_to_upsert)} lab specs to database")

    async def sync_experiment_specs(self, db: AsyncDbSession) -> None:
        """Sync all discovered experiment specifications to the database using batch UPSERT."""
        # Get all experiment types from all packages
        all_experiment_types = set()
        for package in self._package_manager.get_all_packages():
            package_experiments = self._package_manager.get_entities_in_package(package.name, EntityType.EXPERIMENT)
            all_experiment_types.update(package_experiments)

        specs_to_upsert = []
        for experiment_type in all_experiment_types:
            try:
                experiment_config = self._package_manager.read_experiment_config(experiment_type)
                package = self._package_manager.find_package_for_entity(experiment_type, EntityType.EXPERIMENT)
                package_name = package.name if package else "unknown"

                # Get source path
                entity_dir = self._package_manager.get_entity_dir(experiment_type, EntityType.EXPERIMENT)
                source_path = str(entity_dir.relative_to(Path(self._package_manager._user_dir)))

                specs_to_upsert.append(
                    {
                        "spec_type": "experiment",
                        "spec_name": experiment_type,
                        "spec_data": experiment_config.model_dump(),
                        "is_loaded": False,  # Will be set to True when experiment is loaded
                        "package_name": package_name,
                        "source_path": source_path,
                    }
                )
            except Exception as e:
                log.error(f"Error syncing experiment spec '{experiment_type}': {e}")
                continue

        if specs_to_upsert:
            await self._batch_upsert_specs(db, specs_to_upsert)
            log.debug(f"Synced {len(specs_to_upsert)} experiment specs to database")

    async def mark_labs_loaded(self, db: AsyncDbSession, lab_names: set[str], is_loaded: bool) -> None:
        """
        Update the is_loaded status for multiple lab specifications in a single batch operation.
        Optimized for minimal database queries.
        """
        if not lab_names:
            return

        await self._batch_update_loaded_status(db, "lab", lab_names, is_loaded)
        status_text = "loaded" if is_loaded else "unloaded"
        log.debug(f"Marked {len(lab_names)} labs as {status_text} in database")

    async def mark_experiments_loaded(self, db: AsyncDbSession, experiment_names: set[str], is_loaded: bool) -> None:
        """
        Update the is_loaded status for multiple experiment specifications in a single batch operation.
        Optimized for minimal database queries.
        """
        if not experiment_names:
            return

        await self._batch_update_loaded_status(db, "experiment", experiment_names, is_loaded)
        status_text = "loaded" if is_loaded else "unloaded"
        log.debug(f"Marked {len(experiment_names)} experiments as {status_text} in database")

    async def cleanup_deleted_specs(self, db: AsyncDbSession) -> None:
        """
        Remove specifications from the database where the source files no longer exist.
        This should be called periodically or on startup.
        Uses the registries and package manager as the source of truth for what exists.
        """
        # Build lookup of existing entities by type
        existing_entities = self._get_all_existing_entities()

        # Get all specs from database
        result = await db.execute(select(SpecificationModel))
        all_specs = result.scalars().all()

        specs_to_delete = []
        for spec in all_specs:
            existing_set = existing_entities.get(spec.spec_type)
            if existing_set is None or spec.spec_name not in existing_set:
                specs_to_delete.append((spec.spec_type, spec.spec_name))
                log.info(f"Removing spec '{spec.spec_type}/{spec.spec_name}' - no longer exists in user directory")

        if specs_to_delete:
            for spec_type, spec_name in specs_to_delete:
                await db.execute(
                    delete(SpecificationModel).where(
                        SpecificationModel.spec_type == spec_type,
                        SpecificationModel.spec_name == spec_name,
                    )
                )
            await db.commit()
            log.info(f"Cleaned up {len(specs_to_delete)} deleted specs from database")

    def _get_all_existing_entities(self) -> dict[str, set[str]]:
        """Build a mapping of spec_type to existing entity names from the package manager."""
        spec_type_to_entity_type = {
            "task": EntityType.TASK,
            "device": EntityType.DEVICE,
            "lab": EntityType.LAB,
            "experiment": EntityType.EXPERIMENT,
        }

        existing_entities: dict[str, set[str]] = {}
        for spec_type, entity_type in spec_type_to_entity_type.items():
            try:
                entities: set[str] = set()
                for package in self._package_manager.get_all_packages():
                    package_entities = self._package_manager.get_entities_in_package(package.name, entity_type)
                    entities.update(package_entities)
                existing_entities[spec_type] = entities
            except Exception:
                existing_entities[spec_type] = set()

        return existing_entities

    async def _batch_upsert_specs(self, db: AsyncDbSession, specs: list[dict[str, Any]]) -> None:
        """
        Insert or update multiple specifications in the database using a single batch operation.
        Uses PostgreSQL's INSERT ... ON CONFLICT DO UPDATE for idempotency.
        Commits only once at the end for optimal performance.
        """
        if not specs:
            return

        now = datetime.now(UTC)

        # Add timestamps to all specs
        for spec in specs:
            spec["created_at"] = now
            spec["updated_at"] = now

        # Execute all upserts in a single batch
        stmt = insert(SpecificationModel).values(specs)

        # On conflict, update all fields except created_at
        stmt = stmt.on_conflict_do_update(
            index_elements=["spec_type", "spec_name"],
            set_={
                "spec_data": stmt.excluded.spec_data,
                "is_loaded": stmt.excluded.is_loaded,
                "package_name": stmt.excluded.package_name,
                "source_path": stmt.excluded.source_path,
                "updated_at": now,
            },
        )

        await db.execute(stmt)
        await db.commit()

    async def _batch_update_loaded_status(
        self, db: AsyncDbSession, spec_type: str, spec_names: set[str], is_loaded: bool
    ) -> None:
        """
        Update the is_loaded status for multiple specs in a single batch operation.
        Much more efficient than individual updates.
        """
        if not spec_names:
            return

        now = datetime.now(UTC)

        # Single UPDATE query for all specs of the same type
        stmt = (
            update(SpecificationModel)
            .where(
                SpecificationModel.spec_type == spec_type,
                SpecificationModel.spec_name.in_(spec_names),
            )
            .values(is_loaded=is_loaded, updated_at=now)
        )

        result = await db.execute(stmt)
        await db.commit()

        # Warn if some specs weren't found
        if result.rowcount != len(spec_names):
            log.warning(f"Expected to update {len(spec_names)} {spec_type} specs, but only updated {result.rowcount}")

import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select, update

from eos.configuration.entities.definition import DefinitionModel
from eos.configuration.packages import EntityType, PackageManager
from eos.configuration.registries import SpecRegistry
from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.logging.logger import log


class DefSync:
    """Synchronizes definitions from the file system to the database."""

    def __init__(
        self,
        package_manager: PackageManager,
        task_spec_registry: SpecRegistry,
        device_spec_registry: SpecRegistry,
    ):
        self._package_manager = package_manager
        self._task_spec_registry = task_spec_registry
        self._device_spec_registry = device_spec_registry

    async def sync_all_defs(self, db: AsyncDbSession) -> None:
        """Sync all definitions (tasks, devices, labs, experiments) to the database."""
        log.info("Syncing defs to database...")
        try:
            await self.sync_task_defs(db)
            await self.sync_device_defs(db)
            await self.sync_lab_defs(db)
            await self.sync_experiment_defs(db)
            log.info("Successfully synced all defs to database")
        except Exception:
            log.error(f"Error syncing defs to database: {traceback.format_exc()}")
            raise

    async def sync_task_defs(self, db: AsyncDbSession) -> None:
        """Sync task definitions to the database."""
        await self._sync_registry_defs(db, self._task_spec_registry, "task")

    async def sync_device_defs(self, db: AsyncDbSession) -> None:
        """Sync device definitions to the database."""
        await self._sync_registry_defs(db, self._device_spec_registry, "device")

    async def _sync_registry_defs(self, db: AsyncDbSession, registry: SpecRegistry, def_type: str) -> None:
        """Sync defs from a registry to the database."""
        defs_to_upsert = []
        for type_name, spec in registry.get_all_specs().items():
            dir_path = registry.get_dir_by_type(type_name)
            if not dir_path:
                log.warning(f"Could not find directory for {def_type} '{type_name}', skipping")
                continue

            package_name = str(dir_path).split("/")[0] if "/" in str(dir_path) else "unknown"
            defs_to_upsert.append(
                {
                    "type": def_type,
                    "name": dir_path.name,
                    "data": spec.model_dump(),
                    "is_loaded": True,
                    "package_name": package_name,
                    "source_path": str(dir_path),
                }
            )

        if defs_to_upsert:
            await self._batch_upsert_defs(db, defs_to_upsert)
            log.debug(f"Synced {len(defs_to_upsert)} {def_type} definitions to database")

    async def sync_lab_defs(self, db: AsyncDbSession) -> None:
        """Sync lab definitions to the database."""
        await self._sync_entity_defs(db, EntityType.LAB, "lab", self._package_manager.read_lab, is_loaded=False)

    async def sync_experiment_defs(self, db: AsyncDbSession) -> None:
        """Sync experiment definitions to the database."""
        await self._sync_entity_defs(
            db, EntityType.EXPERIMENT, "experiment", self._package_manager.read_experiment, is_loaded=False
        )

    async def _sync_entity_defs(
        self,
        db: AsyncDbSession,
        entity_type: EntityType,
        def_type: str,
        read_config_fn,
        is_loaded: bool,
    ) -> None:
        """Sync defs for an entity type from packages to the dionatabase."""
        all_entity_types = set()
        for package in self._package_manager.get_all_packages():
            all_entity_types.update(self._package_manager.get_entities_in_package(package.name, entity_type))

        defs_to_upsert = []
        for entity_name in all_entity_types:
            try:
                config = read_config_fn(entity_name)
                package = self._package_manager.find_package_for_entity(entity_name, entity_type)
                entity_dir = self._package_manager.get_entity_dir(entity_name, entity_type)
                source_path = str(entity_dir.relative_to(Path(self._package_manager._user_dir)))

                defs_to_upsert.append(
                    {
                        "type": def_type,
                        "name": entity_name,
                        "data": config.model_dump(),
                        "is_loaded": is_loaded,
                        "package_name": package.name if package else "unknown",
                        "source_path": source_path,
                    }
                )
            except Exception as e:
                log.error(f"Error syncing {def_type} definition '{entity_name}': {e}")

        if defs_to_upsert:
            await self._batch_upsert_defs(db, defs_to_upsert)
            log.debug(f"Synced {len(defs_to_upsert)} {def_type} definitions to database")

    async def mark_labs_loaded(self, db: AsyncDbSession, lab_names: set[str], is_loaded: bool) -> None:
        """Update is_loaded status for lab definitions."""
        await self._mark_defs_loaded(db, "lab", lab_names, is_loaded)

    async def mark_experiments_loaded(self, db: AsyncDbSession, experiment_names: set[str], is_loaded: bool) -> None:
        """Update is_loaded status for experiment definitions."""
        await self._mark_defs_loaded(db, "experiment", experiment_names, is_loaded)

    async def _mark_defs_loaded(self, db: AsyncDbSession, def_type: str, names: set[str], is_loaded: bool) -> None:
        """Update is_loaded status for multiple defs."""
        if not names:
            return
        await self._batch_update_loaded_status(db, def_type, names, is_loaded)
        log.debug(f"Marked {len(names)} {def_type}s as {'loaded' if is_loaded else 'unloaded'}")

    async def cleanup_deleted_defs(self, db: AsyncDbSession) -> None:
        """Remove defs from the database where source files no longer exist."""
        existing_entities = self._get_all_existing_entities()

        result = await db.execute(select(DefinitionModel))
        all_defs = result.scalars().all()

        defs_to_delete = [
            (defn.type, defn.name) for defn in all_defs if defn.name not in existing_entities.get(defn.type, set())
        ]

        for def_type, def_name in defs_to_delete:
            log.info(f"Removing definition '{def_type}/{def_name}' - no longer exists")
            await db.execute(
                delete(DefinitionModel).where(
                    DefinitionModel.type == def_type,
                    DefinitionModel.name == def_name,
                )
            )

        if defs_to_delete:
            await db.commit()
            log.info(f"Cleaned up {len(defs_to_delete)} deleted definitions from database")

    def _get_all_existing_entities(self) -> dict[str, set[str]]:
        """Build mapping of def_type to existing entity names."""
        def_type_to_entity_type = {
            "task": EntityType.TASK,
            "device": EntityType.DEVICE,
            "lab": EntityType.LAB,
            "experiment": EntityType.EXPERIMENT,
        }

        existing_entities: dict[str, set[str]] = {}
        for def_type, entity_type in def_type_to_entity_type.items():
            try:
                entities: set[str] = set()
                for package in self._package_manager.get_all_packages():
                    entities.update(self._package_manager.get_entities_in_package(package.name, entity_type))
                existing_entities[def_type] = entities
            except Exception:
                existing_entities[def_type] = set()

        return existing_entities

    async def _batch_upsert_defs(self, db: AsyncDbSession, defs: list[dict[str, Any]]) -> None:
        """Batch insert or update definitions."""
        if not defs:
            return

        now = datetime.now(UTC)
        for defn in defs:
            existing = await db.get(DefinitionModel, (defn["type"], defn["name"]))

            if existing:
                existing.data = defn["data"]
                existing.is_loaded = defn["is_loaded"]
                existing.package_name = defn["package_name"]
                existing.source_path = defn["source_path"]
                existing.updated_at = now
            else:
                defn["created_at"] = now
                defn["updated_at"] = now
                db.add(DefinitionModel(**defn))

        await db.commit()

    async def _batch_update_loaded_status(
        self, db: AsyncDbSession, def_type: str, def_names: set[str], is_loaded: bool
    ) -> None:
        """Update is_loaded status for multiple defs in a single query."""
        if not def_names:
            return

        stmt = (
            update(DefinitionModel)
            .where(
                DefinitionModel.type == def_type,
                DefinitionModel.name.in_(def_names),
            )
            .values(is_loaded=is_loaded, updated_at=datetime.now(UTC))
        )

        result = await db.execute(stmt)
        await db.commit()

        if result.rowcount != len(def_names):
            log.warning(f"Expected to update {len(def_names)} {def_type} definitions, but updated {result.rowcount}")

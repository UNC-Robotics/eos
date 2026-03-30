from eos.configuration.configuration_manager import ConfigurationManager
from eos.configuration.exceptions import EosConfigurationError
from eos.configuration.packages import EntityType
from eos.resources.resource_manager import ResourceManager
from eos.devices.device_manager import DeviceManager
from eos.protocols.entities.protocol_run import ProtocolRunStatus
from eos.protocols.protocol_run_manager import ProtocolRunManager
from eos.logging.logger import log
from eos.orchestration.exceptions import EosProtocolInUseError
from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.tasks.entities.task import TaskStatus, Task
from eos.tasks.task_manager import TaskManager
from eos.utils.async_rlock import AsyncRLock
from eos.utils.di.di_container import inject


class LoadingService:
    """Responsible for loading/unloading entities such as labs, protocols, etc."""

    @inject
    def __init__(
        self,
        configuration_manager: ConfigurationManager,
        device_manager: DeviceManager,
        resource_manager: ResourceManager,
        protocol_run_manager: ProtocolRunManager,
        task_manager: TaskManager,
    ):
        self._configuration_manager = configuration_manager
        self._device_manager = device_manager
        self._resource_manager = resource_manager
        self._protocol_run_manager = protocol_run_manager
        self._task_manager = task_manager
        self._loading_lock = AsyncRLock()

    async def load_labs(self, db: AsyncDbSession, labs: set[str]) -> None:
        """Load one or more labs into the orchestrator."""
        async with self._loading_lock:
            self._configuration_manager.load_labs(labs)
            await self._device_manager.update_devices(db, loaded_labs=labs)
            await self._resource_manager.update_resources(db, loaded_labs=labs)
            await self._configuration_manager.def_sync.mark_labs_loaded(db, labs, True)

    async def unload_labs(self, db: AsyncDbSession, labs: set[str]) -> None:
        """Unload one or more labs from the orchestrator."""
        for lab_name in labs:
            await self._check_lab_usage(db, lab_name)

        async with self._loading_lock:
            # Determine which protocols will be implicitly unloaded with the labs
            protocols_to_unload = self._get_protocols_for_labs(labs)

            self._configuration_manager.unload_labs(labs)
            await self._device_manager.update_devices(db, unloaded_labs=labs)
            await self._resource_manager.update_resources(db, unloaded_labs=labs)
            await self._configuration_manager.def_sync.mark_labs_loaded(db, labs, False)

            # Mark implicitly unloaded protocols in the database
            if protocols_to_unload:
                await self._configuration_manager.def_sync.mark_protocols_loaded(db, protocols_to_unload, False)

    async def reload_labs(self, db: AsyncDbSession, lab_types: set[str]) -> None:
        """Reload one or more labs in the orchestrator with updated device plugin code."""
        for lab_type in lab_types:
            lab = self._configuration_manager.package_manager.read_lab(lab_type)
            device_types = {device.type for device in lab.devices.values()}
            for device_type in device_types:
                try:
                    self._configuration_manager.devices.reload_plugin(device_type)
                except Exception as e:
                    log.error(f"Failed to reload device '{device_type}' before lab reload: {e}")
                    raise

        async with self._loading_lock:
            # Determine which protocols will need re-loading after lab reload
            protocols_to_reload = self._get_protocols_for_labs(lab_types)

            # Ensure labs are not currently in use
            for lab_type in lab_types:
                await self._check_lab_usage(db, lab_type)

            try:
                # Unload: update in-memory config, devices, and containers
                self._configuration_manager.unload_labs(lab_types)
                await self._device_manager.update_devices(db, unloaded_labs=lab_types)
                await self._resource_manager.update_resources(db, unloaded_labs=lab_types)

                # Load: update in-memory config, devices, and containers
                self._configuration_manager.load_labs(lab_types)
                await self._device_manager.update_devices(db, loaded_labs=lab_types)
                await self._resource_manager.update_resources(db, loaded_labs=lab_types)

                # Finally, reload any dependent protocols
                await self.load_protocols(db, protocols_to_reload)
            except Exception as e:
                log.error(f"Error reloading labs {lab_types}: {e}")
                raise

    async def reload_devices(self, db: AsyncDbSession, lab_name: str, device_names: list[str]) -> None:
        """Reload specific devices within a lab."""
        async with self._loading_lock:
            # Verify lab is loaded
            if lab_name not in self._configuration_manager.labs:
                log.error(f"Cannot reload devices in lab '{lab_name}' as the lab is not loaded.")
                raise EosConfigurationError(f"Lab '{lab_name}' is not loaded")

            # Check if any protocols or tasks are using the devices
            await self._check_device_usage(db, lab_name, device_names)

            await self._device_manager.reload_devices(db, lab_name, device_names)

    def _get_protocols_for_labs(self, lab_types: set[str]) -> set[str]:
        """Get protocols that depend on the specified labs."""
        protocols_to_reload = set()
        for protocol_type, protocol in self._configuration_manager.protocols.items():
            if any(lab_type in protocol.labs for lab_type in lab_types):
                protocols_to_reload.add(protocol_type)
        return protocols_to_reload

    async def list_labs(self) -> dict[str, bool]:
        """Return a dictionary of lab types and a boolean indicating whether they are loaded."""
        return self._configuration_manager.get_loaded_labs()

    async def load_protocols(self, db: AsyncDbSession, protocol_types: set[str]) -> None:
        """Load one or more protocols into the orchestrator."""
        if not protocol_types:
            return

        self._configuration_manager.load_protocols(protocol_types)
        await self._configuration_manager.def_sync.mark_protocols_loaded(db, protocol_types, True)

    async def unload_protocols(self, db: AsyncDbSession, protocol_types: set[str]) -> None:
        """Unload one or more protocols from the orchestrator."""
        for protocol_type in protocol_types:
            await self._check_protocol_usage(db, protocol_type)

        self._configuration_manager.unload_protocols(protocol_types)
        await self._configuration_manager.def_sync.mark_protocols_loaded(db, protocol_types, False)

    async def reload_protocols(self, db: AsyncDbSession, protocol_types: set[str]) -> None:
        """Reload one or more protocols in the orchestrator."""
        async with self._loading_lock:
            for protocol_type in protocol_types:
                await self._check_protocol_usage(db, protocol_type)

            self._configuration_manager.unload_protocols(protocol_types)
            await self._configuration_manager.def_sync.mark_protocols_loaded(db, protocol_types, False)
            self._configuration_manager.load_protocols(protocol_types)
            await self._configuration_manager.def_sync.mark_protocols_loaded(db, protocol_types, True)

    async def list_protocols(self) -> dict[str, bool]:
        """Return a dictionary of protocol types and a boolean indicating whether they are loaded."""
        return self._configuration_manager.get_loaded_protocols()

    async def refresh_packages(self, db: AsyncDbSession) -> int:
        """
        Re-discover packages from the filesystem and sync specifications to the database.
        This allows the system to detect new or deleted entities (labs, protocols, tasks, devices).

        :param db: Database session
        :return: Number of packages discovered
        """
        async with self._loading_lock:
            log.info("Starting package refresh...")

            # Get the package manager
            package_manager = self._configuration_manager.package_manager

            # Re-discover packages from the filesystem
            package_manager.refresh()

            package_count = len(package_manager.get_all_packages())

            # Re-read task and device specs to update registries
            task_specs, task_dirs_to_types = package_manager.read_task_specs()
            self._configuration_manager.task_specs.update_specs(task_specs, task_dirs_to_types)

            device_specs, device_dirs_to_types = package_manager.read_device_specs()
            self._configuration_manager.device_specs.update_specs(device_specs, device_dirs_to_types)

            # Sync all specifications to the database
            await self._configuration_manager.def_sync.sync_all_defs(db)

            # Clean up specifications for deleted entities
            await self._configuration_manager.def_sync.cleanup_deleted_defs(db)

            log.info("Package refresh completed successfully")

            return package_count

    async def list_packages(self) -> dict[str, bool]:
        """List all discovered packages and whether they're currently active."""
        package_manager = self._configuration_manager.package_manager
        all_names = package_manager.discover_all_package_names()
        active_names = {p.name for p in package_manager.get_all_packages()}
        return {name: name in active_names for name in all_names}

    async def load_packages(self, db: AsyncDbSession, package_names: set[str]) -> None:
        """Load packages into the active set and sync definitions to database."""
        async with self._loading_lock:
            package_manager = self._configuration_manager.package_manager
            for name in package_names:
                package_manager.add_package(name)

            # Re-read specs and sync to DB
            task_specs, task_dirs = package_manager.read_task_specs()
            self._configuration_manager.task_specs.update_specs(task_specs, task_dirs)
            device_specs, device_dirs = package_manager.read_device_specs()
            self._configuration_manager.device_specs.update_specs(device_specs, device_dirs)
            self._configuration_manager._initialize_task_plugins()
            await self._configuration_manager.def_sync.sync_all_defs(db)

            log.info(f"Loaded packages: {', '.join(package_names)}")

    async def unload_packages(self, db: AsyncDbSession, package_names: set[str]) -> None:
        """Unload packages from the active set, checking for usage first."""
        for pkg_name in package_names:
            self._check_package_not_in_use(pkg_name)

        async with self._loading_lock:
            package_manager = self._configuration_manager.package_manager
            for name in package_names:
                package_manager.remove_package(name)

            # Re-read specs and sync/cleanup DB
            task_specs, task_dirs = package_manager.read_task_specs()
            self._configuration_manager.task_specs.update_specs(task_specs, task_dirs)
            device_specs, device_dirs = package_manager.read_device_specs()
            self._configuration_manager.device_specs.update_specs(device_specs, device_dirs)
            await self._configuration_manager.def_sync.sync_all_defs(db)
            await self._configuration_manager.def_sync.cleanup_deleted_defs(db)

            log.info(f"Unloaded packages: {', '.join(package_names)}")

    def _check_package_not_in_use(self, package_name: str) -> None:
        """Verify no loaded labs or protocols belong to the package."""
        package_manager = self._configuration_manager.package_manager

        lab_entities = package_manager.get_entities_in_package(package_name, EntityType.LAB)
        loaded_labs = set(self._configuration_manager.labs.keys())
        in_use_labs = loaded_labs & set(lab_entities)
        if in_use_labs:
            raise EosConfigurationError(
                f"Cannot remove package '{package_name}': labs {in_use_labs} are currently loaded"
            )

        protocol_entities = package_manager.get_entities_in_package(package_name, EntityType.PROTOCOL)
        loaded_protocols = set(self._configuration_manager.protocols.keys())
        in_use_protocols = loaded_protocols & set(protocol_entities)
        if in_use_protocols:
            raise EosConfigurationError(
                f"Cannot remove package '{package_name}': protocols {in_use_protocols} are currently loaded"
            )

    async def reload_task_plugins(self, db: AsyncDbSession, task_types: set[str]) -> None:
        """Reload one or more task plugins and their specs in the orchestrator."""
        async with self._loading_lock:
            for task_type in task_types:
                await self._check_task_usage(db, task_type)

            for task_type in task_types:
                self._configuration_manager.refresh_task_spec(task_type)
                self._configuration_manager.tasks.reload_plugin(task_type)
                log.info(f"Reloaded task '{task_type}'")

    async def _check_tasks_using_devices(
        self, db: AsyncDbSession, lab_name: str, device_names: list[str] | None = None
    ) -> list[Task]:
        """
        Check if any standalone tasks are using specific devices in a lab.

        Includes both RUNNING and CREATED tasks.

        :param db: Database session
        :param lab_name: The lab containing the devices
        :param device_names: Optional list of device IDs to check. If None, checks for any device in the lab.
        :return: List of active standalone tasks using the devices
        """
        # Get all active standalone tasks (both RUNNING and CREATED)
        active_tasks = []
        for status in [TaskStatus.RUNNING.value, TaskStatus.CREATED.value]:
            tasks = await self._task_manager.get_tasks(db, status=status)
            active_tasks.extend(tasks)

        # Filter tasks that use the specified devices
        device_tasks = []
        for task in active_tasks:
            if task.protocol_run_name and task.protocol_run_name != "on_demand":
                continue

            for device_config in task.devices:
                if device_config.lab == lab_name and (device_names is None or device_config.name in device_names):
                    device_tasks.append(task)
                    break

        return device_tasks

    async def _check_protocol_runs_using_lab(self, db: AsyncDbSession, lab_name: str) -> list:
        """
        Check if any running protocols are using a lab.

        :param db: Database session
        :param lab_name: The lab to check
        :return: List of protocols using the lab
        """
        running_protocol_runs = await self._protocol_run_manager.get_protocol_runs(
            db, status=ProtocolRunStatus.RUNNING.value
        )
        return [
            protocol_run
            for protocol_run in running_protocol_runs
            if lab_name in self._configuration_manager.protocols[protocol_run.type].labs
        ]

    async def _check_protocol_runs_using_devices(
        self, db: AsyncDbSession, lab_name: str, device_names: list[str]
    ) -> list:
        """
        Check if any running protocols are using specific devices.

        :param db: Database session
        :param lab_name: The lab containing the devices
        :param device_names: List of device names to check
        :return: List of protocols using the devices
        """
        running_protocol_runs = await self._protocol_run_manager.get_protocol_runs(
            db, status=ProtocolRunStatus.RUNNING.value
        )
        using_protocol_runs = []

        for protocol_run in running_protocol_runs:
            protocol_def = self._configuration_manager.protocols[protocol_run.type]
            if lab_name in protocol_def.labs:
                # Get the protocol's task graph to see if it uses any of these devices
                task_graph = protocol_def.task_graph
                for task in task_graph.tasks.values():
                    if task.lab == lab_name and any(device_name in task.devices for device_name in device_names):
                        using_protocol_runs.append(protocol_run)
                        break

        return using_protocol_runs

    async def _check_protocol_usage(self, db: AsyncDbSession, protocol_type: str) -> None:
        """
        Check if a protocol type is currently in use (has running instances).

        :param db: Database session
        :param protocol_type: The protocol type to check
        :raises EosProtocolInUseError: If the protocol has running instances
        """
        existing_protocol_runs = await self._protocol_run_manager.get_protocol_runs(
            db, status=ProtocolRunStatus.RUNNING.value, type=protocol_type
        )

        if existing_protocol_runs:
            protocol_run_names = ", ".join(protocol_run.id for protocol_run in existing_protocol_runs)
            log.error(
                f"Cannot modify protocol type '{protocol_type}' as it has running instances: {protocol_run_names}"
            )
            raise EosProtocolInUseError(f"ProtocolRun type '{protocol_type}' has running instances")

    async def _check_lab_usage(self, db: AsyncDbSession, lab_name: str) -> None:
        """
        Check if a lab is in use by any protocols or standalone tasks.

        :param db: Database session
        :param lab_name: The lab to check
        """
        # Check protocols using the lab
        using_protocol_runs = await self._check_protocol_runs_using_lab(db, lab_name)
        if using_protocol_runs:
            protocol_run_names = ", ".join(protocol_run.name for protocol_run in using_protocol_runs)
            log.error(f"Cannot modify lab '{lab_name}' as it is in use by protocols: {protocol_run_names}")
            raise EosProtocolInUseError(f"Lab '{lab_name}' is in use by protocols")

        # Check standalone tasks using the lab
        standalone_tasks = await self._check_tasks_using_devices(db, lab_name)
        if standalone_tasks:
            task_names = ", ".join(task.name for task in standalone_tasks)
            log.error(f"Cannot modify lab '{lab_name}' as it is in use by tasks: {task_names}")
            raise EosProtocolInUseError(f"Lab '{lab_name}' is in use by tasks")

    async def _check_device_usage(self, db: AsyncDbSession, lab_name: str, device_names: list[str]) -> None:
        """
        Check if specific devices are in use by any protocols or standalone tasks.

        :param db: Database session
        :param lab_name: The lab containing the devices
        :param device_names: List of device names to check
        """
        # Check protocols using the devices
        using_protocol_runs = await self._check_protocol_runs_using_devices(db, lab_name, device_names)
        if using_protocol_runs:
            protocol_run_names = ", ".join(protocol_run.name for protocol_run in using_protocol_runs)
            log.error(
                f"Cannot modify device(s) in lab '{lab_name}' as they are in use by protocols: {protocol_run_names}"
            )
            raise EosProtocolInUseError(f"Devices in lab '{lab_name}' are in use by protocols")

        # Check standalone tasks using the devices
        standalone_tasks = await self._check_tasks_using_devices(db, lab_name, device_names)
        if standalone_tasks:
            task_names = ", ".join(task.name for task in standalone_tasks)
            log.error(f"Cannot modify device(s) in lab '{lab_name}' as they are in use by tasks: {task_names}")
            raise EosProtocolInUseError(f"Devices in lab '{lab_name}' are in use by tasks")

    async def _check_task_usage(self, db: AsyncDbSession, task_type: str) -> None:
        """
        Check if a task type is currently in use (has running or created instances).

        :param db: Database session
        :param task_type: The task type to check
        :raises EosProtocolInUseError: If the task has active instances
        """
        active_tasks = []
        for status in [TaskStatus.RUNNING.value, TaskStatus.CREATED.value]:
            tasks = await self._task_manager.get_tasks(db, status=status, type=task_type)
            active_tasks.extend(tasks)

        if active_tasks:
            task_names = ", ".join(task.name for task in active_tasks)
            log.error(f"Cannot modify task type '{task_type}' as it has active instances: {task_names}")
            raise EosProtocolInUseError(f"Task type '{task_type}' has active instances")

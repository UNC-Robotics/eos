import asyncio
from abc import ABC

from eos.configuration.configuration_manager import ConfigurationManager
from eos.configuration.entities.task import TaskDeviceConfig, TaskConfig
from eos.configuration.experiment_graph.experiment_graph import ExperimentGraph
from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.devices.device_manager import DeviceManager
from eos.devices.entities.device import DeviceStatus
from eos.experiments.entities.experiment import Experiment
from eos.experiments.experiment_manager import ExperimentManager
from eos.logging.logger import log
from eos.resource_allocation.entities.resource_request import (
    ActiveResourceAllocationRequest,
    ResourceAllocationRequest,
    ResourceType,
    ResourceRequestAllocationStatus,
)
from eos.resource_allocation.exceptions import EosResourceRequestError
from eos.resource_allocation.resource_allocation_manager import ResourceAllocationManager
from eos.scheduling.abstract_scheduler import AbstractScheduler
from eos.scheduling.entities.scheduled_task import ScheduledTask
from eos.scheduling.exceptions import EosSchedulerRegistrationError
from eos.tasks.task_input_resolver import TaskInputResolver
from eos.tasks.task_manager import TaskManager
from eos.utils.async_rlock import AsyncRLock


class BaseScheduler(AbstractScheduler, ABC):
    """
    This base scheduler contains common logic shared by multiple scheduler implementations.
    """

    def __init__(
        self,
        configuration_manager: ConfigurationManager,
        experiment_manager: ExperimentManager,
        task_manager: TaskManager,
        device_manager: DeviceManager,
        resource_allocation_manager: ResourceAllocationManager,
    ):
        self._configuration_manager = configuration_manager
        self._experiment_manager = experiment_manager
        self._task_input_resolver = TaskInputResolver(task_manager, experiment_manager)
        self._device_manager = device_manager
        self._resource_allocation_manager = resource_allocation_manager
        self._device_allocation_manager = resource_allocation_manager.device_allocation_manager
        self._container_allocator = resource_allocation_manager.container_allocation_manager

        # Mapping: experiment_id -> (experiment_type, experiment_graph)
        self._registered_experiments: dict[str, tuple[str, ExperimentGraph]] = {}

        # Mapping: experiment_id -> {task_id -> ActiveResourceAllocationRequest}
        self._allocated_resources: dict[str, dict[str, ActiveResourceAllocationRequest]] = {}

        self._lock = AsyncRLock()

    async def register_experiment(
        self, experiment_id: str, experiment_type: str, experiment_graph: ExperimentGraph
    ) -> None:
        """
        Register an experiment by checking that the experiment type exists and storing its graph.
        """
        async with self._lock:
            if experiment_type not in self._configuration_manager.experiments:
                raise EosSchedulerRegistrationError(f"Experiment type '{experiment_type}' does not exist.")
            self._registered_experiments[experiment_id] = (experiment_type, experiment_graph)

    async def unregister_experiment(self, db: AsyncDbSession, experiment_id: str) -> None:
        """
        Unregister an experiment and release its allocated resources.
        """
        async with self._lock:
            if experiment_id not in self._registered_experiments:
                raise EosSchedulerRegistrationError(f"Experiment {experiment_id} is not registered.")
            del self._registered_experiments[experiment_id]
            await self._release_experiment_resources(db, experiment_id)

    async def _release_task_resources(self, db: AsyncDbSession, experiment_id: str, task_id: str) -> None:
        """
        Release allocated resources for a given task.
        """
        active_request = self._allocated_resources.get(experiment_id, {}).pop(task_id, None)
        if active_request:
            try:
                await self._resource_allocation_manager.release_resources(db, active_request)
            except EosResourceRequestError as e:
                log.error(f"Error releasing resources for task {task_id} in experiment {experiment_id}: {e!s}")

    async def _release_experiment_resources(self, db: AsyncDbSession, experiment_id: str) -> None:
        """
        Release resources for all tasks belonging to an experiment.
        """
        task_ids = list(self._allocated_resources.get(experiment_id, {}).keys())
        for task_id in task_ids:
            await self._release_task_resources(db, experiment_id, task_id)
        self._allocated_resources.pop(experiment_id, None)

    @staticmethod
    def _check_task_dependencies_met(
        task_id: str, completed_tasks: set[str], experiment_graph: ExperimentGraph
    ) -> bool:
        """
        Check whether all dependencies of a task have been completed.
        """
        dependencies = experiment_graph.get_task_dependencies(task_id)
        return all(dep in completed_tasks for dep in dependencies)

    async def _check_device_available(
        self, db: AsyncDbSession, task_config: TaskConfig, experiment_id: str, task_device: TaskDeviceConfig
    ) -> bool:
        """
        A device is available if it is active and either unallocated or allocated to this task.
        """
        device = await self._device_manager.get_device(db, task_device.lab_id, task_device.id)
        if device.status == DeviceStatus.INACTIVE:
            log.warning(
                "Device %s in lab %s is inactive (requested by task %s).",
                task_device.id,
                task_device.lab_id,
                task_config.id,
            )
            return False
        allocation = await self._device_allocation_manager.get_allocation(db, task_device.lab_id, task_device.id)
        if not allocation:
            return True
        return allocation.owner == task_config.id and allocation.experiment_id == experiment_id

    async def _check_container_available(
        self, db: AsyncDbSession, task_config: TaskConfig, experiment_id: str, container_id: str
    ) -> bool:
        """
        A container is available if it is unallocated or allocated to the requesting task.
        """
        allocation = await self._container_allocator.get_allocation(db, container_id)
        if not allocation:
            return True
        return allocation.owner == task_config.id and allocation.experiment_id == experiment_id

    @staticmethod
    def _create_resource_request(
        task_id: str, task_config: TaskConfig, experiment: Experiment
    ) -> ResourceAllocationRequest | None:
        """
        Create a resource allocation request for all resources required by a task.
        """
        if not task_config.devices and not task_config.containers:
            return None
        request = ResourceAllocationRequest(
            requester=task_id,
            experiment_id=experiment.id,
            priority=experiment.priority,
            reason=f"Resources required for task '{task_id}'",
        )
        for device in task_config.devices:
            request.add_resource(device.id, device.lab_id, ResourceType.DEVICE)
        for container_id in task_config.containers.values():
            request.add_resource(container_id, "", ResourceType.CONTAINER)
        return request

    async def is_experiment_completed(self, db: AsyncDbSession, experiment_id: str) -> bool:
        """
        Check if every task in the experiment graph has been completed.
        """
        if experiment_id not in self._registered_experiments:
            raise Exception(f"Cannot check completion of unregistered experiment {experiment_id}.")
        _, experiment_graph = self._registered_experiments[experiment_id]
        all_tasks = set(experiment_graph.get_task_graph().nodes)
        completed_tasks = set(await self._experiment_manager.get_completed_tasks(db, experiment_id))
        return all_tasks.issubset(completed_tasks)

    async def _check_and_allocate_resources(
        self,
        db: AsyncDbSession,
        experiment_id: str,
        task_id: str,
        completed_tasks: set[str],
        experiment_graph: ExperimentGraph,
    ) -> ScheduledTask | None:
        """
        Check if a task can be scheduled and allocate resources for it if possible.

        :param db: A database session.
        :param experiment_id: The ID of the experiment.
        :param task_id: The ID of the task to check.
        :param completed_tasks: Set of completed task IDs.
        :param experiment_graph: The experiment graph.
        :return: A ScheduledTask if the task can be scheduled, None otherwise.
        """
        # Check if dependencies are met
        if not self._check_task_dependencies_met(task_id, completed_tasks, experiment_graph):
            return None

        # Resolve container input references
        task_config = experiment_graph.get_task_config(task_id)
        task_config = await self._task_input_resolver.resolve_input_container_references(db, experiment_id, task_config)

        # Check device availability
        if task_config.devices:
            device_checks = [
                self._check_device_available(db, task_config, experiment_id, device) for device in task_config.devices
            ]
            if not all(await asyncio.gather(*device_checks)):
                return None

        # Check container availability
        if task_config.containers:
            container_checks = [
                self._check_container_available(db, task_config, experiment_id, container_id)
                for container_id in task_config.containers.values()
            ]
            if not all(await asyncio.gather(*container_checks)):
                return None

        try:
            experiment = await self._experiment_manager.get_experiment(db, experiment_id)
            resource_request = self._create_resource_request(task_id, task_config, experiment)

            # Allocate resources for the task
            allocated_request = None
            if resource_request is not None:
                allocated_request = await self._resource_allocation_manager.request_resources(
                    db, resource_request, lambda _: None
                )
                self._allocated_resources.setdefault(experiment_id, {})[task_id] = allocated_request

            if allocated_request is None or (
                allocated_request is not None and allocated_request.status == ResourceRequestAllocationStatus.ALLOCATED
            ):
                return ScheduledTask(
                    id=task_id,
                    experiment_id=experiment_id,
                    devices=[TaskDeviceConfig(lab_id=device.lab_id, id=device.id) for device in task_config.devices],
                    allocated_resources=allocated_request,
                )
            return None

        except Exception as e:
            log.warning(f"Error requesting resources for task '{task_id}' in experiment '{experiment_id}': {e}")
            return None

    async def update_parameters(self, parameters: dict) -> None:
        """
        Base implementation of parameter updates. Does nothing by default.

        :param parameters: Dictionary of parameter names and values to update.
        :return: None
        """

import asyncio
import threading

from eos.configuration.configuration_manager import ConfigurationManager
from eos.configuration.entities.task import TaskDeviceConfig, TaskConfig
from eos.configuration.experiment_graph.experiment_graph import ExperimentGraph
from eos.devices.device_manager import DeviceManager
from eos.devices.entities.device import DeviceStatus
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
from eos.scheduling.exceptions import EosSchedulerRegistrationError, EosSchedulerResourceAllocationError
from eos.tasks.task_input_resolver import TaskInputResolver
from eos.tasks.task_manager import TaskManager


class GreedyScheduler(AbstractScheduler):
    """
    The greedy scheduler is responsible for scheduling experiment tasks based on their precedence constraints and
    required devices. The scheduler uses a greedy policy, meaning that if a task is ready to be executed, it will be
    scheduled immediately.
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
        self._device_allocator = self._resource_allocation_manager.device_allocator
        self._container_allocator = self._resource_allocation_manager.container_allocator

        self._registered_experiments = {}
        self._allocated_resources: dict[str, dict[str, ActiveResourceAllocationRequest]] = {}
        self._lock = threading.Lock()

        log.debug("Greedy scheduler initialized.")

    def register_experiment(self, experiment_id: str, experiment_type: str, experiment_graph: ExperimentGraph) -> None:
        """
        Register an experiment for execution. The scheduler will also consider this experiment when tasks are requested.
        The scheduler records the experiment's ID, type, and task graph.
        """
        with self._lock:
            if experiment_type not in self._configuration_manager.experiments:
                raise EosSchedulerRegistrationError(
                    f"Cannot register an experiment with the scheduler. Experiment '{experiment_type}' does not exist."
                )
            self._registered_experiments[experiment_id] = (experiment_type, experiment_graph)
            log.debug("Experiment '%s' registered for scheduling.", experiment_id)

    async def unregister_experiment(self, experiment_id: str) -> None:
        """
        Unregister an experiment from the scheduler. The scheduler will no longer consider this experiment when tasks
        are requested.
        """
        with self._lock:
            if experiment_id in self._registered_experiments:
                del self._registered_experiments[experiment_id]
                await self._release_experiment_resources(experiment_id)
            else:
                raise EosSchedulerRegistrationError(
                    f"Cannot unregister experiment {experiment_id} from the scheduler as it is not registered."
                )

    async def request_tasks(self, experiment_id: str) -> list[ScheduledTask]:
        """
        Request the next tasks to be executed for a specific experiment. Resources such as devices are
        allocated for the tasks. The scheduler will only consider tasks that have all their dependencies met and have
        available resources.

        :param experiment_id: The ID of the experiment for which to request tasks.
        :return: A list of tasks that are ready to be executed.
        """
        with self._lock:
            if experiment_id not in self._registered_experiments:
                raise EosSchedulerRegistrationError(
                    f"Cannot request tasks from the scheduler for unregistered experiment {experiment_id}."
                )
            experiment_type, experiment_graph = self._registered_experiments[experiment_id]

        all_tasks = experiment_graph.get_topologically_sorted_tasks()
        completed_tasks = await self._experiment_manager.get_completed_tasks(experiment_id)
        pending_tasks = [task_id for task_id in all_tasks if task_id not in completed_tasks]

        # Release resources for completed tasks
        await asyncio.gather(
            *[
                self._release_task_resources(experiment_id, task_id)
                for task_id in completed_tasks
                if task_id in self._allocated_resources.get(experiment_id, {})
            ]
        )

        scheduled_tasks = []
        for task_id in pending_tasks:
            if not self._check_task_dependencies_met(task_id, completed_tasks, experiment_graph):
                continue

            task_config = experiment_graph.get_task_config(task_id)
            task_config = await self._task_input_resolver.resolve_input_container_references(experiment_id, task_config)

            device_checks = [self._check_device_available(device) for device in task_config.devices]
            if not all(await asyncio.gather(*device_checks)):
                continue
            container_checks = [
                self._check_container_available(container_id) for container_id in task_config.containers.values()
            ]
            if not all(await asyncio.gather(*container_checks)):
                continue

            try:
                resource_request = self._create_resource_request(experiment_id, task_id, task_config)
                allocated_resources = await self._request_resources(resource_request)
                self._allocated_resources.setdefault(experiment_id, {})[task_id] = allocated_resources
                scheduled_tasks.append(
                    ScheduledTask(
                        id=task_id,
                        experiment_id=experiment_id,
                        devices=[
                            TaskDeviceConfig(lab_id=device.lab_id, id=device.id) for device in task_config.devices
                        ],
                        allocated_resources=allocated_resources,
                    )
                )
            except EosSchedulerResourceAllocationError:
                log.warning(
                    f"Timed out in allocating resources for task '{task_id}' in experiment '{experiment_id}'. "
                    f"Will retry."
                )
                continue

        return scheduled_tasks

    def _create_resource_request(
        self, experiment_id: str, task_id: str, task_config: TaskConfig
    ) -> ResourceAllocationRequest:
        """
        Create a single resource allocation request for all devices and containers required by a task.
        """
        request = ResourceAllocationRequest(
            requester=task_id,
            experiment_id=experiment_id,
            reason=f"Resources required for task '{task_id}'",
        )

        for device in task_config.devices:
            request.add_resource(device.id, device.lab_id, ResourceType.DEVICE)

        for container_id in task_config.containers.values():
            request.add_resource(container_id, "", ResourceType.CONTAINER)

        return request

    async def _request_resources(
        self, resource_request: ResourceAllocationRequest, timeout: int = 15
    ) -> ActiveResourceAllocationRequest:
        """
        Request resources from the resource allocation manager for a single resource allocation request. This method
        will block until all resources are allocated or until the timeout is reached. If the timeout is reached, the
        resource allocation will be aborted and an error will be raised.

        :param resource_request: A resource allocation request to be allocated.
        :param timeout: The maximum time to wait for resource allocation in seconds.

        :return: An active resource allocation request that has been allocated.
        """
        allocation_event = asyncio.Event()
        active_request = None

        def resource_request_callback(request: ActiveResourceAllocationRequest) -> None:
            nonlocal active_request
            active_request = request
            allocation_event.set()

        active_resource_request = await self._resource_allocation_manager.request_resources(
            resource_request, resource_request_callback
        )

        if active_resource_request.status == ResourceRequestAllocationStatus.ALLOCATED:
            return active_resource_request

        await self._resource_allocation_manager.process_active_requests()

        try:
            await asyncio.wait_for(allocation_event.wait(), timeout)
        except asyncio.TimeoutError as e:
            await self._resource_allocation_manager.abort_active_request(active_resource_request.id)
            raise EosSchedulerResourceAllocationError(
                f"Resource allocation timed out after {timeout} seconds for task '{resource_request.requester}' "
                f"while trying to schedule it. "
                f"Aborting resource allocation for this task. Will retry again."
            ) from e

        if not active_request:
            raise EosSchedulerResourceAllocationError(
                f"Failed to allocate resources for task '{resource_request.requester}'."
            )

        return active_request

    async def _release_task_resources(self, experiment_id: str, task_id: str) -> None:
        active_request = self._allocated_resources[experiment_id].pop(task_id, None)
        if active_request:
            try:
                await self._resource_allocation_manager.release_resources(active_request)
                await self._resource_allocation_manager.process_active_requests()
            except EosResourceRequestError as e:
                log.error(f"Error releasing resources for task '{task_id}' in experiment '{experiment_id}': {e}")

    async def _release_experiment_resources(self, experiment_id: str) -> None:
        task_ids = list(self._allocated_resources.get(experiment_id, {}).keys())
        for task_id in task_ids:
            await self._release_task_resources(experiment_id, task_id)

        if experiment_id in self._allocated_resources:
            del self._allocated_resources[experiment_id]

    @staticmethod
    def _check_task_dependencies_met(
        task_id: str, completed_tasks: set[str], experiment_graph: ExperimentGraph
    ) -> bool:
        """
        Return True if all dependencies of a task have been completed, False otherwise.
        """
        dependencies = experiment_graph.get_task_dependencies(task_id)
        return all(dep in completed_tasks for dep in dependencies)

    async def _check_device_available(self, task_device: TaskDeviceConfig) -> bool:
        """
        Check if a device is available for a task. A device is available if it is active, not allocated by the device
        allocation manager.
        """
        device = await self._device_manager.get_device(task_device.lab_id, task_device.id)
        if device.status == DeviceStatus.INACTIVE:
            log.warning(
                f"Device {task_device.id} in lab {task_device.lab_id} is inactive but is requested by task "
                f"{task_device.id}."
            )
            return False

        return not await self._device_allocator.is_allocated(task_device.lab_id, task_device.id)

    async def _check_container_available(self, container_id: str) -> bool:
        """
        Check if a container is available for a task. A device is available if not allocated by the container
        allocation manager.
        """
        return not await self._container_allocator.is_allocated(container_id)

    async def is_experiment_completed(self, experiment_id: str) -> bool:
        """
        Check if an experiment has been completed. The scheduler should consider the completed tasks from the task
        manager to determine if the experiment has been completed.
        """
        if experiment_id not in self._registered_experiments:
            raise EosSchedulerRegistrationError(
                f"Cannot check if experiment {experiment_id} is completed as it is not registered."
            )

        experiment_type, experiment_graph = self._registered_experiments[experiment_id]
        all_tasks = experiment_graph.get_task_graph().nodes
        completed_tasks = await self._experiment_manager.get_completed_tasks(experiment_id)

        return all(task in completed_tasks for task in all_tasks)

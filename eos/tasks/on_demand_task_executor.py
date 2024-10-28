import asyncio
import traceback
from typing import Any

from eos.containers.container_manager import ContainerManager
from eos.containers.entities.container import Container
from eos.logging.logger import log
from eos.tasks.entities.task import TaskOutput, TaskDefinition
from eos.tasks.exceptions import EosTaskExecutionError, EosTaskValidationError, EosTaskStateError
from eos.tasks.task_executor import TaskExecutor
from eos.tasks.task_manager import TaskManager


class OnDemandTaskExecutor:
    """
    Executor for on-demand tasks (not part of an experiment or campaign).
    """

    EXPERIMENT_ID = "on_demand"

    def __init__(self, task_executor: TaskExecutor, task_manager: TaskManager, container_manager: ContainerManager):
        self._task_executor = task_executor
        self._task_manager = task_manager
        self._container_manager = container_manager

        self._task_futures: dict[str, asyncio.Task] = {}

        log.debug("On-demand task executor initialized.")

    def submit_task(self, task_definition: TaskDefinition) -> None:
        """Submit an on-demand task for execution."""
        self._task_futures[task_definition.id] = asyncio.create_task(
            self._task_executor.request_task_execution(task_definition)
        )
        log.info(f"Submitted on-demand task '{task_definition.id}'.")

    async def request_task_cancellation(self, task_id: str) -> None:
        """Request cancellation of an on-demand task."""
        if task_id not in self._task_futures:
            raise EosTaskExecutionError(f"Cannot cancel non-existent on-demand task '{task_id}'.")

        await self._task_executor.request_task_cancellation(self.EXPERIMENT_ID, task_id)
        self._task_futures[task_id].cancel()
        del self._task_futures[task_id]
        log.info(f"Cancelled on-demand task '{task_id}'.")

    async def process_tasks(self) -> None:
        """
        Process the on-demand tasks that have been submitted.
        This should be called periodically to check for task completion.
        """
        completed_tasks = []

        for task_id, future in self._task_futures.items():
            if future.done():
                try:
                    output = await future
                    await self._process_task_output(task_id, *output)
                except asyncio.CancelledError:
                    log.info(f"On-demand task '{task_id}' was cancelled.")
                except (EosTaskExecutionError, EosTaskValidationError, EosTaskStateError):
                    log.error(f"Failed on-demand task '{task_id}': {traceback.format_exc()}")
                finally:
                    completed_tasks.append(task_id)

        for task_id in completed_tasks:
            del self._task_futures[task_id]

    async def _process_task_output(
        self,
        task_id: str,
        output_parameters: dict[str, Any],
        output_containers: dict[str, Container],
        output_files: dict[str, bytes],
    ) -> None:
        await asyncio.gather(
            *[self._container_manager.update_container(container) for container in output_containers.values()]
        )

        task_output = TaskOutput(
            parameters=output_parameters,
            containers=output_containers,
            file_names=list(output_files.keys()),
        )

        for file_name, file_data in output_files.items():
            self._task_manager.add_task_output_file(self.EXPERIMENT_ID, task_id, file_name, file_data)

        await self._task_manager.add_task_output(self.EXPERIMENT_ID, task_id, task_output)
        await self._task_manager.complete_task(self.EXPERIMENT_ID, task_id)
        log.info(f"EXP '{self.EXPERIMENT_ID}' - Completed task '{task_id}'.")

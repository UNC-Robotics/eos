import asyncio
from typing import Any

import ray

from eos.configuration.eos_config import FileDbConfig
from eos.database.file_db_interface import FileDbInterface, get_worker_file_db
from eos.devices.device_actor_utils import DeviceActorReference, create_device_actor_dict
from eos.resources.entities.resource import Resource
from eos.tasks.file import File
from eos.tasks.task_definition import Context, TaskDefinition


@ray.remote(num_cpus=0)
def run_task(
    task_definition: TaskDefinition,
    file_db_config: FileDbConfig,
    protocol_run_name: str | None,
    task_name: str,
    device_actor_references: dict[str, DeviceActorReference],
    parameters: dict[str, Any],
    resources: dict[str, Resource],
    input_files: dict[str, str],
) -> tuple:
    """Execute a task in a Ray worker. Kept in a light module so workers avoid importing the orchestrator."""
    devices = create_device_actor_dict(device_actor_references)

    # Lazy: opens the SeaweedFS connection only on first input read or output upload.
    def file_db_provider() -> FileDbInterface:
        return get_worker_file_db(file_db_config)

    files = {name: File(file_db_provider, key) for name, key in input_files.items()}
    context = Context(task_name=task_name, protocol_run_name=protocol_run_name)
    return asyncio.run(task_definition.execute(context, devices, parameters, resources, files, file_db_provider))
